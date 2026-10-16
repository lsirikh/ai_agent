"""
Phase 35.7.3: WebSocket STT 호출 통합 테스트

TDD Red Phase - H2 해결: speech_ended 시 STT 자동 호출
"""
import pytest
import sys
import os
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import numpy as np

# 서비스 경로 추가
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../services/audio_gateway'))


class TestWebSocketSTTRecording:
    """WebSocket에서 음성 녹음 시작 테스트"""

    def test_websocket_has_audio_recorder_instance(self):
        """
        main.py에 AudioRecorder 인스턴스가 존재해야 함
        """
        from app import main

        assert hasattr(main, 'audio_recorder'), "audio_recorder 인스턴스가 main에 없음"

    def test_audio_recorder_is_audio_recorder_class(self):
        """
        audio_recorder가 AudioRecorder 클래스의 인스턴스여야 함
        """
        from app import main
        from app.audio_recorder import AudioRecorder

        assert isinstance(main.audio_recorder, AudioRecorder)


class TestSpeechStartedRecording:
    """speech_started 이벤트에서 녹음 시작 테스트"""

    @pytest.mark.asyncio
    async def test_speech_started_calls_recorder_start(self):
        """
        VAD에서 speech_started 이벤트 발생 시 AudioRecorder.start() 호출
        """
        from app import main
        from app.audio_recorder import AudioRecorder

        # Mock AudioRecorder
        mock_recorder = MagicMock(spec=AudioRecorder)
        original_recorder = main.audio_recorder
        main.audio_recorder = mock_recorder

        try:
            # speech_started 이벤트 시뮬레이션
            await main.on_speech_started()

            mock_recorder.start.assert_called_once()
        finally:
            main.audio_recorder = original_recorder


class TestSpeechEndedSTTCall:
    """speech_ended 이벤트에서 STT 호출 테스트"""

    @pytest.mark.asyncio
    async def test_speech_ended_stops_recording(self):
        """
        VAD에서 speech_ended 이벤트 발생 시 AudioRecorder.stop() 호출
        """
        from app import main
        from app.audio_recorder import AudioRecorder

        # Mock AudioRecorder
        mock_recorder = MagicMock(spec=AudioRecorder)
        mock_recorder.stop.return_value = np.ones(16000, dtype=np.float32)
        mock_recorder.to_wav_bytes.return_value = b'RIFF...'
        original_recorder = main.audio_recorder
        main.audio_recorder = mock_recorder

        try:
            # speech_ended 이벤트 시뮬레이션
            with patch.object(main, 'stt_client', AsyncMock()) as mock_stt:
                await main.on_speech_ended(session_id="test-session")

            mock_recorder.stop.assert_called_once()
        finally:
            main.audio_recorder = original_recorder

    @pytest.mark.asyncio
    async def test_speech_ended_calls_stt_transcribe(self):
        """
        speech_ended 시 STT 클라이언트의 transcribe_and_publish 호출
        """
        from app import main
        from app.audio_recorder import AudioRecorder

        # Mock AudioRecorder
        mock_recorder = MagicMock(spec=AudioRecorder)
        audio_data = np.ones(16000, dtype=np.float32)
        wav_bytes = b'RIFF...'
        mock_recorder.stop.return_value = audio_data
        mock_recorder.to_wav_bytes.return_value = wav_bytes
        original_recorder = main.audio_recorder
        main.audio_recorder = mock_recorder

        # Mock STT Client
        mock_stt = AsyncMock()
        mock_stt.transcribe_and_publish.return_value = "테스트 텍스트"
        original_stt = getattr(main, 'stt_client', None)
        main.stt_client = mock_stt

        try:
            await main.on_speech_ended(session_id="test-session")

            mock_stt.transcribe_and_publish.assert_called_once()
            # WAV 바이트와 세션 ID 전달 확인
            call_args = mock_stt.transcribe_and_publish.call_args
            assert call_args[0][0] == wav_bytes or call_args[1].get('wav_bytes') == wav_bytes
        finally:
            main.audio_recorder = original_recorder
            if original_stt:
                main.stt_client = original_stt

    @pytest.mark.asyncio
    async def test_speech_ended_converts_audio_to_wav(self):
        """
        speech_ended 시 오디오 데이터를 WAV로 변환해야 함
        """
        from app import main
        from app.audio_recorder import AudioRecorder

        # Mock AudioRecorder
        mock_recorder = MagicMock(spec=AudioRecorder)
        audio_data = np.ones(16000, dtype=np.float32)
        mock_recorder.stop.return_value = audio_data
        mock_recorder.to_wav_bytes.return_value = b'RIFF...'
        original_recorder = main.audio_recorder
        main.audio_recorder = mock_recorder

        # Mock STT Client
        mock_stt = AsyncMock()
        original_stt = getattr(main, 'stt_client', None)
        main.stt_client = mock_stt

        try:
            await main.on_speech_ended(session_id="test-session")

            # to_wav_bytes가 stop()에서 반환된 데이터로 호출됨
            mock_recorder.to_wav_bytes.assert_called_once()
            call_args = mock_recorder.to_wav_bytes.call_args[0][0]
            assert np.array_equal(call_args, audio_data)
        finally:
            main.audio_recorder = original_recorder
            if original_stt:
                main.stt_client = original_stt


class TestSTTResultPublish:
    """STT 결과 Redis 발행 테스트"""

    @pytest.mark.asyncio
    async def test_stt_result_published_with_session_id(self):
        """
        STT 결과가 세션 ID와 함께 발행되어야 함
        """
        from app import main

        # Mock AudioRecorder
        mock_recorder = MagicMock()
        mock_recorder.stop.return_value = np.ones(16000, dtype=np.float32)
        mock_recorder.to_wav_bytes.return_value = b'RIFF...'
        original_recorder = main.audio_recorder
        main.audio_recorder = mock_recorder

        # Mock STT Client
        mock_stt = AsyncMock()
        mock_stt.transcribe_and_publish.return_value = "안녕하세요"
        original_stt = getattr(main, 'stt_client', None)
        main.stt_client = mock_stt

        try:
            session_id = "session-12345"
            await main.on_speech_ended(session_id=session_id)

            # 세션 ID가 전달되었는지 확인
            call_args = mock_stt.transcribe_and_publish.call_args
            assert session_id in str(call_args)
        finally:
            main.audio_recorder = original_recorder
            if original_stt:
                main.stt_client = original_stt


class TestSTTClientInstance:
    """STT 클라이언트 인스턴스 테스트"""

    def test_main_has_stt_client_instance(self):
        """
        main.py에 stt_client 인스턴스가 존재해야 함
        """
        from app import main

        assert hasattr(main, 'stt_client'), "stt_client 인스턴스가 main에 없음"

    def test_stt_client_is_stt_client_class(self):
        """
        stt_client가 STTClient 클래스의 인스턴스여야 함
        """
        from app import main
        from app.stt_client import STTClient

        assert isinstance(main.stt_client, STTClient)

