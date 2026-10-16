"""
Orchestrator Main

Phase 2.3: 음성 대화 흐름을 관리하는 오케스트레이터
Redis 이벤트 기반으로 STT, LLM, TTS를 조율
"""
import asyncio
import json
import os
import re
import time
from typing import Any, Optional

from .llm_client import LLMClient
from .pipeline_logger import get_logger
from .queue_manager import SentenceQueueManager
from .state_machine import OrchestratorStateMachine, State

DEFAULT_VOICE_SYSTEM_PROMPT = (
    "당신은 EdgeVoice 음성 비서입니다. 항상 한국어로 답하세요. "
    "답은 소리 내어 읽기 좋게 2~3문장으로 짧고 자연스럽게 말하고, "
    "목록 기호·마크다운·이모지는 쓰지 마세요."
)

# 녹음에 섞여 들어온 웨이크워드("Hey Jarvis", "헤이 자비스")를 STT 결과 앞에서 뗀다
WAKE_PHRASE_PATTERN = re.compile(
    r"^\s*(?:hey|hi|헤이|해이)[\s,.!~\-]*(?:jarvis|자비스|쟈비스)[\s,.!?~\-]*",
    re.IGNORECASE,
)


def strip_wake_phrase(text: str) -> str:
    return WAKE_PHRASE_PATTERN.sub("", text, count=1).strip()


