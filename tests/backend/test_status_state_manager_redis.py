"""
상태 스트림 Redis 연결 회귀 테스트

set_status_redis_client() 를 아무도 부르지 않아 StateManager 의 Redis 가 None 이었고,
/api/status/stream 이 오케스트레이터 상태와 무관하게 항상 OFF 를 보냈다.
주입된 클라이언트가 없으면 REDIS_HOST/REDIS_PORT 로 직접 연결해야 한다.
"""

import json
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_should_read_orchestrator_state_when_no_client_was_injected() -> None:
    import services.backend.app.routes.status as status

    fake_redis = AsyncMock()
    fake_redis.get.return_value = json.dumps({"state": "LISTENING"})

    with (
        patch.object(status, "_redis_client", None),
        patch.object(status, "_state_manager", None),
        patch("redis.asyncio.Redis", return_value=fake_redis),
    ):
        manager = await status.get_status_state_manager()
        state = await manager.get_current_state()

    assert state["state"] == "LISTENING"
