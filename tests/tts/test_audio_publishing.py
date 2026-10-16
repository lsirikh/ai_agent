"""
Phase 36.5: TTS 오디오 스트림 발행 테스트

TDD Red Phase - G5 해결: TTS 서비스에서 오디오 스트림 Redis 발행
"""
import pytest
import sys
import os
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import json
import numpy as np

# 서비스 경로 추가
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../services/tts'))


class TestTTSAudioPublishing:
    """TTS 오디오 Redis 발행 테스트"""

    def test_tts_audio_channel_defined(self):
        """
        TTS 오디오 채널 상수가 정의되어 있어야 함
        """
        from app import redis_subscriber

        assert hasattr(redis_subscriber, 'TTS_AUDIO_CHANNEL'), "TTS_AUDIO_CHANNEL 상수가 없음"
        assert redis_subscriber.TTS_AUDIO_CHANNEL == "edgevoice:tts:audio"

    @pytest.mark.asyncio
    async def test_tts_publishes_audio_to_redis(self):
        """
        TTS 합성 후 오디오 데이터가 Redis로 발행되어야 함
        """
        from app.redis_subscriber import TTSRedisSubscriber

        # Mock synthesizer
        mock_synthesizer = MagicMock()
        mock_synthesizer.synthesize.return_value = np.ones(16000, dtype=np.float32).tobytes()

        subscriber = TTSRedisSubscriber(synthesizer=mock_synthesizer)

        # Mock Redis client
        mock_redis = MagicMock()
        mock_redis.publish = AsyncMock()
        subscriber.redis_client = mock_redis

        # Mock logger - 모든 메서드를 AsyncMock으로 설정
        mock_logger = MagicMock()
        mock_logger.info = AsyncMock()
        mock_logger.warning = AsyncMock()
        mock_logger.error = AsyncMock()
        mock_logger.debug = AsyncMock()
        subscriber._logger = mock_logger

        # TTS 요청 처리
        request_data = json.dumps({
            "session_id": "test-session",
            "text": "안녕하세요",
            "voice": "af_heart"
        })

        await subscriber._handle_message(request_data)

        # 오디오 발행 확인
        # edgevoice:tts:audio 채널로 발행되어야 함
        publish_calls = mock_redis.publish.call_args_list
        audio_published = any(
            "edgevoice:tts:audio" in str(call)
            for call in publish_calls
        )

        assert audio_published, "TTS 오디오가 Redis로 발행되지 않음"


class TestTTSAudioChunkSize:
    """TTS 오디오 청크 크기 테스트"""

    @pytest.mark.asyncio
    async def test_tts_audio_chunks_correct_size(self):
        """
        TTS 오디오가 적절한 청크 크기로 분할되어야 함

        AEC에서 처리 가능한 크기로 분할 (100ms = 1600 samples @ 16kHz)
        """
        from app import redis_subscriber

        # CHUNK_SIZE 상수 확인
        assert hasattr(redis_subscriber, 'TTS_CHUNK_SIZE'), "TTS_CHUNK_SIZE 상수가 없음"
        assert redis_subscriber.TTS_CHUNK_SIZE == 1600, "청크 크기가 1600 samples가 아님"


class TestTTSStateEvents:
    """TTS 상태 이벤트 발행 테스트"""

    @pytest.mark.asyncio
    async def test_tts_publishes_started_event(self):
        """
        TTS 시작 시 edgevoice:tts:state 채널에 tts_started 이벤트 발행
        """
        from app.redis_subscriber import TTSRedisSubscriber

        # Mock synthesizer
        mock_synthesizer = MagicMock()
        mock_synthesizer.synthesize.return_value = np.ones(16000, dtype=np.float32).tobytes()

        subscriber = TTSRedisSubscriber(synthesizer=mock_synthesizer)

        # Mock Redis client
        mock_redis = MagicMock()
        mock_redis.publish = AsyncMock()
        subscriber.redis_client = mock_redis

        # Mock logger - 모든 메서드를 AsyncMock으로 설정
        mock_logger = MagicMock()
        mock_logger.info = AsyncMock()
        mock_logger.warning = AsyncMock()
        mock_logger.error = AsyncMock()
        mock_logger.debug = AsyncMock()
        subscriber._logger = mock_logger

        # TTS 요청 처리
        request_data = json.dumps({
            "session_id": "test-session",
            "text": "안녕하세요",
            "voice": "af_heart"
        })

        await subscriber._handle_message(request_data)

        # tts_started 이벤트 발행 확인
        publish_calls = mock_redis.publish.call_args_list
        started_published = any(
            "tts_started" in str(call) and "edgevoice:tts:state" in str(call)
            for call in publish_calls
        )

        assert started_published, "tts_started 이벤트가 발행되지 않음"

    @pytest.mark.asyncio
    async def test_tts_publishes_complete_event(self):
        """
        TTS 완료 시 edgevoice:tts:state 채널에 tts_complete 이벤트 발행
        """
        from app.redis_subscriber import TTSRedisSubscriber

        # Mock synthesizer
        mock_synthesizer = MagicMock()
        mock_synthesizer.synthesize.return_value = np.ones(16000, dtype=np.float32).tobytes()

        subscriber = TTSRedisSubscriber(synthesizer=mock_synthesizer)

        # Mock Redis client
        mock_redis = MagicMock()
        mock_redis.publish = AsyncMock()
        subscriber.redis_client = mock_redis

        # Mock logger - 모든 메서드를 AsyncMock으로 설정
        mock_logger = MagicMock()
        mock_logger.info = AsyncMock()
        mock_logger.warning = AsyncMock()
        mock_logger.error = AsyncMock()
        mock_logger.debug = AsyncMock()
        subscriber._logger = mock_logger

        # TTS 요청 처리
        request_data = json.dumps({
            "session_id": "test-session",
            "text": "안녕하세요",
            "voice": "af_heart"
        })

        await subscriber._handle_message(request_data)

        # tts_complete 이벤트 발행 확인
        publish_calls = mock_redis.publish.call_args_list
        complete_published = any(
            "tts_complete" in str(call) and "edgevoice:tts:state" in str(call)
            for call in publish_calls
        )

        assert complete_published, "tts_complete 이벤트가 발행되지 않음"