class Orchestrator:
    """
    음성 대화 오케스트레이터

    역할:
    - Wake Word 감지 후 음성 입력 수신
    - STT 결과를 LLM으로 전달
    - LLM 응답을 문장 단위로 분리하여 TTS로 전달
    - Barge-in 감지 시 응답 중단 및 새 입력 수신
    - 대화 컨텍스트 관리

    Attributes:
        state_machine: 상태 머신
        queue_manager: 문장 큐 관리자
        llm_client: LLM 클라이언트
        redis: Redis 클라이언트
    """

    # Redis 채널
    CHANNELS = {
        "wake_word": "edgevoice:wake_word:detected",
        "stt_result": "edgevoice:stt:result",
        "stt_partial": "edgevoice:stt:partial",
        "barge_in": "edgevoice:barge_in:detected",
        "tts_request": "edgevoice:tts:request",
        "tts_complete": "edgevoice:tts:complete",
        "state_change": "edgevoice:orchestrator:state"
    }

    # 백엔드 StateManager 의 ORCHESTRATOR_STATE_KEY 와 같은 키
    STATE_KEY = "orchestrator:state"
    STATE_KEY_TTL_SECONDS = 300

    # 듣기 상태에서 발화·end_pause·STT 처리를 기다리는 여유 시간
    UTTERANCE_GRACE_SECONDS = 30.0

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        redis_client: Optional[Any] = None,
        listening_timeout: float = 10.0,
        end_pause_seconds: float = 3.0,
        environment: str = "development"
    ):
        """
        Orchestrator 초기화

        Args:
            llm_client: LLM 클라이언트 (기본: 새로 생성)
            redis_client: Redis 클라이언트 (기본: 새로 연결)
            listening_timeout: LISTENING 상태 타임아웃 (초)
            end_pause_seconds: 음성 종료 감지를 위한 무음 시간 (초) - Phase 50
            environment: 환경 설정
        """
        self.environment = environment
        self.listening_timeout = listening_timeout
        # Phase 50: End Pause 설정
        self.end_pause_seconds = end_pause_seconds

        # 상태 머신 초기화
        self.state_machine = OrchestratorStateMachine(
            on_state_change=self._on_state_change
        )

        # LLM 클라이언트 (음성 경로는 한국어로 짧게 답하도록 시스템 프롬프트를 준다)
        self.llm_client = llm_client or LLMClient(
            environment=environment,
            system_prompt=os.getenv("VOICE_SYSTEM_PROMPT", DEFAULT_VOICE_SYSTEM_PROMPT),
        )

        # Redis 클라이언트 (lazy initialization)
        self.redis = redis_client
        if self.redis is None:
            self.redis = self._setup_redis()

        # 문장 큐 관리자
        self.queue_manager = SentenceQueueManager(
            redis_client=self.redis,
            redis_channel=self.CHANNELS["tts_request"]
        )

        # 내부 상태
        self._listening_task: Optional[asyncio.Task] = None
        self._processing_task: Optional[asyncio.Task] = None
        self._is_running = False

        # TTS 설정 (Phase 8.3)
        self._current_session_id: Optional[str] = None
        self._tts_voice: str = os.getenv("TTS_VOICE", "af_heart")
        self._tts_speed: float = float(os.getenv("TTS_SPEED", "1.0"))

        # Pipeline Logger (Phase 17)
        self._logger = get_logger("orchestrator")

    def _setup_redis(self) -> Any:
        """Redis 클라이언트 설정 (Mock 반환 for testing)"""
        try:
            import redis.asyncio as redis
            redis_host = os.getenv("REDIS_HOST", "localhost")
            redis_port = int(os.getenv("REDIS_PORT", "6379"))
            return redis.Redis(host=redis_host, port=redis_port, decode_responses=True)
        except Exception:
            return None

    def _on_state_change(self, old_state: State, new_state: State) -> None:
        """상태 변경 콜백"""
        # Redis로 상태 변경 브로드캐스트 (비동기로 처리)
        if self.redis:
            asyncio.create_task(self._publish_state_change(old_state, new_state))

    async def _publish_state_change(self, old_state: State, new_state: State) -> None:
        """상태 변경을 Redis로 발행"""
        if self.redis:
            message = json.dumps({
                "type": "state_change",
                "old_state": old_state.name,
                "new_state": new_state.name,
                # Phase 50: 상태 변경 시 설정 정보도 포함
                "settings": {
                    "end_pause_seconds": self.end_pause_seconds,
                    "listening_timeout_seconds": self.listening_timeout
                }
            })
            try:
                await self.redis.publish(self.CHANNELS["state_change"], message)
            except Exception:
                pass

            # 백엔드 /api/status/stream 은 이 키를 읽는다 (없으면 항상 OFF 로 보인다)
            current = json.dumps({
                "state": new_state.name,
                "session_id": self._current_session_id,
                "timestamp": time.time()
            })
            try:
                await self.redis.set(self.STATE_KEY, current, ex=self.STATE_KEY_TTL_SECONDS)
            except Exception:
                pass

    async def broadcast_settings(self) -> None:
        """
        Phase 50: 현재 설정을 Redis로 브로드캐스트

        Audio Gateway 등 다른 서비스가 설정 변경을 수신할 수 있도록 합니다.
        """
        if not self.redis:
            return

        message = json.dumps({
            "type": "settings_update",
            "current_state": self.state_machine.current_state.name,
            "settings": {
                "end_pause_seconds": self.end_pause_seconds,
                "listening_timeout_seconds": self.listening_timeout
            },
            "timestamp": time.time()
        })

        try:
            await self.redis.publish(self.CHANNELS["state_change"], message)
            await self._logger.log(
                event="settings_broadcast",
                data={
                    "message": f"Settings broadcast: end_pause={self.end_pause_seconds}s",
                    "end_pause_seconds": self.end_pause_seconds,
                    "listening_timeout_seconds": self.listening_timeout
                }
            )
        except Exception as e:
            await self._logger.log(
                event="settings_broadcast_failed",
                data={"error": str(e)},
                level="error"
            )

    async def handle_wake_word(self) -> bool:
        """
        Wake Word 감지 이벤트 처리

        Returns:
            처리 성공 여부
        """
        # Phase 32: IDLE → READY 별칭이므로 READY도 허용
        if self.state_machine.current_state not in (State.IDLE, State.READY):
            await self._logger.log(
                event="wake_word_ignored",
                session_id=self._current_session_id,
                data={"current_state": self.state_machine.current_state.name},
                level="warning"
            )
            return False

        success = self.state_machine.transition_to(State.LISTENING)

        if success:
            await self._logger.log(
                event="wake_word_detected",
                session_id=self._current_session_id,
                data={"message": "Wake word detected, transitioning to LISTENING state"}
            )
            # 타임아웃 타이머 시작
            self._start_listening_timeout()

        return success

    async def handle_stt_result(self, text: str) -> None:
        """
        STT 결과 처리

        Args:
            text: 인식된 텍스트
        """
        if self.state_machine.current_state != State.LISTENING:
            return

        text = strip_wake_phrase(text)
        if not text:
            # 웨이크워드만 들렸으면 LLM 을 부르지 않고 대기로 돌아간다
            self._cancel_listening_timeout()
            self.state_machine.transition_to(State.READY)
            return

        await self._logger.log(
            event="stt_result_received",
            session_id=self._current_session_id,
            data={
                "message": f"STT result received: {text[:50]}{'...' if len(text) > 50 else ''}",
                "text_length": len(text)
            }
        )

        # 타임아웃 타이머 취소
        self._cancel_listening_timeout()

        # Phase 32: LISTENING → STT_PROCESSING → LLM_PROCESSING
        self.state_machine.transition_to(State.STT_PROCESSING)
        self.state_machine.transition_to(State.LLM_PROCESSING)

        # LLM 처리 시작
        await self.process_user_input(text)

    async def handle_barge_in(self) -> bool:
        """
        Barge-in 이벤트 처리

        Returns:
            처리 성공 여부
        """
        await self._logger.log(
            event="barge_in_detected",
            session_id=self._current_session_id,
            data={"message": "Barge-in detected, interrupting current response"}
        )

        # 진행 중인 처리 취소
        if self._processing_task and not self._processing_task.done():
            self._processing_task.cancel()

        # 큐 클리어
        self.queue_manager.clear_on_barge_in()

        # 상태 전이
        return self.state_machine.handle_barge_in()

    async def handle_timeout(self) -> bool:
        """
        타임아웃 이벤트 처리

        Returns:
            처리 성공 여부
        """
        return self.state_machine.handle_timeout()

    async def handle_speaking_complete(self) -> bool:
        """
        TTS 출력 완료 처리

        Returns:
            처리 성공 여부
        """
        # Phase 32: SPEAKING은 TTS_PROCESSING의 별칭
        if self.state_machine.current_state in (State.SPEAKING, State.TTS_PROCESSING):
            # Phase 32: IDLE은 READY의 별칭
            return self.state_machine.transition_to(State.READY)
        return False

    async def process_user_input(self, text: str) -> None:
        """
        사용자 입력 처리 (LLM 호출)

        Args:
            text: 사용자 입력 텍스트
        """
        # 사용자 메시지는 generate_stream 이 요청에 붙이므로 여기서 컨텍스트에 미리 넣지 않는다
        # (응답이 끝나면 _process_llm_stream 이 user/assistant 를 함께 기록)

        # LLM 스트리밍 처리
        self._processing_task = asyncio.create_task(
            self._process_llm_stream(text)
        )

        try:
            await self._processing_task
        except asyncio.CancelledError:
            # Barge-in으로 인한 취소
            pass

    async def _process_llm_stream(self, text: str) -> None:
        """
        LLM 스트리밍 응답 처리

        Args:
            text: 사용자 입력 텍스트
        """
        first_sentence_sent = False
        full_response = ""
        llm_start_time = time.time()

        await self._logger.log(
            event="llm_processing_started",
            session_id=self._current_session_id,
            data={"message": "LLM processing started", "input_text": text[:100]}
        )

        try:
            async for token in self.llm_client.generate_stream(text):
                # 토큰을 큐 매니저에 추가
                await self.queue_manager.add_token_async(token)
                full_response += token

                # 완성된 문장 확인
                sentences = self.queue_manager.get_complete_sentences()

                for sentence in sentences:
                    # Phase 32: 첫 문장에서 TTS_PROCESSING 상태로 전이
                    if not first_sentence_sent:
                        # LLM_PROCESSING 또는 PROCESSING(별칭)에서 TTS_PROCESSING으로 전이
                        if self.state_machine.current_state in (State.LLM_PROCESSING, State.PROCESSING):
                            self.state_machine.transition_to(State.TTS_PROCESSING)
                        first_sentence_sent = True

                    # TTS 요청 발행
                    await self.publish_tts_request(sentence)

            # 남은 버퍼 처리
            remaining = self.queue_manager.flush()
            if remaining and len(remaining.strip()) > 0:
                if not first_sentence_sent:
                    if self.state_machine.current_state in (State.LLM_PROCESSING, State.PROCESSING):
                        self.state_machine.transition_to(State.TTS_PROCESSING)
                await self.publish_tts_request(remaining)

            # 어시스턴트 응답을 컨텍스트에 추가
            if hasattr(self.llm_client, 'add_to_context') and full_response:
                self.llm_client.add_to_context("user", text)
                self.llm_client.add_to_context("assistant", full_response)

            # Phase 32: 모든 처리 완료 후 READY로 전이
            if self.state_machine.current_state in (State.TTS_PROCESSING, State.SPEAKING):
                self.state_machine.transition_to(State.READY)

            llm_duration = int((time.time() - llm_start_time) * 1000)
            await self._logger.log(
                event="llm_processing_completed",
                session_id=self._current_session_id,
                data={
                    "message": f"LLM processing completed ({llm_duration}ms)",
                    "duration_ms": llm_duration,
                    "response_length": len(full_response)
                }
            )

        except asyncio.CancelledError:
            await self._logger.log(
                event="llm_processing_cancelled",
                session_id=self._current_session_id,
                data={"message": "LLM processing cancelled (barge-in)"}
            )
            raise
        except Exception as e:
            await self._logger.log(
                event="llm_processing_error",
                session_id=self._current_session_id,
                data={"message": f"LLM processing error: {str(e)}", "error": str(e)},
                level="error"
            )
            # 에러 시 IDLE로 복귀
            self.state_machine.reset()

    async def publish_tts_request(self, text: str) -> None:
        """
        TTS 요청을 Redis로 발행

        Args:
            text: 합성할 텍스트
        """
        await self._logger.log(
            event="tts_request_sent",
            session_id=self._current_session_id,
            data={
                "message": f"TTS request sent: {text[:50]}{'...' if len(text) > 50 else ''}",
                "text_length": len(text),
                "voice": self._tts_voice
            }
        )

        if self.redis:
            message = json.dumps({
                "session_id": self._current_session_id,
                "text": text,
                "voice": self._tts_voice,
                "speed": self._tts_speed,
                "timestamp": time.time()
            })
            try:
                await self.redis.publish(self.CHANNELS["tts_request"], message)
            except Exception as e:
                await self._logger.log(
                    event="tts_request_failed",
                    session_id=self._current_session_id,
                    data={
                        "message": f"Failed to publish TTS request: {str(e)}",
                        "error": str(e)
                    },
                    level="error"
                )

    async def subscribe_events(self) -> None:
        """Redis 이벤트 구독 시작"""
        if not self.redis:
            return

        pubsub = self.redis.pubsub()
        await pubsub.subscribe(
            self.CHANNELS["wake_word"],
            self.CHANNELS["stt_result"],
            self.CHANNELS["barge_in"],
            self.CHANNELS["tts_complete"]
        )

    async def reset_session(self) -> None:
        """세션 초기화 (대화 컨텍스트 클리어)"""
        if hasattr(self.llm_client, 'clear_context'):
            self.llm_client.clear_context()

        self.queue_manager.clear_on_barge_in()
        self.state_machine.reset()

    def _start_listening_timeout(self) -> None:
        """LISTENING 타임아웃 타이머 시작"""
        if self._listening_task:
            self._listening_task.cancel()

        async def timeout_handler():
            # 말 시작 대기(listening_timeout) + 말하는 시간·end_pause·STT 처리 여유.
            # 말이 아예 없으면 게이트웨이가 먼저 듣기를 끝낸다.
            await asyncio.sleep(self.listening_timeout + self.UTTERANCE_GRACE_SECONDS)
            if self.state_machine.current_state == State.LISTENING:
                await self.handle_timeout()

        self._listening_task = asyncio.create_task(timeout_handler())

    def _cancel_listening_timeout(self) -> None:
        """LISTENING 타임아웃 타이머 취소"""
        if self._listening_task and not self._listening_task.done():
            self._listening_task.cancel()
            self._listening_task = None

    async def run(self) -> None:
        """오케스트레이터 메인 루프 실행"""
        self._is_running = True

        if not self.redis:
            print("Redis not available, running in standalone mode")
            return

        pubsub = self.redis.pubsub()
        await pubsub.subscribe(
            self.CHANNELS["wake_word"],
            self.CHANNELS["stt_result"],
            self.CHANNELS["barge_in"],
            self.CHANNELS["tts_complete"]
        )

        try:
            async for message in pubsub.listen():
                if not self._is_running:
                    break

                if message["type"] != "message":
                    continue

                channel = message["channel"]
                data = json.loads(message["data"])

                await self._handle_message(channel, data)

        except asyncio.CancelledError:
            pass
        finally:
            await pubsub.unsubscribe()

    async def _handle_message(self, channel: str, data: dict) -> None:
        """
        Redis 메시지 처리

        Args:
            channel: 채널 이름
            data: 메시지 데이터
        """
        if channel == self.CHANNELS["wake_word"]:
            await self.handle_wake_word()

        elif channel == self.CHANNELS["stt_result"]:
            text = data.get("text", "")
            if text:
                await self.handle_stt_result(text)

        elif channel == self.CHANNELS["barge_in"]:
            await self.handle_barge_in()

        elif channel == self.CHANNELS["tts_complete"]:
            await self.handle_speaking_complete()

    async def stop(self) -> None:
        """오케스트레이터 중지"""
        self._is_running = False

        if self._listening_task:
            self._listening_task.cancel()

        if self._processing_task:
            self._processing_task.cancel()

        if self.redis:
            await self.redis.aclose()

    def get_status(self) -> dict:
        """현재 상태 정보 반환"""
        return {
            "state": self.state_machine.current_state.name,
            "state_info": self.state_machine.get_state_info(),
            "environment": self.environment,
            "is_running": self._is_running
        }
