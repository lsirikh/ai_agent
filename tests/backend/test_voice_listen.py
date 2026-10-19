"""
파형을 눌러 듣기 시작
(사용자 요청 2026-10-19: 파형을 한 번 누르면 입력받고, 한 번 더 누르면 정지)

앱 → POST /api/orchestrator/listen → '헤이 자비스' 감지와 같은 이벤트
(edgevoice:wake_word:detected) — 오케스트레이터는 듣기로, 게이트웨이는 녹음을 시작한다.
"""

import json
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient


def test_listen_button_acts_like_the_wake_word() -> None:
    from services.backend.app.main import app
    from services.backend.app.services import conversation

    redis = AsyncMock()
    with patch.object(conversation, "_get_redis", return_value=redis):
        response = TestClient(app).post("/api/orchestrator/listen")

    assert response.status_code == 200
    channel, payload = redis.publish.await_args.args
    assert channel == "edgevoice:wake_word:detected"
    event = json.loads(payload)
    assert event["type"] == "wake_word_detected" and event["source"] == "button"
