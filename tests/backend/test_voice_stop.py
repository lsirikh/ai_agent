"""
말하는 도중 멈추기 (사용자 요청 2026-10-18: '자비스가 말을 한번 시작하면 중단을 못 해')

앱의 [중단] 버튼 → POST /api/orchestrator/stop → Redis edgevoice:voice:stop 로 알린다
(오케스트레이터는 답을 멈추고 대기로, 게이트웨이는 남은 답 음성을 버린다).
"""

import json
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient


def test_stop_button_publishes_voice_stop() -> None:
    from services.backend.app.main import app
    from services.backend.app.services import conversation

    redis = AsyncMock()
    with patch.object(conversation, "_get_redis", return_value=redis):
        response = TestClient(app).post("/api/orchestrator/stop")

    assert response.status_code == 200
    channel, payload = redis.publish.await_args.args
    assert channel == "edgevoice:voice:stop"
    assert json.loads(payload)["type"] == "stop"
