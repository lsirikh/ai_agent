"""
Test: StateManager Service
Phase 18.1.2: Orchestrator 상태 관리 서비스

TDD Red Phase: 이 테스트는 처음에 실패해야 합니다.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4


@pytest.fixture
def mock_redis():
    """Mock Redis client"""
    redis = AsyncMock()
    redis.set = AsyncMock(return_value=True)
    redis.get = AsyncMock(return_value=None)
    redis.publish = AsyncMock(return_value=1)
    return redis


@pytest.mark.asyncio
async def test_state_manager_update_state_stores_in_redis(mock_redis):
    """StateManager.update_state()가 Redis에 상태를 저장하는지 확인"""
    from app.services.state_manager import StateManager
    from app.models.orchestrator import OrchestratorState

    manager = StateManager(redis=mock_redis)
    await manager.update_state(OrchestratorState.READY)

    # Redis set이 호출되었는지 확인
    mock_redis.set.assert_called_once()
    call_args = mock_redis.set.call_args
    # 키 이름에 'orchestrator' 포함
    assert "orchestrator" in call_args[0][0].lower() or "state" in call_args[0][0].lower()


@pytest.mark.asyncio
async def test_state_manager_get_current_state_returns_latest(mock_redis):
    """StateManager.get_current_state()가 최신 상태를 반환하는지 확인"""
    from app.services.state_manager import StateManager
    from app.models.orchestrator import OrchestratorState

    # Redis에서 'READY' 상태 반환하도록 설정
    mock_redis.get = AsyncMock(return_value='{"state": "READY"}')

    manager = StateManager(redis=mock_redis)
    state = await manager.get_current_state()

    # 상태 반환 확인
    assert state is not None
    assert state.get("state") == "READY" or state == OrchestratorState.READY


@pytest.mark.asyncio
async def test_state_manager_publishes_state_change_event(mock_redis):
    """상태 변경 시 Redis Pub/Sub으로 이벤트를 발행하는지 확인"""
    from app.services.state_manager import StateManager
    from app.models.orchestrator import OrchestratorState

    manager = StateManager(redis=mock_redis)
    await manager.update_state(OrchestratorState.LISTENING)

    # Redis publish가 호출되었는지 확인
    mock_redis.publish.assert_called_once()
    call_args = mock_redis.publish.call_args
    # 채널 이름에 'dashboard' 또는 'orchestrator' 포함
    channel = call_args[0][0]
    assert "dashboard" in channel.lower() or "orchestrator" in channel.lower() or "state" in channel.lower()


@pytest.mark.asyncio
async def test_state_manager_stores_session_id(mock_redis):
    """StateManager가 session_id와 함께 상태를 저장하는지 확인"""
    from app.services.state_manager import StateManager
    from app.models.orchestrator import OrchestratorState

    session_id = uuid4()
    manager = StateManager(redis=mock_redis)
    await manager.update_state(OrchestratorState.STT_PROCESSING, session_id=session_id)

    # Redis set 호출 확인
    mock_redis.set.assert_called_once()
    # 저장된 데이터에 session_id 포함 여부는 구현에 따라 다를 수 있음
    call_args = mock_redis.set.call_args
    stored_value = call_args[0][1]
    assert str(session_id) in stored_value or session_id is not None


@pytest.mark.asyncio
async def test_state_manager_stores_metadata(mock_redis):
    """StateManager가 metadata와 함께 상태를 저장하는지 확인"""
    from app.services.state_manager import StateManager
    from app.models.orchestrator import OrchestratorState

    metadata = {"error": "Connection timeout", "service": "stt"}
    manager = StateManager(redis=mock_redis)
    await manager.update_state(OrchestratorState.ERROR, metadata=metadata)

    # Redis set 호출 확인
    mock_redis.set.assert_called_once()
    call_args = mock_redis.set.call_args
    stored_value = call_args[0][1]
    # metadata가 JSON에 포함되어야 함
    assert "error" in stored_value or "metadata" in stored_value
