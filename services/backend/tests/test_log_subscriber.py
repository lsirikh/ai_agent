"""
Test: Log Subscriber
Phase 26: Log Streaming 실시간 연동 수정

TDD Red Phase: 이 테스트는 처음에 실패해야 합니다.
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import json


# ============================================
# Phase 26.1: Log Subscriber 구현
# ============================================

def test_log_subscriber_class_exists():
    """LogSubscriber 클래스가 존재하는지 확인"""
    from app.services.log_subscriber import LogSubscriber
    assert LogSubscriber is not None


def test_log_subscriber_has_subscribe_method():
    """LogSubscriber에 subscribe 메서드가 있는지 확인"""
    from app.services.log_subscriber import LogSubscriber

    subscriber = LogSubscriber()
    assert hasattr(subscriber, "subscribe")
    assert callable(subscriber.subscribe)


def test_log_subscriber_has_logs_channel_constant():
    """LOGS_CHANNEL 상수가 정의되어 있는지 확인"""
    from app.services.log_subscriber import LOGS_CHANNEL
    assert LOGS_CHANNEL is not None
    assert isinstance(LOGS_CHANNEL, str)
    assert "log" in LOGS_CHANNEL.lower()


# ============================================
# Phase 26.2: Log 브로드캐스트
# ============================================

@pytest.mark.asyncio
async def test_log_broadcaster_class_exists():
    """LogBroadcaster 클래스가 존재하는지 확인"""
    from app.services.log_broadcaster import LogBroadcaster
    assert LogBroadcaster is not None


@pytest.mark.asyncio
async def test_log_broadcaster_has_broadcast_method():
    """LogBroadcaster에 broadcast 메서드가 있는지 확인"""
    from app.services.log_broadcaster import LogBroadcaster

    broadcaster = LogBroadcaster()
    assert hasattr(broadcaster, "broadcast")


@pytest.mark.asyncio
async def test_broadcast_log_publishes_to_redis():
    """로그 브로드캐스트가 Redis에 발행하는지 확인"""
    from app.services.log_broadcaster import LogBroadcaster, LOGS_CHANNEL

    mock_redis = AsyncMock()
    mock_redis.publish = AsyncMock(return_value=1)

    broadcaster = LogBroadcaster(redis=mock_redis)

    log_data = {
        "id": "test-id",
        "service": "stt",
        "stage": "transcription",
        "level": "INFO",
        "message": "Test message",
        "created_at": "2024-01-01T00:00:00"
    }

    await broadcaster.broadcast(log_data)

    mock_redis.publish.assert_called_once()
    call_args = mock_redis.publish.call_args
    assert call_args[0][0] == LOGS_CHANNEL


@pytest.mark.asyncio
async def test_broadcast_message_format_correct():
    """브로드캐스트 메시지 포맷이 올바른지 확인"""
    from app.services.log_broadcaster import LogBroadcaster

    mock_redis = AsyncMock()
    mock_redis.publish = AsyncMock(return_value=1)

    broadcaster = LogBroadcaster(redis=mock_redis)

    log_data = {
        "id": "test-id",
        "service": "tts",
        "stage": "synthesis",
        "level": "DEBUG",
        "message": "Debug message"
    }

    await broadcaster.broadcast(log_data)

    call_args = mock_redis.publish.call_args
    message = call_args[0][1]
    parsed = json.loads(message)

    assert "type" in parsed
    assert parsed["type"] == "log"
    assert "data" in parsed
    assert parsed["data"]["service"] == "tts"


# ============================================
# Phase 26.3: SSE Redis Pub/Sub 연동
# ============================================

def test_logs_sse_has_redis_subscription():
    """logs SSE 엔드포인트가 Redis 구독을 사용하는지 확인"""
    from app.routes.logs import create_log_event_generator
    assert create_log_event_generator is not None


@pytest.mark.asyncio
async def test_sse_yields_realtime_logs():
    """SSE가 실시간 로그를 yield하는지 확인"""
    from app.routes.logs import create_log_event_generator

    # Mock Redis pubsub
    mock_pubsub = AsyncMock()
    mock_message = {
        "type": "message",
        "data": json.dumps({
            "type": "log",
            "data": {
                "id": "test-id",
                "service": "llm",
                "message": "Test log"
            }
        }).encode()
    }

    async def mock_listen():
        yield mock_message

    mock_pubsub.listen = mock_listen

    generator = create_log_event_generator(pubsub=mock_pubsub)

    # Get first event (should be connected)
    event = await generator.__anext__()
    assert "connected" in event

    # Get second event (should be the log)
    event = await generator.__anext__()
    assert "log" in event
    assert "llm" in event


# ============================================
# Phase 26.4: Lifespan에서 Log Subscriber 시작
# ============================================

def test_main_imports_log_subscriber():
    """main.py가 log_subscriber를 import하는지 확인"""
    # 이 테스트는 main.py에서 log_subscriber import 여부를 확인
    import app.main
    assert hasattr(app.main, "start_log_subscriber") or "log_subscriber" in dir(app.main)
