"""
Phase 13.1: Wake Word 등록 버튼 및 연동 테스트

TDD Red-Green-Refactor cycle:
1. PUT /api/settings/wake-word 엔드포인트
2. Wake Word 서비스에 설정 전파
3. 현재 활성 Wake Word 표시
"""

import pytest
from fastapi.testclient import TestClient


class TestWakeWordSettingsEndpoint:
    """PUT /api/settings/wake-word 엔드포인트 테스트"""

    def test_wake_word_endpoint_exists(self, client: TestClient):
        """PUT /api/settings/wake-word 엔드포인트가 존재함"""
        response = client.put("/api/settings/wake-word", json={
            "wake_word": "hey_jarvis"
        })
        # 404나 405가 아니면 엔드포인트 존재
        assert response.status_code not in [404, 405], "PUT /api/settings/wake-word endpoint should exist"

    def test_wake_word_update_hey_jarvis(self, client: TestClient):
        """hey_jarvis로 업데이트"""
        response = client.put("/api/settings/wake-word", json={
            "wake_word": "hey_jarvis"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["wake_word"] == "hey_jarvis"

    def test_wake_word_update_alexa(self, client: TestClient):
        """alexa로 업데이트"""
        response = client.put("/api/settings/wake-word", json={
            "wake_word": "alexa"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["wake_word"] == "alexa"

    def test_wake_word_update_ok_google(self, client: TestClient):
        """ok_google로 업데이트"""
        response = client.put("/api/settings/wake-word", json={
            "wake_word": "ok_google"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["wake_word"] == "ok_google"

    def test_wake_word_returns_status(self, client: TestClient):
        """상태 반환"""
        response = client.put("/api/settings/wake-word", json={
            "wake_word": "hey_jarvis"
        })
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert data["status"] in ["registered", "applied"]

    def test_wake_word_returns_propagated(self, client: TestClient):
        """전파 결과 반환"""
        response = client.put("/api/settings/wake-word", json={
            "wake_word": "hey_jarvis"
        })
        assert response.status_code == 200
        data = response.json()
        assert "propagated" in data


class TestWakeWordPersistence:
    """Wake Word 설정 영속성 테스트"""

    def test_wake_word_saved_to_general_settings(self, client: TestClient):
        """Wake Word가 General Settings에 저장됨"""
        # Wake Word 변경
        client.put("/api/settings/wake-word", json={
            "wake_word": "ok_google"
        })

        # General Settings 조회
        response = client.get("/api/settings/general")
        data = response.json()
        assert data["wake_word"] == "ok_google"


@pytest.fixture
def client():
    """FastAPI TestClient fixture"""
    from services.backend.app.main import app
    return TestClient(app)
