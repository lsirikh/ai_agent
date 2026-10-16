"""
TTS Redis Subscriber Tests

Phase 8.1: TTS Redis Subscriber 구현 테스트
TDD Red-Green-Refactor 방식으로 진행
"""
import asyncio
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestTTSRedisSubscriberConnection:
    """Redis 연결 테스트"""

    @pytest.mark.asyncio
    async def test_subscriber_connects_to_redis(self):
        """TTSRedisSubscriber가 Redis에 연결되는지 테스트"""
        from services.tts.app.redis_subscriber import TTSRedisSubscriber

        mock_synthesizer = MagicMock()

        with patch("services.tts.app.redis_subscriber.aioredis") as mock_aioredis:
            # Redis 클라이언트 mock 설정
            mock_redis = MagicMock()
            mock_aioredis.Redis.return_value = mock_redis

            # pubsub은 동기 메서드로 PubSub 객체 반환
            mock_pubsub = MagicMock()
            mock_pubsub.unsubscribe = AsyncMock()
            mock_pubsub.subscribe = AsyncMock()
            mock_redis.pubsub.return_value = mock_pubsub
            mock_redis.aclose = AsyncMock()

            subscriber = TTSRedisSubscriber(synthesizer=mock_synthesizer)
            await subscriber.connect()

            # Redis 연결 확인
            mock_aioredis.Redis.assert_called_once_with(
                host="localhost",
                port=6379,
                decode_responses=True
            )
            assert subscriber.redis_client is not None
            assert subscriber.pubsub is not None

            # 정리
            await subscriber.stop()


class TestTTSRedisSubscriberSubscription:
    """채널 구독 테스트"""

    @pytest.mark.asyncio
    async def test_subscriber_subscribes_to_tts_request_channel(self):
        """TTSRedisSubscriber가 edgevoice:tts:request 채널을 구독하는지 테스트"""
        from services.tts.app.redis_subscriber import TTSRedisSubscriber

        mock_synthesizer = MagicMock()

        with patch("services.tts.app.redis_subscriber.aioredis") as mock_aioredis:
            mock_redis = MagicMock()
            mock_aioredis.Redis.return_value = mock_redis

            mock_pubsub = MagicMock()
            mock_pubsub.subscribe = AsyncMock()
            mock_pubsub.unsubscribe = AsyncMock()
            mock_redis.pubsub.return_value = mock_pubsub
            mock_redis.aclose = AsyncMock()

            subscriber = TTSRedisSubscriber(synthesizer=mock_synthesizer)
            await subscriber.connect()

            # 채널 구독 수행
            await subscriber.subscribe()

            # edgevoice:tts:request 채널 구독 확인
            mock_pubsub.subscribe.assert_called_once_with("edgevoice:tts:request")

            await subscriber.stop()


