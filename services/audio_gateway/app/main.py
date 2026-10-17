"""
Audio Gateway Main

Phase 3.5: Audio Gateway FastAPI 애플리케이션
Phase 17.1: Pipeline Logging 추가
Phase 17.2: Service Heartbeat Logging (10초 간격)
"""
import asyncio
import json
from collections import deque
import os
import time
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional

import numpy as np
import redis.asyncio as redis
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from .aec import AcousticEchoCanceller
from .audio_io import AudioIOManager
from .audio_recorder import AudioRecorder
from .barge_in import BargeInDetector, PlaybackState
from .speech_barge_in import PlaybackTracker, SpeechBargeIn
from .pipeline_logger import get_logger, HEARTBEAT_INTERVAL
from .stt_client import STTClient
from .vad import VoiceActivityDetector


# 전역 컴포넌트
vad = VoiceActivityDetector()
aec = AcousticEchoCanceller()
# Phase 35.5: VAD 주입 패턴 적용 (M1 해결: 중복 VAD 인스턴스 방지)
barge_in_detector = BargeInDetector(vad=vad)
audio_io_manager = AudioIOManager()
# Phase 35.7: STT 연동 컴포넌트
audio_recorder = AudioRecorder()
# 말소리로 끼어들기: 앱으로 보낸 답 음성의 실제 재생 구간과, 에코보다 큰 목소리 감지
playback_tracker = PlaybackTracker()
speech_barge = SpeechBargeIn()
# 끼어든 첫마디가 녹음에서 빠지지 않게 최근 마이크 소리를 들고 있는다(0.8초)
_recent_chunks: deque = deque(maxlen=8)
stt_client = STTClient()

# Redis 클라이언트
redis_client: Optional[redis.Redis] = None

# Pipeline Logger
_logger = get_logger("audio_gateway")

# Redis 채널
AUDIO_OUTPUT_CHANNEL = "edgevoice:audio:input"
TTS_STATE_CHANNEL = "edgevoice:tts:state"
TTS_AUDIO_CHANNEL = "edgevoice:tts:audio"  # Phase 35.6: TTS 오디오 스트림 채널
WAKE_WORD_CHANNEL = "edgevoice:wake_word:detected"  # Phase 36.2: Wake Word 감지 채널 (Phase 47 Fix: 채널명 수정)
ORCHESTRATOR_STATE_CHANNEL = "edgevoice:orchestrator:state"  # Phase 50.3: Orchestrator 상태 채널

# 서비스 시작 시간 (heartbeat용)
_service_start_time: float = 0.0
_heartbeat_running: bool = False

# Phase 36.1.1: VAD 이벤트 상태 변수
_listening_mode: bool = False  # Wake Word 감지 후 녹음 대기 모드
_is_recording: bool = False    # 현재 녹음 중인지 여부
_previous_is_speech: bool = False  # 이전 VAD 결과

# Phase 36.2 & 36.4: 세션 추적
_current_session: Dict[str, Any] = {}  # 현재 세션 정보

# Phase 36.3: 음성 타임아웃
# Phase 50.3: 동적 설정 지원 - Orchestrator에서 브로드캐스트된 값으로 업데이트됨
# 말이 멈춘 뒤 답하기까지 기다리는 무음 시간.
# 설정 화면에서 바꾸면 Orchestrator 가 전달한다
DEFAULT_END_PAUSE_SECONDS = 2.0
_speech_timeout_seconds: float = DEFAULT_END_PAUSE_SECONDS
_last_speech_time: Optional[float] = None  # 마지막 음성 감지 시간
# 호출어 뒤 질문을 시작하기까지 기다리는 시간.
# 이 안에서는 무음이어도 녹음을 끝내지 않는다
# (호출어를 말하는 도중에 감지되면 바로 '말 끝' 이 돼 질문 전에 녹음이 끝났다 — 실측)
WAIT_FOR_QUESTION_SECONDS = 4.0
_question_wait_until: Optional[float] = None

# Phase 46: 녹음 진행 추적
_recording_chunk_count: int = 0  # 녹음 중 청크 카운트
_recording_total_samples: int = 0  # 녹음된 총 샘플 수


def check_speech_timeout() -> bool:
    """
    음성 타임아웃 확인 (Phase 36.3, Phase 50.3)

    마지막 음성 감지로부터 _speech_timeout_seconds 이상 경과했는지 확인합니다.
    타임아웃 값은 Orchestrator에서 동적으로 업데이트될 수 있습니다.

    Returns:
        타임아웃 발생 시 True, 아니면 False
    """
    global _last_speech_time, _speech_timeout_seconds

    if _last_speech_time is None:
        return False
    if _question_wait_until is not None and time.time() < _question_wait_until:
        return False

    elapsed = time.time() - _last_speech_time
    return elapsed >= _speech_timeout_seconds


async def process_speech_timeout() -> Optional[str]:
    """
    음성 타임아웃 처리 (Phase 36.3, Phase 50.3)

    end_pause_seconds 무음 후 녹음을 중지하고 STT를 호출합니다.
    타임아웃 값은 Orchestrator에서 동적으로 설정됩니다.

    Returns:
        STT 결과 텍스트, 실패 시 None
    """
    global _is_recording, _listening_mode, _last_speech_time, _speech_timeout_seconds

    if not _is_recording:
        return None

    session_id = _current_session.get("session_id", "unknown")

    await _logger.info(
        "speech_timeout",
        f"{_speech_timeout_seconds}초 무음 감지, STT 호출",
        metadata={"session_id": session_id, "timeout_seconds": _speech_timeout_seconds}
    )

    # Phase 46: 녹음 타임아웃 로그 (Pipeline에서 명확히 보이도록)
    await _logger.info(
        "recording_timeout",
        f"Voice input timeout ({_speech_timeout_seconds}s silence) - sending to STT",
        metadata={
            "session_id": session_id,
            "timeout_seconds": _speech_timeout_seconds
        }
    )

    # 녹음 종료 및 STT 호출
    _is_recording = False
    result = await on_speech_ended(session_id=session_id)

    # 세션 리셋
    await reset_session()

    return result


