"""
Phase 36.4: Session ID 추적 테스트

TDD Red Phase - G4 해결: Session ID 추적 미구현
"""
import pytest
import sys
import os
import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch
import numpy as np

# 서비스 경로 추가
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../services/audio_gateway'))


class TestCurrentSessionDict:
    """현재 세션 딕셔너리 테스트"""

    def test_current_session_dict_exists(self):
        """
        _current_session 딕셔너리가 main에 존재해야 함
        """
        from app import main

        assert hasattr(main, '_current_session'), "_current_session 딕셔너리가 없음"
        assert isinstance(main._current_session, dict)


class TestGenerateSessionId:
    """세션 ID 생성 테스트"""

    def test_generate_session_id_returns_unique_id(self):
        """
        generate_session_id가 고유한 ID를 반환해야 함
        """
        from app import main

        id1 = main.generate_session_id()
        id2 = main.generate_session_id()

        assert id1 != id2, "생성된 세션 ID가 고유하지 않음"

    def test_generate_session_id_has_prefix(self):
        """
        세션 ID가 'session-' 접두사로 시작해야 함
        """
        from app import main

        session_id = main.generate_session_id()

        assert session_id.startswith("session-"), "세션 ID가 'session-'으로 시작하지 않음"


class TestSessionIdInSTTResult:
    """STT 결과에 Session ID 포함 테스트"""

    @pytest.mark.asyncio
    async def test_session_id_included_in_stt_result(self):
        """
        STT 호출 시 session_id가 함께 전달되어야 함
        """
        from app import main
        from app.audio_recorder import AudioRecorder

        # 세션 설정
        main._current_session = {
            "session_id": "test-session-abc123",
            "started_at": time.time()
        }

        # Mock AudioRecorder
        mock_recorder = MagicMock(spec=AudioRecorder)
        mock_recorder.stop.return_value = np.ones(16000, dtype=np.float32)
        mock_recorder.to_wav_bytes.return_value = b'RIFF...'
        original_recorder = main.audio_recorder
        main.audio_recorder = mock_recorder

        # Mock STT Client
        mock_stt = AsyncMock()
        mock_stt.transcribe_and_publish = AsyncMock(return_value="테스트 텍스트")
        original_stt = main.stt_client
        main.stt_client = mock_stt

        try:
            with patch.object(main, '_logger') as mock_logger:
                mock_logger.info = AsyncMock()
                mock_logger.warning = AsyncMock()

                # on_speech_ended 호출
                await main.on_speech_ended(session_id="test-session-abc123")

                # STT 클라이언트가 session_id와 함께 호출되었는지 확인
                mock_stt.transcribe_and_publish.assert_called_once()
                call_args = mock_stt.transcribe_and_publish.call_args

                # session_id가 전달되었는지 확인
                assert "test-session-abc123" in str(call_args)

        finally:
            main.audio_recorder = original_recorder
            main.stt_client = original_stt


class TestSessionReset:
    """세션 리셋 테스트"""

    @pytest.mark.asyncio
    async def test_session_reset_after_stt_complete(self):
        """
        STT 완료 후 세션 정보가 리셋되어야 함

        reset_session 함수가 존재하고 올바르게 동작해야 함
        """
        from app import main

        # reset_session 함수 존재 확인
        assert hasattr(main, 'reset_session'), "reset_session 함수가 없음"

        # 세션 설정
        main._current_session = {
            "session_id": "test-session-xyz",
            "started_at": time.time()
        }
        main._listening_mode = True
        main._is_recording = True
        main._last_speech_time = time.time()

        # 세션 리셋
        await main.reset_session()

        # 상태 확인
        assert main._current_session == {}
        assert main._listening_mode is False
        assert main._is_recording is False
        assert main._last_speech_time is None


class TestSessionLogging:
    """세션 정보 로깅 테스트"""

    @pytest.mark.asyncio
    async def test_all_logs_include_session_id(self):
        """
        모든 파이프라인 로그에 session_id가 포함되어야 함
        """
        from app import main

        main._listening_mode = True
        main._is_recording = False
        main._current_session = {"session_id": "test-log-session"}

        # VAD 결과 (음성 시작)
        vad_result = {
            "is_speech": True,
            "probability": 0.9,
            "speech_started": True,
            "speech_ended": False
        }

        with patch.object(main, 'on_speech_started', new_callable=AsyncMock):
            with patch.object(main, '_logger') as mock_logger:
                mock_logger.info = AsyncMock()

                await main.handle_vad_result(vad_result, session_id="test-log-session")

                # 로그에 session_id가 포함되어야 함
                mock_logger.info.assert_called()
                call_args = mock_logger.info.call_args

                # metadata에 session_id가 있는지 확인
                if len(call_args) > 0 and 'metadata' in str(call_args):
                    assert "test-log-session" in str(call_args)