class TestTTSRedisSubscriberMessageHandling:
    """메시지 처리 테스트"""

    @pytest.mark.asyncio
    async def test_subscriber_parses_tts_request_message(self):
        """TTSRedisSubscriber가 TTS 요청 메시지를 올바르게 파싱하는지 테스트"""
        from services.tts.app.redis_subscriber import TTSRedisSubscriber

        mock_synthesizer = MagicMock()
        mock_synthesizer.synthesize = MagicMock(return_value=b"audio_data")

        subscriber = TTSRedisSubscriber(synthesizer=mock_synthesizer)

        # 테스트 메시지
        test_message = json.dumps({
            "session_id": "test-session-123",
            "text": "안녕하세요",
            "voice": "af_heart",
            "speed": 1.0,
            "timestamp": 1234567890.123
        })

        # 메시지 파싱 테스트
        parsed = subscriber._parse_message(test_message)

        assert parsed["session_id"] == "test-session-123"
        assert parsed["text"] == "안녕하세요"
        assert parsed["voice"] == "af_heart"
        assert parsed["speed"] == 1.0

    @pytest.mark.asyncio
    async def test_subscriber_calls_synthesizer(self):
        """TTSRedisSubscriber가 합성기를 호출하는지 테스트"""
        from services.tts.app.redis_subscriber import TTSRedisSubscriber

        mock_synthesizer = MagicMock()
        mock_synthesizer.synthesize = MagicMock(return_value=b"fake_audio_data")

        with patch("services.tts.app.redis_subscriber.aioredis") as mock_aioredis:
            mock_redis = MagicMock()
            mock_aioredis.Redis.return_value = mock_redis

            mock_pubsub = MagicMock()
            mock_pubsub.subscribe = AsyncMock()
            mock_pubsub.unsubscribe = AsyncMock()
            mock_redis.pubsub.return_value = mock_pubsub
            mock_redis.aclose = AsyncMock()
            mock_redis.publish = AsyncMock()

            subscriber = TTSRedisSubscriber(synthesizer=mock_synthesizer)
            await subscriber.connect()

            # 테스트 메시지 처리
            test_data = {
                "session_id": "test-session-456",
                "text": "테스트 음성입니다",
                "voice": "af_heart",
                "speed": 1.0,
                "timestamp": time.time()
            }

            await subscriber._handle_message(json.dumps(test_data))

            # 합성기 호출 확인 (KokoroTTS.synthesize(text) 시그니처)
            mock_synthesizer.synthesize.assert_called_once_with("테스트 음성입니다")

            await subscriber.stop()

    @pytest.mark.asyncio
    async def test_subscriber_publishes_tts_complete(self):
        """TTSRedisSubscriber가 TTS 완료 메시지를 발행하는지 테스트"""
        from services.tts.app.redis_subscriber import TTSRedisSubscriber

        mock_synthesizer = MagicMock()
        mock_synthesizer.synthesize = MagicMock(return_value=b"fake_audio_data")

        with patch("services.tts.app.redis_subscriber.aioredis") as mock_aioredis:
            mock_redis = MagicMock()
            mock_aioredis.Redis.return_value = mock_redis

            mock_pubsub = MagicMock()
            mock_pubsub.subscribe = AsyncMock()
            mock_pubsub.unsubscribe = AsyncMock()
            mock_redis.pubsub.return_value = mock_pubsub
            mock_redis.aclose = AsyncMock()
            mock_redis.publish = AsyncMock()

            subscriber = TTSRedisSubscriber(synthesizer=mock_synthesizer)
            await subscriber.connect()

            # 테스트 메시지 처리
            test_data = {
                "session_id": "test-session-789",
                "text": "완료 테스트",
                "voice": "af_heart",
                "speed": 1.0,
                "timestamp": time.time()
            }

            await subscriber._handle_message(json.dumps(test_data))

            # tts:complete 채널에 메시지 발행 확인
            # (Phase 36.5 부터 tts:state 의 started/complete 이벤트도 함께 발행된다)
            complete_calls = [
                c for c in mock_redis.publish.call_args_list
                if c[0][0] == "edgevoice:tts:complete"
            ]
            assert len(complete_calls) == 1

            # 발행된 메시지 내용 확인
            published_message = json.loads(complete_calls[0][0][1])
            assert published_message["session_id"] == "test-session-789"
            assert published_message["status"] == "complete"
            assert "audio_length" in published_message

            await subscriber.stop()

    @pytest.mark.asyncio
    async def test_subscriber_handles_invalid_message(self):
        """TTSRedisSubscriber가 잘못된 메시지를 처리하는지 테스트"""
        from services.tts.app.redis_subscriber import TTSRedisSubscriber

        mock_synthesizer = MagicMock()

        with patch("services.tts.app.redis_subscriber.aioredis") as mock_aioredis:
            mock_redis = MagicMock()
            mock_aioredis.Redis.return_value = mock_redis

            mock_pubsub = MagicMock()
            mock_pubsub.subscribe = AsyncMock()
            mock_pubsub.unsubscribe = AsyncMock()
            mock_redis.pubsub.return_value = mock_pubsub
            mock_redis.aclose = AsyncMock()

            subscriber = TTSRedisSubscriber(synthesizer=mock_synthesizer)
            await subscriber.connect()

            # 잘못된 JSON 메시지 처리 - 예외 없이 처리되어야 함
            await subscriber._handle_message("invalid json")

            # 합성기가 호출되지 않아야 함
            mock_synthesizer.synthesize.assert_not_called()

            await subscriber.stop()