async def reset_session() -> None:
    """
    세션 상태 리셋 (Phase 36.4)

    STT 완료 후 또는 세션 종료 시 모든 상태를 초기화합니다.
    """
    global _current_session, _listening_mode, _is_recording, _last_speech_time
    global _question_wait_until

    _current_session = {}
    _listening_mode = False
    _is_recording = False
    _last_speech_time = None
    _question_wait_until = None

    await _logger.info(
        "session_reset",
        "세션 리셋 완료"
    )


def generate_session_id() -> str:
    """
    고유한 세션 ID 생성 (Phase 36.4)

    Returns:
        UUID 형식의 세션 ID
    """
    import uuid
    return f"session-{uuid.uuid4().hex[:12]}"


async def handle_wake_word_event(event_data: Dict[str, Any]) -> None:
    """
    Wake Word 이벤트 처리 (Phase 36.2)

    Args:
        event_data: Wake Word 이벤트 데이터
            - event: 이벤트 타입 ("wake_word_detected")
            - keyword: 감지된 키워드 (예: "에이전트")
            - confidence: 감지 신뢰도
    """
    global _listening_mode, _current_session

    keyword = event_data.get("keyword", "unknown")
    confidence = event_data.get("confidence", 0.0)

    # 새 세션 시작
    session_id = generate_session_id()
    _current_session = {
        "session_id": session_id,
        "started_at": time.time(),
        "keyword": keyword
    }

    # Listening 모드 활성화
    _listening_mode = True

    # Phase 49: Wake Word 직후 바로 음성 녹음 시작
    # 사용자가 "헤이 자비스, 오늘 날씨 어때?" 처럼 연속 발화 시
    # speech_started 이벤트 없이도 녹음이 시작되어야 함
    global _is_recording, _last_speech_time, _question_wait_until
    # 말하는 도중의 호출어 = 끼어들기: 재생을 끝내고 듣는다
    barge_in_detector.set_playback_state(PlaybackState.IDLE)
    aec.clear_playback_reference()
    if not _is_recording:
        await on_speech_started()
        _is_recording = True
        _last_speech_time = time.time()
    _question_wait_until = time.time() + WAIT_FOR_QUESTION_SECONDS

    await _logger.info(
        "wake_word_received",
        f"Wake Word 수신완료: {keyword}",
        metadata={
            "session_id": session_id,
            "keyword": keyword,
            "confidence": confidence
        }
    )

    # Phase 46: Listening 모드 시작 로그 (Pipeline에서 명확히 보이도록)
    await _logger.info(
        "listening_mode_started",
        "Listening mode activated - waiting for voice input",
        metadata={
            "wake_word": keyword,
            "confidence": confidence
        }
    )

    # Phase 49: 녹음 시작 로그
    await _logger.info(
        "recording_started",
        "Recording started immediately after Wake Word detection",
        metadata={
            "session_id": session_id,
            "wake_word": keyword
        }
    )


async def wake_word_subscriber() -> None:
    """
    Wake Word 이벤트 구독 태스크 (Phase 36.2)

    Redis Pub/Sub을 통해 Wake Word 감지 이벤트를 수신하고
    Listening 모드를 활성화합니다.
    """
    if redis_client is None:
        await _logger.warning(
            "wake_word_subscriber_skip",
            "Redis client not available, skipping Wake Word subscription"
        )
        return

    pubsub = redis_client.pubsub()
    await pubsub.subscribe(WAKE_WORD_CHANNEL)

    await _logger.info(
        "wake_word_subscriber_started",
        f"Subscribed to Wake Word channel: {WAKE_WORD_CHANNEL}"
    )

    try:
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue

            try:
                data = json.loads(message["data"])
                # Phase 47 Fix: Wake Word 서비스는 "type" 필드 사용
                event = data.get("type") or data.get("event")

                if event == "wake_word_detected":
                    await handle_wake_word_event(data)

            except json.JSONDecodeError as e:
                await _logger.error(
                    "wake_word_parse_error",
                    f"Failed to parse Wake Word message: {e}"
                )

    except asyncio.CancelledError:
        await _logger.info(
            "wake_word_subscriber_stopped",
            "Wake Word subscriber stopped"
        )
    finally:
        await pubsub.unsubscribe(WAKE_WORD_CHANNEL)


async def orchestrator_state_subscriber() -> None:
    """
    Orchestrator 상태 구독 태스크 (Phase 50.3)

    Redis Pub/Sub을 통해 Orchestrator 상태 변경 및 설정 업데이트를 수신합니다.
    - state_change: Orchestrator 상태 변경 시 settings 포함
    - settings_update: Dashboard에서 설정 변경 시 브로드캐스트
    """
    global _speech_timeout_seconds

    if redis_client is None:
        await _logger.warning(
            "orchestrator_subscriber_skip",
            "Redis client not available, skipping Orchestrator state subscription"
        )
        return

    pubsub = redis_client.pubsub()
    await pubsub.subscribe(ORCHESTRATOR_STATE_CHANNEL)

    await _logger.info(
        "orchestrator_subscriber_started",
        f"Subscribed to Orchestrator state channel: {ORCHESTRATOR_STATE_CHANNEL}"
    )

    try:
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue

            try:
                data = json.loads(message["data"])
                msg_type = data.get("type")

                # 설정 업데이트 처리
                settings = data.get("settings", {})
                if settings:
                    new_end_pause = settings.get("end_pause_seconds")
                    if new_end_pause is not None and new_end_pause != _speech_timeout_seconds:
                        old_value = _speech_timeout_seconds
                        _speech_timeout_seconds = new_end_pause
                        await _logger.info(
                            "settings_updated",
                            f"End pause updated: {old_value}s -> {_speech_timeout_seconds}s",
                            metadata={
                                "old_value": old_value,
                                "new_value": _speech_timeout_seconds,
                                "source": msg_type
                            }
                        )

            except json.JSONDecodeError as e:
                await _logger.error(
                    "orchestrator_parse_error",
                    f"Failed to parse Orchestrator message: {e}"
                )

    except asyncio.CancelledError:
        await _logger.info(
            "orchestrator_subscriber_stopped",
            "Orchestrator state subscriber stopped"
        )
    finally:
        await pubsub.unsubscribe(ORCHESTRATOR_STATE_CHANNEL)


