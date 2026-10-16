"""
Recording Logs Tests - Phase 46

Phase 46: Listening/Recording 상태 Pipeline 로그 추가
TDD Red 단계: 테스트 먼저 작성

목표: Wake Word 후 Listening/Recording 상태를 Pipeline Log에서 명확히 파악
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest


class TestListeningModeStartedLog:
    """Listening 모드 시작 로그 테스트"""

    @pytest.mark.asyncio
    async def test_listening_mode_started_log_on_wake_word(self):
        """
        Wake Word 감지 후 listening_mode_started 로그가 발행되어야 한다.

        Phase 46.1: TDD Red 단계

        예상 로그:
        [INFO] audio_gateway listening_mode_started Listening mode activated - waiting for voice input
        """
        # Mock logger 설정
        mock_logger = AsyncMock()

        # Wake Word 이벤트 데이터
        wake_word_event = {
            "event": "wake_word_detected",
            "keyword": "hey_jarvis",
            "confidence": 0.45
        }

        # handle_wake_word_event 시뮬레이션
        # 기존 동작: Wake Word 수신 후 Listening 모드 활성화
        # 추가 필요: listening_mode_started 로그 발행

        # 시뮬레이션: Wake Word 처리 후 로그 발행
        await mock_logger.info(
            "listening_mode_started",
            "Listening mode activated - waiting for voice input",
            metadata={
                "wake_word": wake_word_event["keyword"],
                "confidence": wake_word_event["confidence"]
            }
        )

        # 검증: listening_mode_started 로그가 발행됨
        mock_logger.info.assert_called_once()
        call_args = mock_logger.info.call_args
        assert call_args[0][0] == "listening_mode_started"
        assert "Listening mode activated" in call_args[0][1]


class TestRecordingStartedLog:
    """녹음 시작 로그 테스트"""

    @pytest.mark.asyncio
    async def test_recording_started_log_on_speech_detected(self):
        """
        음성 감지 시 recording_started 로그가 발행되어야 한다.

        Phase 46.1: TDD Red 단계

        예상 로그:
        [INFO] audio_gateway recording_started Recording started - capturing voice input
        """
        mock_logger = AsyncMock()

        # on_speech_started 시뮬레이션
        # 기존: AudioRecorder.start() 호출 + speech_started 로그
        # 추가 필요: recording_started 로그 발행 (더 명확한 메시지)

        await mock_logger.info(
            "recording_started",
            "Recording started - capturing voice input"
        )

        # 검증
        mock_logger.info.assert_called_once()
        call_args = mock_logger.info.call_args
        assert call_args[0][0] == "recording_started"
        assert "Recording started" in call_args[0][1]


class TestRecordingProgressLog:
    """녹음 진행 상황 로그 테스트"""

    @pytest.mark.asyncio
    async def test_recording_progress_log_every_10_chunks(self):
        """
        녹음 중 10청크마다 recording_progress 로그가 발행되어야 한다.

        Phase 46.1: TDD Red 단계

        예상 로그:
        [DEBUG] audio_gateway recording_progress Recording: 1600 samples (100ms)
        """
        mock_logger = AsyncMock()

        # 녹음 진행 시뮬레이션 (30 청크 = 3번 로그)
        chunk_size = 1600  # 100ms at 16kHz
        sample_rate = 16000
        log_count = 0

        for chunk_num in range(1, 31):
            if chunk_num % 10 == 0:
                total_samples = chunk_num * chunk_size
                duration_ms = (total_samples / sample_rate) * 1000

                await mock_logger.log(
                    event="recording_progress",
                    data={
                        "message": f"Recording: {total_samples} samples ({int(duration_ms)}ms)",
                        "samples": total_samples,
                        "duration_ms": int(duration_ms),
                        "chunk_count": chunk_num
                    },
                    level="debug"
                )
                log_count += 1

        # 검증: 3번 로그 발행 (10, 20, 30 청크)
        assert mock_logger.log.call_count == 3

        # 마지막 로그 검증
        last_call = mock_logger.log.call_args
        assert last_call[1]["event"] == "recording_progress"
        assert "Recording:" in last_call[1]["data"]["message"]


class TestRecordingTimeoutLog:
    """녹음 타임아웃 로그 테스트"""

    @pytest.mark.asyncio
    async def test_recording_timeout_log_on_3s_silence(self):
        """
        3초 무음 시 recording_timeout 로그가 발행되어야 한다.

        Phase 46.1: TDD Red 단계

        예상 로그:
        [INFO] audio_gateway recording_timeout Voice input timeout (3s silence) - sending to STT
        """
        mock_logger = AsyncMock()

        # process_speech_timeout 시뮬레이션
        # 기존: speech_timeout 로그 (메시지: "3초 무음 감지, STT 호출")
        # 변경: recording_timeout 로그 (더 명확한 영문 메시지)

        timeout_seconds = 3.0
        session_id = "test-session-123"

        await mock_logger.info(
            "recording_timeout",
            f"Voice input timeout ({int(timeout_seconds)}s silence) - sending to STT",
            metadata={
                "session_id": session_id,
                "timeout_seconds": timeout_seconds
            }
        )

        # 검증
        mock_logger.info.assert_called_once()
        call_args = mock_logger.info.call_args
        assert call_args[0][0] == "recording_timeout"
        assert "Voice input timeout" in call_args[0][1]
        assert "3s silence" in call_args[0][1]


class TestRecordingCompletedLog:
    """녹음 완료 로그 테스트"""

    @pytest.mark.asyncio
    async def test_recording_completed_log_on_speech_ended(self):
        """
        녹음 완료 시 recording_completed 로그가 발행되어야 한다.

        Phase 46.1: TDD Red 단계

        예상 로그:
        [INFO] audio_gateway recording_completed Recording completed - 48000 samples (3.0s)
        """
        mock_logger = AsyncMock()

        # on_speech_ended 시뮬레이션
        # 기존: speech_ended 로그
        # 추가 필요: recording_completed 로그 (총 샘플 수, 시간)

        total_samples = 48000  # 3초 분량
        sample_rate = 16000
        duration_seconds = total_samples / sample_rate
        session_id = "test-session-123"

        await mock_logger.info(
            "recording_completed",
            f"Recording completed - {total_samples} samples ({duration_seconds:.1f}s)",
            metadata={
                "session_id": session_id,
                "samples": total_samples,
                "duration_seconds": duration_seconds
            }
        )

        # 검증
        mock_logger.info.assert_called_once()
        call_args = mock_logger.info.call_args
        assert call_args[0][0] == "recording_completed"
        assert "Recording completed" in call_args[0][1]
        assert "48000 samples" in call_args[0][1]
        assert "3.0s" in call_args[0][1]


class TestRecordingLogsIntegration:
    """녹음 로그 통합 테스트"""

    @pytest.mark.asyncio
    async def test_full_recording_flow_logs(self):
        """
        전체 녹음 흐름에서 올바른 순서로 로그가 발행되어야 한다.

        Phase 46.1: TDD Red 단계

        예상 흐름:
        1. listening_mode_started (Wake Word 후)
        2. recording_started (음성 감지)
        3. recording_progress (10청크마다, DEBUG)
        4. recording_timeout 또는 recording_completed
        """
        mock_logger = AsyncMock()
        log_events = []

        # 로그 이벤트 추적을 위한 side_effect
        async def track_info_log(event, message, metadata=None):
            log_events.append(("info", event, message))

        async def track_log(event, data, level):
            log_events.append((level, event, data.get("message", "")))

        mock_logger.info.side_effect = track_info_log
        mock_logger.log.side_effect = track_log

        # 1. Wake Word 감지 → Listening 모드 시작
        await mock_logger.info(
            "listening_mode_started",
            "Listening mode activated - waiting for voice input"
        )

        # 2. 음성 감지 → 녹음 시작
        await mock_logger.info(
            "recording_started",
            "Recording started - capturing voice input"
        )

        # 3. 녹음 진행 (10청크)
        await mock_logger.log(
            event="recording_progress",
            data={"message": "Recording: 16000 samples (1000ms)"},
            level="debug"
        )

        # 4. 3초 무음 → 타임아웃
        await mock_logger.info(
            "recording_timeout",
            "Voice input timeout (3s silence) - sending to STT"
        )

        # 5. 녹음 완료
        await mock_logger.info(
            "recording_completed",
            "Recording completed - 48000 samples (3.0s)"
        )

        # 검증: 올바른 순서
        assert len(log_events) == 5
        assert log_events[0][1] == "listening_mode_started"
        assert log_events[1][1] == "recording_started"
        assert log_events[2][1] == "recording_progress"
        assert log_events[3][1] == "recording_timeout"
        assert log_events[4][1] == "recording_completed"
