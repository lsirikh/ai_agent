"""
Phase 36.3: 3초 무음 타임아웃 테스트

TDD Red Phase - G3 해결: 3초 무음 후 STT 호출
"""
import pytest
import sys
import os
import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

# 서비스 경로 추가
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../services/audio_gateway'))


class TestSpeechTimeoutFunction:
    """음성 타임아웃 함수 테스트"""

    def test_check_speech_timeout_function_exists(self):
        """
        check_speech_timeout 함수가 main에 존재해야 함
        """
        from app import main

        assert hasattr(main, 'check_speech_timeout'), "check_speech_timeout 함수가 없음"

    def test_speech_timeout_constant_exists(self):
        """
        SPEECH_TIMEOUT_SECONDS 상수가 정의되어 있어야 함
        """
        from app import main

        assert hasattr(main, 'SPEECH_TIMEOUT_SECONDS'), "SPEECH_TIMEOUT_SECONDS 상수가 없음"
        assert main.SPEECH_TIMEOUT_SECONDS == 3.0, "타임아웃이 3초가 아님"


class TestSpeechTimeoutLogic:
    """음성 타임아웃 로직 테스트"""

    def test_check_speech_timeout_returns_false_when_none(self):
        """
        마지막 음성 시간이 None이면 False 반환
        """
        from app import main

        # 음성 시간이 설정되지 않은 상태
        main._last_speech_time = None

        result = main.check_speech_timeout()

        assert result is False

    def test_check_speech_timeout_returns_false_when_recent(self):
        """
        최근 음성이 있으면 False 반환 (3초 미만)
        """
        from app import main

        # 방금 음성 감지
        main._last_speech_time = time.time()

        result = main.check_speech_timeout()

        assert result is False

    def test_check_speech_timeout_returns_true_after_3_seconds(self):
        """
        3초 이상 무음이면 True 반환
        """
        from app import main

        # 4초 전에 마지막 음성
        main._last_speech_time = time.time() - 4.0

        result = main.check_speech_timeout()

        assert result is True


class TestSpeechTimeoutTrigger:
    """음성 타임아웃 시 STT 트리거 테스트"""

    @pytest.mark.asyncio
    async def test_speech_timeout_triggers_on_speech_ended(self):
        """
        타임아웃 발생 시 on_speech_ended가 호출되어야 함
        """
        from app import main
        from app.audio_recorder import AudioRecorder
        import numpy as np

        # 녹음 중 상태로 설정
        main._listening_mode = True
        main._is_recording = True
        main._last_speech_time = time.time() - 4.0  # 4초 전
        main._current_session = {"session_id": "test-timeout-session"}

        # Mock AudioRecorder
        mock_recorder = MagicMock(spec=AudioRecorder)
        mock_recorder.stop.return_value = np.ones(16000, dtype=np.float32)
        mock_recorder.to_wav_bytes.return_value = b'RIFF...'
        original_recorder = main.audio_recorder
        main.audio_recorder = mock_recorder

        # Mock STT client
        mock_stt = AsyncMock()
        mock_stt.transcribe_and_publish.return_value = "테스트 텍스트"
        original_stt = main.stt_client
        main.stt_client = mock_stt

        try:
            with patch.object(main, '_logger') as mock_logger:
                mock_logger.info = AsyncMock()
                mock_logger.warning = AsyncMock()

                # process_speech_timeout 함수 존재 확인
                assert hasattr(main, 'process_speech_timeout'), "process_speech_timeout 함수가 없음"

                # 타임아웃 처리
                result = await main.process_speech_timeout()

                # on_speech_ended 효과 확인 (STT 호출)
                mock_stt.transcribe_and_publish.assert_called_once()

        finally:
            main.audio_recorder = original_recorder
            main.stt_client = original_stt
            main._listening_mode = False
            main._is_recording = False
            main._last_speech_time = None


class TestLastSpeechTimeTracking:
    """마지막 음성 시간 추적 테스트"""

    def test_last_speech_time_variable_exists(self):
        """
        _last_speech_time 변수가 존재해야 함
        """
        from app import main

        assert hasattr(main, '_last_speech_time'), "_last_speech_time 변수가 없음"

    @pytest.mark.asyncio
    async def test_speech_detection_updates_last_speech_time(self):
        """
        음성 감지 시 _last_speech_time이 업데이트되어야 함
        """
        from app import main

        main._listening_mode = True
        main._is_recording = True
        main._last_speech_time = None

        # VAD 결과 (음성 감지 중)
        vad_result = {
            "is_speech": True,
            "probability": 0.8,
            "speech_started": False,
            "speech_ended": False
        }

        with patch.object(main, '_logger') as mock_logger:
            mock_logger.info = AsyncMock()

            await main.handle_vad_result(vad_result, session_id="test-session")

            # _last_speech_time이 업데이트되어야 함
            assert main._last_speech_time is not None
            assert time.time() - main._last_speech_time < 1.0  # 1초 이내
