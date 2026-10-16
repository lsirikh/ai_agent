"""
오케스트레이터 상태 저장 회귀 테스트

백엔드 /api/status/stream 은 Redis 키 "orchestrator:state" 를 읽는데,
오케스트레이터는 채널 발행만 하고 이 키를 쓰지 않아 상태가 항상 OFF 로 보였다
(트레이 파형·단계 아이콘이 계속 대기).
"""

import json
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_should_store_current_state_key_when_state_changes() -> None:
    from services.orchestrator.app.orchestrator import Orchestrator
    from services.orchestrator.app.state_machine import State

    redis = AsyncMock()
    with patch.object(Orchestrator, "_setup_redis", return_value=redis):
        orchestrator = Orchestrator(redis_client=redis)

    await orchestrator._publish_state_change(State.READY, State.LISTENING)

    key, value = redis.set.call_args.args[:2]
    assert key == "orchestrator:state"
    assert json.loads(value)["state"] == "LISTENING"
