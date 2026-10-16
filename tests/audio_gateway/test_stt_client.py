"""
Phase 35.7.2: STT 클라이언트 테스트

TDD Red Phase - H2 해결: STT 서비스 호출 클라이언트
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import sys
import os
import asyncio

# 서비스 경로 추가
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../services/audio_gateway'))


class TestSTTClientClass:
    """STTClient 클래스 존재 테스트"""

    def test_stt_client_class_exists(self):
        """
        STTClient 클래스가 stt_client 모듈에 존재해야 함
        """
        from app.stt_client import STTClient

        assert STTClient is not None

    def test_stt_client_init_with_url(self):
        """
        STTClient가 stt_url 파라미터로 초기화되어야 함
        """
        from app.stt_client import STTClient

        client = STTClient(stt_url="http://localhost:11003")

        assert client.stt_url == "http://localhost:11003"


class TestSTTClientTranscribe:
    """STTClient 음성 인식 테스트"""

    @pytest.mark.asyncio
    async def test_stt_client_transcribe_async_method_exists(self):
        """
        transcribe_async 비동기 메서드가 존재해야 함
        """
        from app.stt_client import STTClient

        client = STTClient()

        assert hasattr(client, 'transcribe_async')
        assert asyncio.iscoroutinefunction(client.transcribe_async)

    @pytest.mark.asyncio
    async def test_stt_client_sends_wav_to_stt_service(self):
        """
        transcribe_async가 WAV 데이터를 STT 서비스로 전송해야 함
        """
        from app.stt_client import STTClient

        client = STTClient(stt_url="http://localhost:11003")

        # Mock HTTP 클라이언트
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"text": "hello world"}

        with patch.object(client, '_http_client') as mock_client:
            mock_client.post = AsyncMock(return_value=mock_response)

            wav_bytes = b'RIFF....WAVE'  # 간단한 WAV mock
            result = await client.transcribe_async(wav_bytes)

            # POST 호출 확인
            mock_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_stt_client_returns_transcription_text(self):
        """
        transcribe_async가 텍스트 결과를 반환해야 함
        """
        from app.stt_client import STTClient

        client = STTClient()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"text": "hello world"}

        with patch.object(client, '_http_client') as mock_client:
            mock_client.post = AsyncMock(return_value=mock_response)

            wav_bytes = b'RIFF....WAVE'
            result = await client.transcribe_async(wav_bytes)

            assert result == "hello world"


class TestSTTClientRedisPublish:
    """STTClient Redis 발행 테스트"""

    @pytest.mark.asyncio
    async def test_stt_client_publishes_result_to_redis(self):
        """
        transcribe_and_publish가 결과를 Redis로 발행해야 함
        """
        from app.stt_client import STTClient

        mock_redis = AsyncMock()
        client = STTClient(redis_client=mock_redis)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"text": "hello world"}

        with patch.object(client, '_http_client') as mock_client:
            mock_client.post = AsyncMock(return_value=mock_response)

            wav_bytes = b'RIFF....WAVE'
            await client.transcribe_and_publish(wav_bytes, session_id="test-session")

            # Redis publish 호출 확인
            mock_redis.publish.assert_called_once()


class TestSTTClientErrorHandling:
    """STTClient 에러 처리 테스트"""

    @pytest.mark.asyncio
    async def test_stt_client_handles_timeout(self):
        """
        STT 서비스 타임아웃 시 None을 반환해야 함
        """
        from app.stt_client import STTClient
        import httpx

        client = STTClient(timeout=1.0)

        with patch.object(client, '_http_client') as mock_client:
            mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("timeout"))

            wav_bytes = b'RIFF....WAVE'
            result = await client.transcribe_async(wav_bytes)

            assert result is None

    @pytest.mark.asyncio
    async def test_stt_client_handles_connection_error(self):
        """
        STT 서비스 연결 실패 시 None을 반환해야 함
        """
        from app.stt_client import STTClient
        import httpx

        client = STTClient()

        with patch.object(client, '_http_client') as mock_client:
            mock_client.post = AsyncMock(side_effect=httpx.ConnectError("connection refused"))

            wav_bytes = b'RIFF....WAVE'
            result = await client.transcribe_async(wav_bytes)

            assert result is None