async def heartbeat_task() -> None:
    """
    하트비트 로그 태스크 (10초 간격)

    서비스 생존 확인을 위해 주기적으로 로그를 전송합니다.
    """
    global _heartbeat_running
    _heartbeat_running = True

    while _heartbeat_running:
        uptime_seconds = int(time.time() - _service_start_time)
        await _logger.info(
            "heartbeat",
            f"Audio Gateway Service alive (uptime: {uptime_seconds}s)",
            metadata={
                "service": "audio_gateway",
                "uptime_seconds": uptime_seconds,
                "redis_connected": redis_client is not None,
                "vad_speaking": vad.is_currently_speaking,
                "playback_state": barge_in_detector.playback_state.name
            }
        )
        await asyncio.sleep(HEARTBEAT_INTERVAL)


async def tts_state_subscriber() -> None:
    """
    TTS 상태 이벤트 구독 태스크 (Phase 35.3.2)

    Redis Pub/Sub을 통해 TTS 상태 변경 이벤트를 수신하고
    PlaybackState와 AEC를 업데이트합니다.
    """
    if redis_client is None:
        await _logger.warning(
            "tts_state_subscriber_skip",
            "Redis client not available, skipping TTS state subscription"
        )
        return

    pubsub = redis_client.pubsub()
    await pubsub.subscribe(TTS_STATE_CHANNEL)

    await _logger.info(
        "tts_state_subscriber_started",
        f"Subscribed to TTS state channel: {TTS_STATE_CHANNEL}"
    )

    try:
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue

            try:
                data = json.loads(message["data"])
                event = data.get("event")

                if event == "tts_started" and _listening_mode:
                    # 끼어들어 듣는 중에 남은 문장이 합성돼도 재생 상태로 바꾸지 않는다
                    continue
                if event == "tts_started":
                    barge_in_detector.set_playback_state(PlaybackState.PLAYING)
                    await _logger.info(
                        "tts_started",
                        "TTS playback started, enabling barge-in detection",
                        metadata={"session_id": data.get("session_id")}
                    )

                elif event == "tts_complete":
                    barge_in_detector.set_playback_state(PlaybackState.IDLE)
                    aec.clear_playback_reference()
                    await _logger.info(
                        "tts_complete",
                        "TTS playback complete, disabling barge-in detection",
                        metadata={"session_id": data.get("session_id")}
                    )

            except json.JSONDecodeError as e:
                await _logger.error(
                    "tts_state_parse_error",
                    f"Failed to parse TTS state message: {e}"
                )

    except asyncio.CancelledError:
        await _logger.info(
            "tts_state_subscriber_stopped",
            "TTS state subscriber stopped"
        )
    finally:
        await pubsub.unsubscribe(TTS_STATE_CHANNEL)


# 정상 종료 코드: 1000 정상, 1001 떠남, 1005 상태 코드 없음(앱 종료), 1012 서비스 재시작
NORMAL_CLOSE_CODES = {1000, 1001, 1005, 1012}


def is_normal_close(error: Exception) -> bool:
    """WebSocket 수신 예외가 정상적인 연결 종료인지."""
    return isinstance(error, WebSocketDisconnect) and error.code in NORMAL_CLOSE_CODES


# 답변 음성을 재생할 /ws/audio 클라이언트들 (게이트웨이는 컨테이너 안이라 직접 재생할 수 없다)
_playback_clients: set = set()


def register_playback_client(websocket: Any) -> None:
    _playback_clients.add(websocket)


def unregister_playback_client(websocket: Any) -> None:
    _playback_clients.discard(websocket)


async def start_speech_barge_in() -> None:
    """
    답을 말하는 도중 사용자가 말했다: 끼어들기를 알리고(오케스트레이터가 답을 멈춤)
    바로 듣기·녹음. 감지하느라 지나간 첫마디(최근 0.8초)도 녹음에 넣는다.
    """
    pre_roll = list(_recent_chunks)
    playback_tracker.clear()
    speech_barge.reset()
    if redis_client is not None:
        event = {
            "type": "barge_in_detected", "source": "speech", "timestamp": time.time()
        }
        await redis_client.publish(barge_in_detector.redis_channel, json.dumps(event))
    await handle_wake_word_event({"type": "barge_in", "keyword": "speech"})
    for chunk in pre_roll:
        audio_recorder.add_chunk(chunk)
    await _logger.info("speech_barge_in", "말소리 끼어들기 — 답을 멈추고 듣는다")


async def publish_for_wake_word(processed: np.ndarray) -> None:
    """마이크 소리를 웨이크워드 서비스로 보낸다(실패해도 오디오 처리는 이어 간다)."""
    if redis_client is None:
        return
    try:
        await redis_client.publish(AUDIO_OUTPUT_CHANNEL, processed.tobytes())
    except Exception as e:
        await _logger.warning("wake_publish_failed", f"Wake publish error: {e}")


async def forward_tts_audio(audio_bytes: bytes) -> None:
    """TTS 오디오(float32 24kHz mono)를 연결된 클라이언트에 바이너리 프레임으로 보낸다."""
    if _listening_mode:
        return  # 끼어들어 듣는 중: 남은 답 음성은 틀지 않는다
    usable = len(audio_bytes) - len(audio_bytes) % 4  # float32 단위만
    if _playback_clients and usable:
        playback_tracker.add(np.frombuffer(audio_bytes[:usable], dtype=np.float32))
    for client in list(_playback_clients):
        try:
            await client.send_bytes(audio_bytes)
        except Exception:
            # 끊긴 클라이언트는 더 보내지 않는다
            _playback_clients.discard(client)


