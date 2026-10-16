"""
Test: Audio Gateway Settings Endpoint
Phase 25.3: Audio Gateway /settings 엔드포인트

TDD Red Phase: 이 테스트는 처음에 실패해야 합니다.
"""
import pytest
from unittest.mock import patch, AsyncMock


# Phase 25.3: Audio Gateway /settings 엔드포인트 테스트

def test_audio_gateway_settings_endpoint_exists():
    """
    Audio Gateway에 /settings 엔드포인트가 존재하는지 확인.

    PUT /settings: 설정 업데이트
    GET /settings: 현재 설정 조회
    """
    from fastapi.testclient import TestClient

    # Redis 연결 모킹
    with patch('app.main.redis') as mock_redis_module:
        mock_redis_module.Redis = AsyncMock

        from app.main import app
        client = TestClient(app)

        # PUT /settings 엔드포인트 존재 확인
        routes = [route.path for route in app.routes]
        assert "/settings" in routes, f"PUT /settings endpoint not found. Routes: {routes}"


def test_audio_gateway_put_settings_updates_vad():
    """
    PUT /settings로 VAD 설정을 업데이트할 수 있는지 확인.
    """
    from fastapi.testclient import TestClient

    with patch('app.main.redis') as mock_redis_module:
        mock_redis_module.Redis = AsyncMock

        from app.main import app
        client = TestClient(app)

        response = client.put("/settings", json={
            "vad_threshold": 0.6
        })

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "updated"
        assert "vad" in data


def test_audio_gateway_put_settings_updates_barge_in():
    """
    PUT /settings로 Barge-in 설정을 업데이트할 수 있는지 확인.
    """
    from fastapi.testclient import TestClient

    with patch('app.main.redis') as mock_redis_module:
        mock_redis_module.Redis = AsyncMock

        from app.main import app
        client = TestClient(app)

        response = client.put("/settings", json={
            "barge_in_energy_threshold": 0.3,
            "barge_in_vad_threshold": 0.5
        })

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "updated"
        assert "barge_in" in data


def test_audio_gateway_get_settings_returns_current():
    """
    GET /settings가 현재 설정을 반환하는지 확인.
    """
    from fastapi.testclient import TestClient

    with patch('app.main.redis') as mock_redis_module:
        mock_redis_module.Redis = AsyncMock

        from app.main import app
        client = TestClient(app)

        response = client.get("/settings")

        assert response.status_code == 200
        data = response.json()

        # 필수 설정 필드 확인
        assert "vad" in data
        assert "barge_in" in data
        assert "aec" in data
