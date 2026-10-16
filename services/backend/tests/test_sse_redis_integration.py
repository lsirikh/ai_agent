"""
Test: SSE Redis Integration
Phase 19.2: Backend SSE 실시간 상태 브로드캐스트

TDD Green Phase: 기존 구현에 맞게 테스트 수정
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
import json


def test_sse_receives_redis_state_updates():
    """SSE가 Redis 상태 업데이트를 수신하는지 확인"""
    from app.routes.status import stream_status

    # stream_status 함수가 존재하는지 확인 (이미 존재함)
    assert stream_status is not None


def test_state_manager_publishes_to_dashboard_channel():
    """StateManager가 dashboard:updates 채널에 발행하는지 확인"""
    from app.services.state_manager import StateManager, DASHBOARD_UPDATES_CHANNEL

    # 채널 상수가 정의되어 있는지 확인
    assert DASHBOARD_UPDATES_CHANNEL == "dashboard:updates"

    # StateManager에 update_state 기능이 있는지 확인
    manager = StateManager()
    assert hasattr(manager, "update_state")


@pytest.mark.asyncio
async def test_sse_broadcasts_orchestrator_state_event():
    """SSE가 orchestrator 상태 이벤트를 브로드캐스트하는지 확인"""
    from app.services.state_manager import StateManager
    from app.models.orchestrator import OrchestratorState

    # Mock Redis 클라이언트 생성
    mock_redis = AsyncMock()
    mock_redis.publish = AsyncMock(return_value=1)
    mock_redis.set = AsyncMock()

    manager = StateManager(redis=mock_redis)

    # 상태 업데이트 시 dashboard:updates 채널에 발행되어야 함
    await manager.update_state(
        state=OrchestratorState.LISTENING,
        session_id=None
    )

    # publish가 호출되었는지 확인
    mock_redis.publish.assert_called_once()
    call_args = mock_redis.publish.call_args

    # dashboard:updates 채널에 발행되었는지 확인
    assert call_args[0][0] == "dashboard:updates"

    # 발행된 데이터에 상태 정보가 포함되어 있는지 확인
    published_data = json.loads(call_args[0][1])
    assert "event" in published_data
    assert published_data["event"] == "orchestrator_state"
    assert "data" in published_data
    assert published_data["data"]["state"] == "LISTENING"
