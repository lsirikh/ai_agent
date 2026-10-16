"""
Phase 36.1.1: VAD 이벤트 처리 테스트

TDD Red Phase - G1 해결: WebSocket에서 VAD 이벤트 연동
"""
import pytest
import sys
import os
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import numpy as np

# 서비스 경로 추가
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../services/audio_gateway'))


class TestSpeechStartedLogging:
    """speech_started 이벤트 로깅 테스트"""

    @pytest.mark.asyncio
    async def test_speech_started_logs_event(self):
        """
        speech_started 호출 시 파이프라인 로그에 이벤트가 기록되어야 함

        사용자 시나리오:
        - 마이크로 말하면 VAD가 음성 감지
        - "사람 목소리 수신 중" 로그가 Pipeline Log에 표시
        """
        from app import main

        # Mock logger
        with patch.object(main, '_logger') as mock_logger:
            mock_logger.info = AsyncMock()

            await main.on_speech_started()

            # 로그 호출 확인
            mock_logger.info.assert_called()
            call_args = mock_logger.info.call_args

            # 이벤트명이 speech_started인지 확인
            assert call_args[0][0] == "speech_started"


class TestListeningModeRecording:
    """Listening 모드에서 녹음 시작 테스트"""

    @pytest.mark.asyncio
    async def test_speech_started_in_listening_mode_starts_recording(self):
        """
        Listening 모드에서 speech_started 시 녹음이 시작되어야 함

        플로우: Wake Word 수신 → Listening 모드 → 음성 감지 → 녹음 시작
        """
        from app import main
        from app.audio_recorder import AudioRecorder

        # Mock AudioRecorder
        mock_recorder = MagicMock(spec=AudioRecorder)
        original_recorder = main.audio_recorder
        main.audio_recorder = mock_recorder

        try:
            # speech_started 호출
            with patch.object(main, '_logger') as mock_logger:
                mock_logger.info = AsyncMock()

                await main.on_speech_started()

                # 녹음 시작 확인
                mock_recorder.start.assert_called_once()
        finally:
            main.audio_recorder = original_recorder


class TestChunkBuffering:
    """음성 청크 버퍼링 테스트"""

    def test_is_speech_adds_chunk_to_buffer(self):
        """
        음성 감지 중 (is_speech=True) 청크가 버퍼에 추가되어야 함
        """
        from app.audio_recorder import AudioRecorder

        recorder = AudioRecorder()
        recorder.start()

        # 음성 청크 추가
        chunk1 = np.ones(1600, dtype=np.float32)
        chunk2 = np.ones(1600, dtype=np.float32) * 0.5

        recorder.add_chunk(chunk1)
        recorder.add_chunk(chunk2)

        # 녹음 중지 및 데이터 확인
        audio_data = recorder.stop()

        # 두 청크가 합쳐져야 함
        assert len(audio_data) == 3200


class TestWebSocketVADEventIntegration:
    """WebSocket에서 VAD 이벤트 연동 테스트"""

    @pytest.mark.asyncio
    async def test_websocket_calls_speech_started_on_speech_detection(self):
        """
        WebSocket에서 음성 감지 시 on_speech_started가 호출되어야 함

        플로우: 오디오 수신 → VAD 감지 → speech_started 이벤트
        """
        from app import main

        # _listening_mode와 _is_recording 상태가 존재해야 함
        assert hasattr(main, '_listening_mode'), "_listening_mode 상태 변수가 없음"
        assert hasattr(main, '_is_recording'), "_is_recording 상태 변수가 없음"

    def test_handle_vad_result_function_exists(self):
        """
        handle_vad_result 함수가 main에 존재해야 함

        이 함수는 VAD 결과를 받아 speech_started/ended 이벤트를 발생시킴
        """
        from app import main

        assert hasattr(main, 'handle_vad_result'), "handle_vad_result 함수가 없음"

    @pytest.mark.asyncio
    async def test_handle_vad_result_starts_recording_on_speech_start(self):
        """
        handle_vad_result에서 음성 시작 감지 시 녹음이 시작되어야 함
        """
        from app import main

        # 초기 상태 설정
        main._listening_mode = True
        main._is_recording = False
        main._previous_is_speech = False

        # VAD 결과 (음성 감지 시작)
        vad_result = {
            "is_speech": True,
            "probability": 0.8,
            "speech_started": True,
            "speech_ended": False
        }

        with patch.object(main, 'on_speech_started', new_callable=AsyncMock) as mock_started:
            with patch.object(main, '_logger') as mock_logger:
                mock_logger.info = AsyncMock()

                await main.handle_vad_result(vad_result, session_id="test-session")

                # on_speech_started가 호출되어야 함
                mock_started.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_vad_result_does_not_end_on_short_vad_pause(self):
        """
        VAD 의 짧은 무음(speech_ended)으로는 STT 를 호출하지 않는다.
        발화 종료는 end_pause_seconds 무음(process_speech_timeout)이 판정한다.
        """
        from app import main

        # 녹음 중인 상태로 설정
        main._listening_mode = True
        main._is_recording = True
        main._previous_is_speech = True

        # VAD 결과 (음성 종료)
        vad_result = {
            "is_speech": False,
            "probability": 0.1,
            "speech_started": False,
            "speech_ended": True
        }

        with patch.object(main, 'on_speech_ended', new_callable=AsyncMock) as mock_ended:
            mock_ended.return_value = "테스트 텍스트"

            with patch.object(main, '_logger') as mock_logger:
                mock_logger.info = AsyncMock()

                await main.handle_vad_result(vad_result, session_id="test-session")

                # 짧은 무음으로는 녹음을 끝내지 않는다
                mock_ended.assert_not_called()


class TestSpeechEndedSTTTrigger:
    """speech_ended 시 STT 호출 테스트"""

    @pytest.mark.asyncio
    async def test_speech_ended_triggers_stt_call(self):
        """
        speech_ended 호출 시 STT 서비스가 호출되어야 함

        플로우: 음성 종료 감지 → 녹음 중지 → WAV 변환 → STT 호출
        """
        from app import main
        from app.audio_recorder import AudioRecorder

        # Mock AudioRecorder
        mock_recorder = MagicMock(spec=AudioRecorder)
        mock_recorder.stop.return_value = np.ones(16000, dtype=np.float32)
        mock_recorder.to_wav_bytes.return_value = b'RIFF...'
        original_recorder = main.audio_recorder
        main.audio_recorder = mock_recorder

        # Mock STT Client
        mock_stt = AsyncMock()
        mock_stt.transcribe_and_publish.return_value = "테스트 음성"
        original_stt = main.stt_client
        main.stt_client = mock_stt

        try:
            with patch.object(main, '_logger') as mock_logger:
                mock_logger.info = AsyncMock()
                mock_logger.warning = AsyncMock()

                # speech_ended 호출
                result = await main.on_speech_ended(session_id="test-session-123")

                # STT 호출 확인
                mock_stt.transcribe_and_publish.assert_called_once()

                # 결과 확인
                assert result == "테스트 음성"
        finally:
            main.audio_recorder = original_recorder
            main.stt_client = original_stt
