"""지역·시간 설정 API 테스트 (시간대·언어·날씨 기준 지역·날씨 켜기)."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from services.backend.app.services import conversation
from tests.backend.test_chat_tools import FakeRedis


def _client(monkeypatch):
    from services.backend.app.routes import settings

    redis = FakeRedis()
    monkeypatch.setattr(conversation, "_get_redis", lambda: redis)
    app = FastAPI()
    app.include_router(settings.router)
    return TestClient(app)


def test_defaults_are_korea(monkeypatch) -> None:
    body = _client(monkeypatch).get("/api/settings/tools").json()

    assert body["timezone"] == "Asia/Seoul"
    assert body["locale"] == "ko-KR"
    assert body["location"] == "서울"
    assert body["weather_enabled"] is True
    assert body["follow_pc_timezone"] is True


def test_should_save_region_and_time_settings(monkeypatch) -> None:
    client = _client(monkeypatch)

    saved = client.put(
        "/api/settings/tools",
        json={"internet_enabled": True, "timezone": "Asia/Seoul",
              "location": "부산", "weather_enabled": True},
    ).json()

    assert saved["location"] == "부산"
    assert "get_weather" in saved["tools"]
    assert client.get("/api/settings/tools").json()["location"] == "부산"


def test_should_reject_unknown_timezone(monkeypatch) -> None:
    response = _client(monkeypatch).put(
        "/api/settings/tools", json={"timezone": "Mars/Olympus"}
    )

    assert response.status_code == 422


def test_server_time_is_reported_for_comparison_with_pc(monkeypatch) -> None:
    body = _client(monkeypatch).get("/api/settings/tools").json()

    assert body["server_time"].startswith("20")
    assert "UTC" in body["server_time"]