async def tts_audio_subscriber() -> None:
    """
    TTS 오디오 스트림 구독 태스크 (Phase 35.6)

    Redis Pub/Sub을 통해 TTS 오디오 데이터를 수신하고
    AEC playback reference로 설정합니다. (H1 해결)
    """
    if redis_client is None:
        await _logger.warning(
            "tts_audio_subscriber_skip",
            "Redis client not available, skipping TTS audio subscription"
        )
        return

    pubsub = redis_client.pubsub()
    await pubsub.subscribe(TTS_AUDIO_CHANNEL)

    await _logger.info(
        "tts_audio_subscriber_started",
        f"Subscribed to TTS audio channel: {TTS_AUDIO_CHANNEL}"
    )

    try:
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue

            try:
                # TTS 오디오 바이트를 float32 배열로 변환
                audio_bytes = message["data"]
                audio_data = np.frombuffer(audio_bytes, dtype=np.float32)

                if _listening_mode:
                    # 끼어들어 듣는 중: 틀지 않으므로 에코 기준으로도 쓰지 않는다
                    continue

                # AEC playback reference로 설정
                aec.set_playback_reference(audio_data)

                # 클라이언트 스피커로 재생하도록 전달
                await forward_tts_audio(audio_bytes)

                # Phase 43: log() 메서드 사용으로 event와 message 분리
                await _logger.log(
                    event="tts_audio_received",
                    data={
                        "message": f"TTS audio: {len(audio_data)} samples",
                        "samples": len(audio_data)
                    },
                    level="debug"
                )

            except Exception as e:
                await _logger.error(
                    "tts_audio_parse_error",
                    f"Failed to parse TTS audio: {e}"
                )

    except asyncio.CancelledError:
        await _logger.info(
            "tts_audio_subscriber_stopped",
            "TTS audio subscriber stopped"
        )
    finally:
        await pubsub.unsubscribe(TTS_AUDIO_CHANNEL)


# Phase 36.1.1: VAD 결과 처리 함수
async def handle_vad_result(
    vad_result: Dict[str, Any],
    session_id: str,
    audio_chunk: Optional[np.ndarray] = None
) -> Optional[str]:
    """
    VAD 결과를 처리하고 적절한 이벤트를 발생시킴 (Phase 36.1.1)

    Args:
        vad_result: VAD 감지 결과 딕셔너리
        session_id: 현재 세션 ID
        audio_chunk: 현재 오디오 청크 (녹음 중일 때 버퍼에 추가)

    Returns:
        STT 결과 텍스트 (음성 종료 시), 그 외에는 None
    """
    global _is_recording, _previous_is_speech, _last_speech_time

    # Listening 모드가 아니면 무시
    if not _listening_mode:
        return None

    is_speech = vad_result.get("is_speech", False)
    speech_started = vad_result.get("speech_started", False)
    speech_ended = vad_result.get("speech_ended", False)

    # 음성 시작 감지
    if speech_started and not _is_recording:
        await on_speech_started()
        _is_recording = True
        await _logger.info(
            "vad_speech_started",
            "사람 목소리 수신 중",
            metadata={"session_id": session_id, "probability": vad_result.get("probability")}
        )

    # Phase 36.3: 음성 감지 시 마지막 음성 시간 업데이트
    if is_speech and _is_recording:
        _last_speech_time = time.time()

    # 녹음 중이면 청크 추가 (Phase 49: 무음 구간도 포함하여 전체 녹음)
    # 사용자 발화 중 잠깐의 멈춤도 포함해야 자연스러운 STT 결과 생성
    if _is_recording and audio_chunk is not None:
        audio_recorder.add_chunk(audio_chunk)

        # Phase 46: 녹음 진행 상황 추적 및 로그
        global _recording_chunk_count, _recording_total_samples
        _recording_chunk_count += 1
        _recording_total_samples += len(audio_chunk)

        # 10 청크마다 recording_progress 로그
        if _recording_chunk_count % 10 == 0:
            duration_ms = int((_recording_total_samples / 16000) * 1000)
            await _logger.log(
                event="recording_progress",
                data={
                    "message": f"Recording: {_recording_total_samples} samples ({duration_ms}ms)",
                    "samples": _recording_total_samples,
                    "duration_ms": duration_ms,
                    "chunk_count": _recording_chunk_count
                },
                level="debug"
            )

    # 발화 종료는 VAD 의 짧은 무음(speech_ended)이 아니라 end_pause_seconds 무음으로만 판정한다
    # (process_speech_timeout). 웨이크워드 뒤나 문장 사이에 잠깐 쉬어도 녹음이 끊기지 않는다.
    _previous_is_speech = is_speech
    return None


# Phase 35.7.3: Speech 이벤트 핸들러
async def on_speech_started() -> None:
    """
    음성 감지 시작 이벤트 핸들러 (Phase 35.7.3)

    VAD에서 speech_started 이벤트 발생 시 AudioRecorder를 시작합니다.
    """
    global _recording_chunk_count, _recording_total_samples

    # Phase 46: 녹음 카운터 리셋
    _recording_chunk_count = 0
    _recording_total_samples = 0

    audio_recorder.start()
    await _logger.info(
        "speech_started",
        "Speech detected, started recording for STT"
    )

    # Phase 46: 녹음 시작 로그 (Pipeline에서 명확히 보이도록)
    await _logger.info(
        "recording_started",
        "Recording started - capturing voice input"
    )


