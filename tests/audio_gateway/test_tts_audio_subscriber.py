"""
Phase 35.6.1: TTS 오디오 구독 테스트

TDD Red Phase - H1 해결: AEC-TTS 오디오 연동
TTS 오디오 스트림을 수신하여 AEC playback reference로 설정
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import sys
import os
import json
import asyncio
import numpy as np

# 서비스 경로 추가
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../services/audio_gateway'))


class TestTTSAudioSubscriberFunction:
    """TTS 오디오 구독 함수 존재 테스트"""

    def test_tts_audio_subscriber_function_exists(self):
        """
        tts_audio_subscriber 함수가 main 모듈에 존재해야 함
        """
        from app import main

        assert hasattr(main, 'tts_audio_subscriber'), \
            "main module should have 'tts_audio_subscriber' function"

    @pytest.mark.asyncio
    async def test_tts_audio_subscriber_is_async(self):
        """
        tts_audio_subscriber 함수가 async 함수여야 함
        """
        from app import main

        # async 함수인지 확인
        assert asyncio.iscoroutinefunction(main.tts_audio_subscriber), \
            "tts_audio_subscriber should be an async function"


def create_mock_pubsub_with_audio(audio_messages):
    """헬퍼: 오디오 메시지 목록을 반환하는 mock pubsub 생성"""

    async def mock_listen():
        for msg in audio_messages:
            yield msg
        # 메시지 처리 후 종료
        raise asyncio.CancelledError()

    mock_pubsub = AsyncMock()
    mock_pubsub.subscribe = AsyncMock()
    mock_pubsub.unsubscribe = AsyncMock()
    mock_pubsub.listen = mock_listen

    return mock_pubsub


def create_mock_logger():
    """헬퍼: mock logger 생성"""
    mock_logger = AsyncMock()
    mock_logger.info = AsyncMock()
    mock_logger.warning = AsyncMock()
    mock_logger.error = AsyncMock()
    mock_logger.debug = AsyncMock()
    return mock_logger


class TestTTSAudioSubscription:
    """TTS 오디오 채널 구독 테스트"""

    @pytest.mark.asyncio
    async def test_tts_audio_subscriber_subscribes_to_channel(self):
        """
        tts_audio_subscriber가 TTS 오디오 채널을 구독해야 함
        """
        from app import main

        # Mock pubsub
        mock_pubsub = create_mock_pubsub_with_audio([])
        mock_redis = MagicMock()
        mock_redis.pubsub.return_value = mock_pubsub
        mock_logger = create_mock_logger()

        original_redis = main.redis_client
        original_logger = main._logger

        try:
            main.redis_client = mock_redis
            main._logger = mock_logger

            try:
                await asyncio.wait_for(
                    main.tts_audio_subscriber(),
                    timeout=0.5
                )
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass

            # subscribe가 호출되었는지 확인
            mock_pubsub.subscribe.assert_called()

        finally:
            main.redis_client = original_redis
            main._logger = original_logger


class TestTTSAudioAECIntegration:
    """TTS 오디오 수신 시 AEC 연동 테스트"""

    @pytest.mark.asyncio
    async def test_tts_audio_sets_aec_playback_reference(self):
        """
        H1 해결: TTS 오디오 수신 시 AEC playback reference가 설정되어야 함
        """
        from app.aec import AcousticEchoCanceller
        from app import main

        # Setup
        aec_instance = AcousticEchoCanceller()
        assert aec_instance.has_playback_reference is False, \
            "AEC should not have playback reference initially"

        # TTS 오디오 메시지 시뮬레이션 (바이트 형식)
        audio_data = np.ones(1600, dtype=np.float32) * 0.5
        tts_audio_message = {
            "type": "message",
            "data": audio_data.tobytes()
        }

        mock_pubsub = create_mock_pubsub_with_audio([tts_audio_message])
        mock_redis = MagicMock()
        mock_redis.pubsub.return_value = mock_pubsub
        mock_logger = create_mock_logger()

        original_aec = main.aec
        original_redis = main.redis_client
        original_logger = main._logger

        try:
            main.aec = aec_instance
            main.redis_client = mock_redis
            main._logger = mock_logger

            try:
                await asyncio.wait_for(
                    main.tts_audio_subscriber(),
                    timeout=1.0
                )
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass

            # TTS 오디오 수신 후 AEC reference가 설정되어야 함
            assert aec_instance.has_playback_reference is True, \
                "AEC playback reference should be set after TTS audio received"

        finally:
            main.aec = original_aec
            main.redis_client = original_redis
            main._logger = original_logger

    @pytest.mark.asyncio
    async def test_tts_audio_converts_bytes_to_float32(self):
        """
        TTS 오디오 바이트를 float32 배열로 변환해야 함
        """
        from app.aec import AcousticEchoCanceller
        from app import main

        # Setup
        aec_instance = AcousticEchoCanceller()

        # TTS 오디오 메시지 시뮬레이션
        original_audio = np.array([0.1, 0.2, 0.3, 0.4], dtype=np.float32)
        tts_audio_message = {
            "type": "message",
            "data": original_audio.tobytes()
        }

        mock_pubsub = create_mock_pubsub_with_audio([tts_audio_message])
        mock_redis = MagicMock()
        mock_redis.pubsub.return_value = mock_pubsub
        mock_logger = create_mock_logger()

        original_aec = main.aec
        original_redis = main.redis_client
        original_logger = main._logger

        try:
            main.aec = aec_instance
            main.redis_client = mock_redis
            main._logger = mock_logger

            try:
                await asyncio.wait_for(
                    main.tts_audio_subscriber(),
                    timeout=1.0
                )
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass

            # AEC에 reference가 설정되었으면 성공
            assert aec_instance.has_playback_reference is True

        finally:
            main.aec = original_aec
            main.redis_client = original_redis
            main._logger = original_logger


class TestTTSAudioChannelConstant:
    """TTS 오디오 채널 상수 테스트"""

    def test_tts_audio_channel_constant_exists(self):
        """
        TTS 오디오 채널 상수가 main 모듈에 정의되어야 함
        """
        from app import main

        assert hasattr(main, 'TTS_AUDIO_CHANNEL'), \
            "main module should have 'TTS_AUDIO_CHANNEL' constant"

    def test_tts_audio_channel_has_correct_prefix(self):
        """
        TTS 오디오 채널이 올바른 prefix를 가져야 함
        """
        from app import main

        channel = main.TTS_AUDIO_CHANNEL
        assert channel.startswith("edgevoice:"), \
            f"TTS audio channel should start with 'edgevoice:', got: {channel}"