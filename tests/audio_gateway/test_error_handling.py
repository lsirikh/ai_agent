"""
Phase 35.8: 에러 핸들링 강화 테스트

TDD Red Phase - M2 해결: 오디오 검증 및 예외 처리 강화
"""
import pytest
import sys
import os
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import numpy as np

# 서비스 경로 추가
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../services/audio_gateway'))


class TestAudioValidation:
    """오디오 데이터 검증 테스트"""

    def test_validate_audio_size_function_exists(self):
        """
        validate_audio_size 함수가 main에 존재해야 함
        """
        from app import main

        assert hasattr(main, 'validate_audio_size'), "validate_audio_size 함수가 없음"

    def test_validate_audio_size_returns_false_for_empty(self):
        """
        빈 오디오 데이터에 대해 False 반환
        """
        from app.main import validate_audio_size

        empty_audio = np.array([], dtype=np.float32)
        result = validate_audio_size(empty_audio)

        assert result is False

    def test_validate_audio_size_returns_true_for_valid_size(self):
        """
        유효한 크기의 오디오에 대해 True 반환
        """
        from app.main import validate_audio_size

        valid_audio = np.ones(1600, dtype=np.float32)
        result = validate_audio_size(valid_audio)

        assert result is True

    def test_validate_audio_size_returns_false_for_too_large(self):
        """
        너무 큰 오디오에 대해 False 반환 (1초 이상 = 16000 samples)
        """
        from app.main import validate_audio_size

        # 10초분량 오디오 (너무 큼)
        large_audio = np.ones(160000, dtype=np.float32)
        result = validate_audio_size(large_audio)

        assert result is False


class TestAudioClipping:
    """오디오 클리핑 테스트"""

    def test_clip_audio_function_exists(self):
        """
        clip_audio 함수가 main에 존재해야 함
        """
        from app import main

        assert hasattr(main, 'clip_audio'), "clip_audio 함수가 없음"

    def test_clip_audio_clips_values_above_one(self):
        """
        1.0 초과 값을 1.0으로 클리핑
        """
        from app.main import clip_audio

        audio = np.array([0.5, 1.5, 2.0, -0.3], dtype=np.float32)
        result = clip_audio(audio)

        assert result[1] == 1.0
        assert result[2] == 1.0

    def test_clip_audio_clips_values_below_minus_one(self):
        """
        -1.0 미만 값을 -1.0으로 클리핑
        """
        from app.main import clip_audio

        audio = np.array([0.5, -1.5, -2.0, 0.3], dtype=np.float32)
        result = clip_audio(audio)

        assert result[1] == -1.0
        assert result[2] == -1.0

    def test_clip_audio_preserves_valid_values(self):
        """
        유효한 범위 값은 보존
        """
        from app.main import clip_audio

        audio = np.array([0.5, -0.5, 0.0, 0.9, -0.9], dtype=np.float32)
        result = clip_audio(audio)

        np.testing.assert_array_almost_equal(result, audio)


class TestWebSocketErrorHandling:
    """WebSocket 예외 처리 테스트"""

    def test_handle_websocket_error_function_exists(self):
        """
        handle_websocket_error 함수가 main에 존재해야 함
        """
        from app import main

        assert hasattr(main, 'handle_websocket_error'), "handle_websocket_error 함수가 없음"

    @pytest.mark.asyncio
    async def test_handle_websocket_error_logs_parse_error(self):
        """
        파싱 에러가 로깅되어야 함
        """
        from app.main import handle_websocket_error

        error = ValueError("Invalid audio format")

        with patch('app.main._logger') as mock_logger:
            mock_logger.error = AsyncMock()

            await handle_websocket_error(error, "audio_parse")

            mock_logger.error.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_websocket_error_returns_recoverable_for_parse_error(self):
        """
        파싱 에러는 복구 가능으로 표시
        """
        from app.main import handle_websocket_error

        error = ValueError("Invalid audio format")

        with patch('app.main._logger') as mock_logger:
            mock_logger.error = AsyncMock()

            result = await handle_websocket_error(error, "audio_parse")

            assert result["recoverable"] is True


class TestRedisErrorHandling:
    """Redis 연결 에러 처리 테스트"""

    @pytest.mark.asyncio
    async def test_handle_redis_error_function_exists(self):
        """
        handle_redis_error 함수가 main에 존재해야 함
        """
        from app import main

        assert hasattr(main, 'handle_redis_error'), "handle_redis_error 함수가 없음"

    @pytest.mark.asyncio
    async def test_handle_redis_error_logs_connection_error(self):
        """
        Redis 연결 에러가 로깅되어야 함
        """
        from app.main import handle_redis_error
        import redis.asyncio

        error = redis.asyncio.ConnectionError("Connection refused")

        with patch('app.main._logger') as mock_logger:
            mock_logger.error = AsyncMock()

            await handle_redis_error(error)

            mock_logger.error.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_redis_error_sets_client_none_on_critical(self):
        """
        심각한 에러 시 Redis 클라이언트를 None으로 설정
        """
        from app import main
        from app.main import handle_redis_error
        import redis.asyncio

        error = redis.asyncio.ConnectionError("Connection refused")

        original_client = main.redis_client
        main.redis_client = MagicMock()

        try:
            with patch('app.main._logger') as mock_logger:
                mock_logger.error = AsyncMock()

                await handle_redis_error(error, critical=True)

                assert main.redis_client is None
        finally:
            main.redis_client = original_client