async def on_speech_ended(session_id: str) -> Optional[str]:
    """
    음성 감지 종료 이벤트 핸들러 (Phase 35.7.3)

    VAD에서 speech_ended 이벤트 발생 시:
    1. AudioRecorder를 중지하고 오디오 데이터 획득
    2. WAV 형식으로 변환
    3. STT 서비스 호출 및 결과 발행

    Args:
        session_id: 현재 세션 ID

    Returns:
        인식된 텍스트, 실패 시 None
    """
    # 녹음 중지 및 오디오 데이터 획득
    audio_data = audio_recorder.stop()

    if len(audio_data) == 0:
        await _logger.warning(
            "speech_ended_empty",
            "Speech ended but no audio recorded"
        )
        return None

    # WAV 변환
    wav_bytes = audio_recorder.to_wav_bytes(audio_data)

    await _logger.info(
        "speech_ended",
        f"Speech ended, sending {len(audio_data)} samples to STT",
        metadata={
            "samples": len(audio_data),
            "wav_bytes": len(wav_bytes),
            "session_id": session_id
        }
    )

    # Phase 46: 녹음 완료 로그 (Pipeline에서 명확히 보이도록)
    duration_seconds = len(audio_data) / 16000
    await _logger.info(
        "recording_completed",
        f"Recording completed - {len(audio_data)} samples ({duration_seconds:.1f}s)",
        metadata={
            "session_id": session_id,
            "samples": len(audio_data),
            "duration_seconds": duration_seconds
        }
    )

    # STT 호출 및 결과 발행
    text = await stt_client.transcribe_and_publish(wav_bytes, session_id)

    if text:
        await _logger.info(
            "stt_result",
            f"STT transcription: {text[:50]}...",
            metadata={
                "session_id": session_id,
                "text_length": len(text)
            }
        )

    return text


# Phase 35.8: 에러 핸들링 유틸리티 함수
# 오디오 크기 제한 상수
MAX_AUDIO_SAMPLES = 48000  # 3초 @ 16kHz
MIN_AUDIO_SAMPLES = 160    # 10ms @ 16kHz


def validate_audio_size(audio: np.ndarray) -> bool:
    """
    오디오 데이터 크기 검증 (Phase 35.8.1)

    Args:
        audio: 오디오 데이터 배열

    Returns:
        유효한 크기면 True, 아니면 False
    """
    if len(audio) < MIN_AUDIO_SAMPLES:
        return False

    if len(audio) > MAX_AUDIO_SAMPLES:
        return False

    return True


def clip_audio(audio: np.ndarray) -> np.ndarray:
    """
    오디오 값을 -1.0 ~ 1.0 범위로 클리핑 (Phase 35.8.1)

    Args:
        audio: 오디오 데이터 배열

    Returns:
        클리핑된 오디오 배열
    """
    return np.clip(audio, -1.0, 1.0)


async def handle_websocket_error(
    error: Exception,
    error_type: str
) -> Dict[str, Any]:
    """
    WebSocket 에러 처리 (Phase 35.8.2)

    Args:
        error: 발생한 예외
        error_type: 에러 유형 (audio_parse, vad, redis 등)

    Returns:
        에러 처리 결과 (recoverable 여부 포함)
    """
    await _logger.error(
        f"websocket_{error_type}_error",
        f"WebSocket error ({error_type}): {error}",
        metadata={"error_type": error_type, "error": str(error)}
    )

    # 복구 가능한 에러 유형
    recoverable_types = ["audio_parse", "vad", "aec"]

    return {
        "error": str(error),
        "error_type": error_type,
        "recoverable": error_type in recoverable_types
    }


async def handle_redis_error(
    error: Exception,
    critical: bool = False
) -> None:
    """
    Redis 에러 처리 (Phase 35.8.2)

    Args:
        error: 발생한 예외
        critical: 심각한 에러 여부 (True면 연결 해제)
    """
    global redis_client

    await _logger.error(
        "redis_error",
        f"Redis error: {error}",
        metadata={"critical": critical, "error": str(error)}
    )

    if critical:
        redis_client = None


# Pydantic 모델
class VADConfigRequest(BaseModel):
    threshold: Optional[float] = None
    min_speech_duration_ms: Optional[int] = None


class ProcessAudioRequest(BaseModel):
    audio_base64: Optional[str] = None


# Phase 25.3: Settings Endpoint용 모델
class AudioSettingsRequest(BaseModel):
    """설정 업데이트 요청 모델"""
    vad_threshold: Optional[float] = None
    barge_in_energy_threshold: Optional[float] = None
    barge_in_vad_threshold: Optional[float] = None


# Phase 37: 내부 마이크 스트리밍 활성화 여부
USE_INTERNAL_MICROPHONE = os.getenv("USE_INTERNAL_MICROPHONE", "false").lower() == "true"


