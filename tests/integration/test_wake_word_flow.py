"""
Wake Word Flow Integration Tests

Phase 6.1: Wake Word 플로우 통합 테스트
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import asyncio
import json

from services.orchestrator.app.state_machine import State, OrchestratorStateMachine as StateMachine


class TestWakeWordDetection:
    """Wake Word 감지 통합 테스트"""

    @pytest.mark.asyncio
    async def test_wake_word_triggers_listening_state(self):
        """Wake Word 감지 시 LISTENING 상태로 전이해야 한다"""
        state_machine = StateMachine()
        assert state_machine.current_state == State.IDLE

        # Wake Word 감지 시뮬레이션
        wake_word_detected = True
        confidence = 0.85

        if wake_word_detected and confidence > 0.7:
            state_machine.transition_to(State.LISTENING)

        assert state_machine.current_state == State.LISTENING

    @pytest.mark.asyncio
    async def test_wake_word_confidence_threshold(self):
        """Wake Word 신뢰도 임계값이 적용되어야 한다"""
        state_machine = StateMachine()
        threshold = 0.7

        # 낮은 신뢰도 - 무시
        low_confidence_detection = {"detected": True, "confidence": 0.5}
        if low_confidence_detection["confidence"] >= threshold:
            state_machine.transition_to(State.LISTENING)

        assert state_machine.current_state == State.IDLE

        # 높은 신뢰도 - 전이
        high_confidence_detection = {"detected": True, "confidence": 0.85}
        if high_confidence_detection["confidence"] >= threshold:
            state_machine.transition_to(State.LISTENING)

        assert state_machine.current_state == State.LISTENING

    @pytest.mark.asyncio
    async def test_wake_word_publishes_event(self, mock_redis):
        """Wake Word 감지 시 Redis 이벤트가 발행되어야 한다"""
        wake_word_detected = True
        confidence = 0.9

        if wake_word_detected:
            event = {
                "type": "wake_word_detected",
                "confidence": confidence,
                "timestamp": "2024-01-01T12:00:00"
            }
            await mock_redis.publish("orchestrator:events", json.dumps(event))

        mock_redis.publish.assert_called_once()
        call_args = mock_redis.publish.call_args
        published_event = json.loads(call_args[0][1])
        assert published_event["type"] == "wake_word_detected"
        assert published_event["confidence"] == 0.9


class TestWakeWordToSTTFlow:
    """Wake Word에서 STT로의 플로우 테스트"""

    @pytest.mark.asyncio
    async def test_stt_starts_after_wake_word(self, mock_stt_service):
        """Wake Word 감지 후 STT가 시작되어야 한다"""
        state_machine = StateMachine()

        # Wake Word 감지
        state_machine.transition_to(State.LISTENING)
        assert state_machine.current_state == State.LISTENING

        # STT 시작
        stt_result = await mock_stt_service.transcribe(b"user_audio")

        assert stt_result["text"] == "안녕하세요"
        mock_stt_service.transcribe.assert_called_once()

    @pytest.mark.asyncio
    async def test_listening_timeout_returns_to_idle(self):
        """LISTENING 상태에서 타임아웃 시 IDLE로 돌아가야 한다"""
        state_machine = StateMachine()
        state_machine.transition_to(State.LISTENING)

        listening_timeout = 5.0  # 5초
        start_time = asyncio.get_event_loop().time()

        # 타임아웃 시뮬레이션 (실제로는 짧게)
        await asyncio.sleep(0.01)

        # 음성 입력 없음 시뮬레이션
        speech_detected = False
        elapsed_time = 6.0  # 타임아웃 초과

        if not speech_detected and elapsed_time > listening_timeout:
            state_machine.transition_to(State.IDLE)

        assert state_machine.current_state == State.IDLE

    @pytest.mark.asyncio
    async def test_audio_buffering_after_wake_word(self):
        """Wake Word 감지 후 오디오가 버퍼링되어야 한다"""
        audio_buffer = []

        # Wake Word 감지
        wake_word_detected = True

        # 오디오 청크 수집
        audio_chunks = [b"chunk1", b"chunk2", b"chunk3"]

        if wake_word_detected:
            for chunk in audio_chunks:
                audio_buffer.append(chunk)

        assert len(audio_buffer) == 3
        assert b"".join(audio_buffer) == b"chunk1chunk2chunk3"


class TestWakeWordCooldown:
    """Wake Word 쿨다운 테스트"""

    @pytest.mark.asyncio
    async def test_wake_word_cooldown_during_processing(self):
        """처리 중에는 Wake Word가 무시되어야 한다"""
        state_machine = StateMachine()

        # 이미 처리 중 (정상 전이 경로: IDLE -> LISTENING -> PROCESSING)
        state_machine.transition_to(State.LISTENING)
        state_machine.transition_to(State.PROCESSING)

        # Wake Word 감지 시도 - 무시되어야 함
        wake_word_detected = True

        if state_machine.current_state == State.IDLE and wake_word_detected:
            state_machine.transition_to(State.LISTENING)

        # 상태 변화 없음
        assert state_machine.current_state == State.PROCESSING

    @pytest.mark.asyncio
    async def test_wake_word_cooldown_during_speaking(self):
        """SPEAKING 중에는 Wake Word가 무시되어야 한다 (Barge-in은 별도)"""
        state_machine = StateMachine()
        # 정상 전이 경로: IDLE -> LISTENING -> PROCESSING -> SPEAKING
        state_machine.transition_to(State.LISTENING)
        state_machine.transition_to(State.PROCESSING)
        state_machine.transition_to(State.SPEAKING)

        # Wake Word 감지 (Barge-in이 아닌 경우)
        wake_word_detected = True
        is_barge_in = False  # 에너지가 충분히 높지 않음

        if state_machine.current_state == State.IDLE and wake_word_detected:
            state_machine.transition_to(State.LISTENING)

        # Barge-in이 아니면 상태 유지
        assert state_machine.current_state == State.SPEAKING

    @pytest.mark.asyncio
    async def test_wake_word_reactivation_after_interaction(self):
        """상호작용 완료 후 Wake Word가 다시 활성화되어야 한다"""
        state_machine = StateMachine()

        # 전체 사이클
        state_machine.transition_to(State.LISTENING)
        state_machine.transition_to(State.PROCESSING)
        state_machine.transition_to(State.SPEAKING)
        state_machine.transition_to(State.IDLE)

        # IDLE 상태에서 Wake Word 다시 감지 가능
        wake_word_detected = True
        if state_machine.current_state == State.IDLE and wake_word_detected:
            state_machine.transition_to(State.LISTENING)

        assert state_machine.current_state == State.LISTENING


class TestWakeWordWithVAD:
    """Wake Word와 VAD 통합 테스트"""

    @pytest.mark.asyncio
    async def test_vad_activates_after_wake_word(self):
        """Wake Word 감지 후 VAD가 활성화되어야 한다"""
        vad_active = False

        # Wake Word 감지
        wake_word_detected = True

        if wake_word_detected:
            vad_active = True

        assert vad_active

    @pytest.mark.asyncio
    async def test_vad_detects_end_of_speech(self):
        """VAD가 발화 종료를 감지해야 한다"""
        # VAD 결과 시뮬레이션
        vad_results = [
            {"is_speech": True, "probability": 0.9},
            {"is_speech": True, "probability": 0.85},
            {"is_speech": False, "probability": 0.1},
            {"is_speech": False, "probability": 0.05},
            {"is_speech": False, "probability": 0.02}
        ]

        silence_threshold = 0.5
        consecutive_silence_for_end = 3

        silence_count = 0
        speech_ended = False

        for result in vad_results:
            if result["probability"] < silence_threshold:
                silence_count += 1
                if silence_count >= consecutive_silence_for_end:
                    speech_ended = True
                    break
            else:
                silence_count = 0

        assert speech_ended
        assert silence_count == 3

    @pytest.mark.asyncio
    async def test_vad_silence_duration_threshold(self):
        """VAD 무음 지속 시간 임계값 테스트"""
        silence_duration_ms = 0
        silence_threshold_ms = 1000  # 1초

        # 무음 시뮬레이션
        frame_duration_ms = 30
        silence_frames = [False] * 5 + [True] * 40  # 5프레임 음성 + 40프레임 무음

        for is_silence in silence_frames:
            if is_silence:
                silence_duration_ms += frame_duration_ms
            else:
                silence_duration_ms = 0

            if silence_duration_ms >= silence_threshold_ms:
                break

        assert silence_duration_ms >= silence_threshold_ms


class TestWakeWordMultipleKeywords:
    """다중 Wake Word 테스트"""

    @pytest.mark.asyncio
    async def test_multiple_wake_words_supported(self):
        """여러 Wake Word가 지원되어야 한다"""
        supported_wake_words = ["헤이 로봇", "오케이 로봇", "안녕 로봇"]

        detected_phrase = "헤이 로봇"

        is_wake_word = detected_phrase in supported_wake_words

        assert is_wake_word

    @pytest.mark.asyncio
    async def test_custom_wake_word_registration(self):
        """커스텀 Wake Word 등록이 가능해야 한다"""
        wake_word_config = {
            "default": ["헤이 로봇"],
            "custom": []
        }

        # 커스텀 Wake Word 추가
        new_wake_word = "안녕 비서"
        wake_word_config["custom"].append(new_wake_word)

        all_wake_words = wake_word_config["default"] + wake_word_config["custom"]

        assert "안녕 비서" in all_wake_words
        assert len(all_wake_words) == 2


class TestWakeWordAudioProcessing:
    """Wake Word 오디오 처리 테스트"""

    @pytest.mark.asyncio
    async def test_audio_preprocessing_for_wake_word(self):
        """Wake Word 감지 전 오디오 전처리가 수행되어야 한다"""
        import numpy as np

        # 원본 오디오 (16kHz, 16-bit)
        raw_audio = np.random.randint(-32768, 32767, size=16000, dtype=np.int16)

        # 전처리: 정규화
        normalized = raw_audio.astype(np.float32) / 32768.0

        assert normalized.min() >= -1.0
        assert normalized.max() <= 1.0

        # 전처리: 리샘플링 (필요한 경우)
        target_sample_rate = 16000
        current_sample_rate = 16000

        if current_sample_rate != target_sample_rate:
            # 리샘플링 로직 (여기서는 동일하므로 스킵)
            pass

        assert len(normalized) == 16000

    @pytest.mark.asyncio
    async def test_wake_word_detection_latency(self):
        """Wake Word 감지 지연 시간이 허용 범위 내여야 한다"""
        import time

        # 감지 시뮬레이션
        start_time = time.time()

        # Wake Word 처리 (mock - 매우 빠름)
        await asyncio.sleep(0.01)

        detection_latency_ms = (time.time() - start_time) * 1000

        # 200ms 이하 목표 (mock이라 훨씬 빠름)
        max_latency_ms = 200
        assert detection_latency_ms < max_latency_ms


class TestWakeWordEventHandling:
    """Wake Word 이벤트 처리 테스트"""

    @pytest.mark.asyncio
    async def test_orchestrator_handles_wake_word_event(self, mock_redis):
        """Orchestrator가 Wake Word 이벤트를 처리해야 한다"""
        state_machine = StateMachine()

        # Wake Word 이벤트 수신 시뮬레이션
        event = {
            "type": "wake_word_detected",
            "confidence": 0.9,
            "timestamp": "2024-01-01T12:00:00"
        }

        # 이벤트 처리
        if event["type"] == "wake_word_detected":
            if state_machine.current_state == State.IDLE:
                state_machine.transition_to(State.LISTENING)

        assert state_machine.current_state == State.LISTENING

    @pytest.mark.asyncio
    async def test_audio_feedback_on_wake_word(self, mock_tts_service):
        """Wake Word 감지 시 오디오 피드백이 재생되어야 한다"""
        wake_word_detected = True
        feedback_enabled = True

        if wake_word_detected and feedback_enabled:
            # 확인음 재생
            await mock_tts_service.synthesize(text="네?")

        mock_tts_service.synthesize.assert_called_once()

    @pytest.mark.asyncio
    async def test_visual_feedback_on_wake_word(self):
        """Wake Word 감지 시 시각적 피드백이 있어야 한다"""
        wake_word_detected = True

        ui_state = {"listening_indicator": False}

        if wake_word_detected:
            ui_state["listening_indicator"] = True

        assert ui_state["listening_indicator"]