async def microphone_stream_task() -> None:
    """
    마이크 입력 스트리밍 태스크 (Phase 37)

    Docker 컨테이너 시작 시 자동으로 마이크에서 오디오를 읽어
    VAD → Wake Word → STT 파이프라인으로 전달합니다.

    USE_INTERNAL_MICROPHONE=true 환경 변수로 활성화됩니다.
    """
    global _listening_mode, _is_recording, _last_speech_time

    await _logger.info(
        "microphone_stream_started",
        "Docker internal microphone streaming started",
        metadata={
            "input_device": os.getenv("AUDIO_INPUT_DEVICE", "default"),
            "sample_rate": int(os.getenv("AUDIO_SAMPLE_RATE", "16000")),
            "chunk_size": int(os.getenv("AUDIO_CHUNK_SIZE", "1600"))
        }
    )

    try:
        # 오디오 스트림 시작
        audio_io_manager.start()
        chunk_count = 0

        while True:
            # 마이크에서 오디오 읽기
            audio_chunk = await audio_io_manager.get_input_chunk_async()

            if audio_chunk is None:
                await asyncio.sleep(0.01)
                continue

            chunk_count += 1

            # AEC 처리
            processed = aec.process(audio_chunk)

            # VAD 분석
            vad_result = vad.detect(processed)

            # VAD 결과 로깅 (10 청크마다, 약 1초)
            # Phase 43: log() 메서드 사용으로 event와 message 분리
            if vad_result.get("is_speech") and chunk_count % 10 == 0:
                prob = vad_result.get("probability", 0)
                await _logger.log(
                    event="mic_vad_speech_detected",
                    data={
                        "message": f"Mic VAD: prob={prob:.2f}",
                        "probability": prob,
                        "chunk_count": chunk_count
                    },
                    level="debug"
                )

            # VAD 이벤트 처리
            session_id = _current_session.get("session_id", "unknown")
            await handle_vad_result(vad_result, session_id, processed)

            # 음성 타임아웃 체크
            if _is_recording and check_speech_timeout():
                await process_speech_timeout()

            # 조건부 라우팅
            if barge_in_detector.playback_state == PlaybackState.PLAYING:
                # TTS 재생 중: Barge-in 감지 활성화 + '헤이 자비스' 끼어들기
                await barge_in_detector.detect_and_publish(processed)
                await publish_for_wake_word(processed)
            elif _listening_mode:
                # Phase 49: Listening 모드: Wake Word로 전달하지 않음
                # 음성 녹음은 handle_vad_result()에서 처리됨
                # 100 청크마다 로그 (디버그용)
                if chunk_count % 100 == 0 and vad_result.get("is_speech"):
                    await _logger.log(
                        event="listening_mode_active",
                        data={
                            "message": "Listening mode - audio NOT sent to Wake Word",
                            "is_recording": _is_recording,
                            "chunk_count": chunk_count
                        },
                        level="debug"
                    )
            else:
                # IDLE 모드: 소리를 끊지 않고 Wake Word 서비스로 전달
                # (VAD 로 조각만 보내면 웨이크워드 점수가 떨어진다 — 실측 99.9% → 40.7%)
                if redis_client:
                    try:
                        await redis_client.publish(
                            AUDIO_OUTPUT_CHANNEL,
                            processed.tobytes()
                        )
                    except Exception as e:
                        if chunk_count % 100 == 0:
                            await _logger.warning(
                                "mic_redis_publish_error",
                                f"Redis publish error: {e}"
                            )

    except asyncio.CancelledError:
        await _logger.info(
            "microphone_stream_cancelled",
            "Microphone streaming task cancelled"
        )
    except Exception as e:
        await _logger.error(
            "microphone_stream_error",
            f"Microphone streaming error: {e}",
            metadata={"error": str(e)}
        )
    finally:
        audio_io_manager.stop()
        await _logger.info(
            "microphone_stream_stopped",
            "Docker internal microphone streaming stopped"
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan handler"""
    global redis_client, _service_start_time, _heartbeat_running

    # Startup
    _service_start_time = time.time()
    redis_host = os.environ.get("REDIS_HOST", "localhost")
    redis_port = int(os.environ.get("REDIS_PORT", "6379"))

    print(f"Connecting to Redis at {redis_host}:{redis_port}...")

    try:
        redis_client = redis.Redis(
            host=redis_host,
            port=redis_port,
            decode_responses=False
        )
        await redis_client.ping()
        print("Redis connection established")
    except Exception as e:
        print(f"Warning: Redis connection failed: {e}")
        redis_client = None

    # Phase 35.1.1: Barge-in Detector에 Redis 클라이언트 주입
    if redis_client:
        barge_in_detector.redis_client = redis_client
        # Phase 48: STT 클라이언트에도 Redis 클라이언트 주입 (결과 발행용)
        stt_client.redis_client = redis_client

    await _logger.info(
        "audio_gateway_started",
        "Audio Gateway Service started",
        metadata={
            "redis_host": redis_host,
            "redis_port": redis_port,
            "redis_connected": redis_client is not None,
            "barge_in_redis_connected": barge_in_detector.redis_client is not None
        }
    )

    # Start heartbeat task (Phase 17.2)
    asyncio.create_task(heartbeat_task())

    # Phase 36.2: Start subscriber tasks
    asyncio.create_task(wake_word_subscriber())
    asyncio.create_task(tts_state_subscriber())
    asyncio.create_task(tts_audio_subscriber())

    # Phase 50.3: Start Orchestrator state subscriber for dynamic settings
    asyncio.create_task(orchestrator_state_subscriber())

    # Phase 37: Start internal microphone streaming if enabled
    if USE_INTERNAL_MICROPHONE:
        asyncio.create_task(microphone_stream_task())
        print("Internal microphone streaming enabled (USE_INTERNAL_MICROPHONE=true)")
    else:
        print("Using WebSocket for audio input (USE_INTERNAL_MICROPHONE=false)")

    print("Audio Gateway Service is ready")

    yield

    # Shutdown
    _heartbeat_running = False

    await _logger.info(
        "audio_gateway_stopped",
        "Audio Gateway Service stopped"
    )

    if redis_client:
        await redis_client.aclose()

    audio_io_manager.stop()
    print("Audio Gateway Service shutdown complete")


# FastAPI 앱 생성
app = FastAPI(
    title="Audio Gateway",
    description="EdgeVoice Audio Gateway Service",
    version="0.1.0",
    lifespan=lifespan
)


# Health 엔드포인트
@app.get("/health")
async def health():
    """
    헬스 체크 엔드포인트 - 단순 생존 확인만

    Returns:
        서비스 상태 정보
    """
    return {
        "status": "healthy",
        "service": "audio-gateway"
    }


@app.get("/info")
async def get_service_info():
    """
    서비스 상세 정보 조회 (Phase 28.1)

    Dashboard에서 사용할 서비스 정보를 반환합니다.
    /health와 분리하여 상세 정보만 제공합니다.
    """
    uptime_seconds = int(time.time() - _service_start_time) if _service_start_time > 0 else 0

    return {
        "service": "audio_gateway",
        "settings": {
            "vad_threshold": vad.threshold,
            "sample_rate": 16000,
            "aec_enabled": True
        },
        "components": {
            "vad": {
                "threshold": vad.threshold,
                "is_speaking": vad.is_currently_speaking
            },
            "aec": {
                "enabled": True,
                "has_playback_reference": aec.has_playback_reference
            },
            "barge_in": {
                "energy_threshold": barge_in_detector.energy_threshold,
                "playback_state": barge_in_detector.playback_state.name
            }
        },
        "stats": {
            "uptime_seconds": uptime_seconds,
            "redis_connected": redis_client is not None
        },
        "status": "ready"
    }


# WebSocket 오디오 스트림
@app.websocket("/ws/audio")
async def websocket_audio_stream(websocket: WebSocket):
    """
    WebSocket 오디오 스트리밍 엔드포인트

    양방향 오디오 스트리밍을 지원하며, 수신된 오디오를 Redis로 발행합니다.
    """
    await websocket.accept()
    print("[WS] WebSocket audio stream connected")

    # Phase 51: 새 연결 시 세션 상태 리셋
    # 이전 세션의 _listening_mode가 남아있으면 Wake Word 없이도 녹음이 시작될 수 있음
    await reset_session()

    await _logger.info(
        "websocket_connected",
        "WebSocket audio stream connected"
    )

    # 이 클라이언트가 답변 음성을 받아 재생한다
    register_playback_client(websocket)

    chunk_count = 0

    try:
        while True:
            # 클라이언트로부터 오디오 데이터 수신
            try:
                data = await websocket.receive_bytes()
            except Exception as recv_error:
                if is_normal_close(recv_error):
                    # 앱 종료·서비스 재시작 등 정상 종료는 오류가 아니다
                    await _logger.info(
                        "websocket_closed",
                        f"WebSocket closed: {recv_error}"
                    )
                    break
                print(f"[WS] Receive error: {recv_error}")
                await _logger.error(
                    "websocket_receive_error",
                    f"Failed to receive data: {recv_error}"
                )
                break

            # Phase 38: 오디오 형식 자동 감지 및 변환
            # int16 (2 bytes per sample) vs float32 (4 bytes per sample)
            data_len = len(data)
            chunk_count += 1

            # 첫 번째 청크에 대해 상세 로깅
            if chunk_count == 1:
                print(f"[WS] First audio chunk: {data_len} bytes")
                await _logger.info(
                    "first_audio_chunk",
                    f"First audio chunk received: {data_len} bytes",
                    metadata={"data_length": data_len}
                )

            # 10 청크마다 로그
            if chunk_count % 10 == 0:
                print(f"[WS] Processed {chunk_count} chunks")

            # int16 데이터 감지 (2 bytes per sample)
            # 데이터 길이가 짝수이고, float32로 해석하면 비정상적인 값이 나올 때
            if data_len % 2 == 0:
                # int16으로 시도
                audio_int16 = np.frombuffer(data, dtype=np.int16)
                audio = audio_int16.astype(np.float32) / 32768.0
            else:
                # float32로 시도
                audio = np.frombuffer(data, dtype=np.float32)

            processed = aec.process(audio)
            vad_result = vad.detect(processed)
            _recent_chunks.append(processed)
            if not _listening_mode and playback_tracker.playing():
                rms = float(np.sqrt(np.mean(processed**2))) if len(processed) else 0.0
                if speech_barge.feed(
                    rms, vad_result.get("probability", 0.0), playback_tracker.level()
                ):
                    await start_speech_barge_in()

            # 10 청크마다 VAD 확률 로그 (콘솔 + Pipeline Log)
            if chunk_count % 10 == 0:
                prob = vad_result.get("probability", 0)
                is_speech = vad_result.get("is_speech", False)
                print(f"[WS] VAD: prob={prob:.3f}, is_speech={is_speech}")

                # Phase 41/43: Pipeline Log에 VAD 확률 발행 (log() 메서드 사용)
                await _logger.log(
                    event="vad_probability",
                    data={
                        "message": f"VAD: prob={prob:.3f}, speech={is_speech}",
                        "probability": float(prob),
                        "is_speech": is_speech,
                        "chunk_count": chunk_count,
                        "listening_mode": _listening_mode,
                        "is_recording": _is_recording
                    },
                    level="debug"
                )

            # Phase 36.1: VAD 결과 로깅 (음성 감지 시)
            if vad_result.get("is_speech"):
                # 10 청크마다 로그 (약 1초)
                if chunk_count % 10 == 0:
                    await _logger.info(
                        "vad_speech_detected",
                        f"사람 목소리 수신 중 (probability: {vad_result.get('probability', 0):.2f})",
                        metadata={
                            "probability": vad_result.get("probability"),
                            "chunk_count": chunk_count,
                            "listening_mode": _listening_mode
                        }
                    )

            # Phase 36.1: handle_vad_result 호출 (Listening 모드일 때)
            session_id = _current_session.get("session_id", "unknown")
            await handle_vad_result(vad_result, session_id, processed)

            # Phase 36.3: 음성 타임아웃 체크 (녹음 중일 때)
            if _is_recording and check_speech_timeout():
                await process_speech_timeout()

            # Phase 35.2.1 & 35.3.1: TTS 재생 상태에 따른 조건부 라우팅
            if barge_in_detector.playback_state == PlaybackState.PLAYING:
                # TTS 재생 중: Barge-in 감지 활성화
                barge_in_result = await barge_in_detector.detect_and_publish(processed)
                vad_result["barge_in"] = barge_in_result
                # 말하는 도중 '헤이 자비스' 로 끼어들 수 있게 웨이크워드로도 보낸다
                # (에너지 끼어들기는 스피커 소리가 마이크로 다시 들어와 동작하지 않았다)
                await publish_for_wake_word(processed)
            elif _listening_mode:
                # Phase 49: Listening 모드: Wake Word로 전달하지 않음
                # 음성 녹음은 handle_vad_result()에서 처리됨
                # 100 청크마다 로그 (디버그용)
                if chunk_count % 100 == 0 and vad_result.get("is_speech"):
                    await _logger.log(
                        event="listening_mode_active",
                        data={
                            "message": "Listening mode - audio NOT sent to Wake Word",
                            "is_recording": _is_recording,
                            "chunk_count": chunk_count
                        },
                        level="debug"
                    )
            else:
                # IDLE 모드: 소리를 끊지 않고 Wake Word 서비스로 전달
                # (VAD 로 조각만 보내면 웨이크워드 점수가 떨어진다 — 실측 99.9% → 40.7%)
                if redis_client:
                    try:
                        await redis_client.publish(
                            AUDIO_OUTPUT_CHANNEL,
                            processed.tobytes()
                        )

                        # 50 청크마다 로그 (약 5초)
                        if chunk_count % 50 == 0:
                            print(f"[WS] Published {chunk_count} chunks to Redis ({AUDIO_OUTPUT_CHANNEL})")

                        # 100 청크마다 로그 (약 10초)
                        # Phase 43: log() 메서드 사용
                        if chunk_count % 100 == 0:
                            await _logger.log(
                                event="audio_chunks_published",
                                data={
                                    "message": f"Published {chunk_count} chunks to Redis",
                                    "chunk_count": chunk_count
                                },
                                level="debug"
                            )
                    except Exception as e:
                        await _logger.error(
                            "redis_publish_failed",
                            f"Failed to publish audio to Redis: {e}"
                        )

            # 결과 전송
            await websocket.send_json(vad_result)

    except WebSocketDisconnect:
        await _logger.info(
            "websocket_disconnected",
            f"WebSocket disconnected after {chunk_count} chunks",
            metadata={"total_chunks": chunk_count}
        )
    finally:
        unregister_playback_client(websocket)


# 오디오 처리 엔드포인트
@app.post("/process")
async def process_audio(request: ProcessAudioRequest):
    """
    단일 오디오 청크 처리

    Args:
        request: 오디오 데이터 요청

    Returns:
        처리 결과
    """
    return {"processed": True, "vad_result": None}


# 재생 제어 엔드포인트
@app.post("/playback/start")
async def playback_start():
    """재생 상태 시작"""
    barge_in_detector.set_playback_state(PlaybackState.PLAYING)
    return {"status": "playing"}


@app.post("/playback/stop")
async def playback_stop():
    """재생 중지 및 큐 비우기"""
    barge_in_detector.set_playback_state(PlaybackState.IDLE)
    audio_io_manager.stop_playback()
    return {"status": "stopped"}


@app.get("/playback/status")
async def playback_status():
    """재생 상태 조회"""
    return {
        "is_playing": barge_in_detector.playback_state == PlaybackState.PLAYING,
        "queue_size": audio_io_manager.output_stream.queue_size,
        "playback_state": barge_in_detector.playback_state.name
    }


# VAD 엔드포인트
@app.get("/vad/status")
async def vad_status():
    """VAD 상태 조회"""
    return {
        "is_speaking": vad.is_currently_speaking,
        "threshold": vad.threshold
    }


@app.post("/vad/config")
async def vad_config_update(request: VADConfigRequest):
    """VAD 설정 업데이트"""
    if request.threshold is not None:
        vad.set_threshold(request.threshold)

    return {"status": "updated", "threshold": vad.threshold}


# AEC 엔드포인트
@app.get("/aec/status")
async def aec_status():
    """AEC 상태 조회"""
    return {
        "enabled": True,
        "has_playback_reference": aec.has_playback_reference,
        "filter_length": aec.filter_length
    }


@app.post("/aec/reset")
async def aec_reset():
    """AEC 리셋"""
    aec.reset()
    return {"status": "reset"}


# Barge-in 엔드포인트
@app.get("/barge-in/status")
async def barge_in_status():
    """Barge-in 상태 조회"""
    return {
        "playback_state": barge_in_detector.playback_state.name,
        "in_cooldown": barge_in_detector._in_cooldown,
        "energy_threshold": barge_in_detector.energy_threshold,
        "vad_threshold": barge_in_detector.vad_threshold
    }


# Phase 25.3: Settings 엔드포인트 (Backend에서 설정 전파 수신용)
@app.put("/settings")
async def update_settings(request: AudioSettingsRequest):
    """
    Audio Gateway 설정 업데이트

    Backend 서비스에서 설정 전파 시 호출됩니다.

    Args:
        request: 업데이트할 설정 값들

    Returns:
        업데이트된 설정 상태
    """
    updated = {}

    # VAD 설정 업데이트
    if request.vad_threshold is not None:
        vad.set_threshold(request.vad_threshold)
        updated["vad_threshold"] = request.vad_threshold

    # Barge-in 설정 업데이트
    if request.barge_in_energy_threshold is not None:
        barge_in_detector.energy_threshold = request.barge_in_energy_threshold
        updated["barge_in_energy_threshold"] = request.barge_in_energy_threshold

    if request.barge_in_vad_threshold is not None:
        barge_in_detector.vad_threshold = request.barge_in_vad_threshold
        updated["barge_in_vad_threshold"] = request.barge_in_vad_threshold

    return {
        "status": "updated",
        "updated_fields": updated,
        "vad": {
            "threshold": vad.threshold,
            "is_speaking": vad.is_currently_speaking
        },
        "barge_in": {
            "energy_threshold": barge_in_detector.energy_threshold,
            "vad_threshold": barge_in_detector.vad_threshold,
            "playback_state": barge_in_detector.playback_state.name
        }
    }


@app.get("/settings")
async def get_settings():
    """
    현재 Audio Gateway 설정 조회

    Returns:
        현재 설정 상태
    """
    return {
        "vad": {
            "threshold": vad.threshold,
            "is_speaking": vad.is_currently_speaking
        },
        "barge_in": {
            "energy_threshold": barge_in_detector.energy_threshold,
            "vad_threshold": barge_in_detector.vad_threshold,
            "playback_state": barge_in_detector.playback_state.name,
            "in_cooldown": barge_in_detector._in_cooldown
        },
        "aec": {
            "enabled": True,
            "has_playback_reference": aec.has_playback_reference,
            "filter_length": aec.filter_length
        },
        # Phase 50.3: 동적 speech timeout 설정
        "speech_timeout": {
            "end_pause_seconds": _speech_timeout_seconds,
            "description": "Silence duration before speech is considered complete"
        }
    }
