"""
Phase 13.5: General Settings DB 저장 테스트

TDD Red-Green-Refactor cycle:
1. GET /api/settings/general 엔드포인트 테스트
2. PUT /api/settings/general 엔드포인트 테스트
3. DB 저장 검증
4. 페이지 새로고침 시 설정 로드
"""

import pytest
from fastapi.testclient import TestClient


class TestGetGeneralSettingsEndpoint:
    """GET /api/settings/general 엔드포인트 테스트"""

    def test_get_general_settings_endpoint_exists(self, client: TestClient):
        """GET /api/settings/general 엔드포인트가 존재함"""
        response = client.get("/api/settings/general")
        # 404가 아니면 엔드포인트 존재
        assert response.status_code != 404, "GET /api/settings/general endpoint should exist"

    def test_get_general_settings_returns_default_values(self, client: TestClient):
        """기본값을 반환함"""
        response = client.get("/api/settings/general")
        assert response.status_code == 200

        data = response.json()
        assert "wake_word" in data
        assert "language" in data
        assert "voice_speed" in data
        assert "wake_word_threshold" in data

    def test_get_general_settings_default_wake_word(self, client: TestClient):
        """기본 Wake Word는 hey_jarvis"""
        response = client.get("/api/settings/general")
        data = response.json()
        assert data["wake_word"] == "hey_jarvis"

    def test_get_general_settings_default_language(self, client: TestClient):
        """기본 언어는 ko (한국어)"""
        response = client.get("/api/settings/general")
        data = response.json()
        assert data["language"] == "ko"

    def test_get_general_settings_default_voice_speed(self, client: TestClient):
        """기본 Voice Speed는 1.0"""
        response = client.get("/api/settings/general")
        data = response.json()
        assert data["voice_speed"] == 1.0

    def test_get_general_settings_default_threshold(self, client: TestClient):
        """기본 Threshold는 0.5"""
        response = client.get("/api/settings/general")
        data = response.json()
        assert data["wake_word_threshold"] == 0.5


class TestPutGeneralSettingsEndpoint:
    """PUT /api/settings/general 엔드포인트 테스트"""

    def test_put_general_settings_endpoint_exists(self, client: TestClient):
        """PUT /api/settings/general 엔드포인트가 존재함"""
        response = client.put("/api/settings/general", json={
            "wake_word": "hey_jarvis",
            "language": "ko",
            "voice_speed": 1.0,
            "wake_word_threshold": 0.5
        })
        # 404나 405가 아니면 엔드포인트 존재
        assert response.status_code not in [404, 405], "PUT /api/settings/general endpoint should exist"

    def test_put_general_settings_updates_wake_word(self, client: TestClient):
        """Wake Word 업데이트"""
        response = client.put("/api/settings/general", json={
            "wake_word": "alexa",
            "language": "ko",
            "voice_speed": 1.0,
            "wake_word_threshold": 0.5
        })
        assert response.status_code == 200
        data = response.json()
        assert data["wake_word"] == "alexa"

    def test_put_general_settings_updates_language(self, client: TestClient):
        """Language 업데이트"""
        response = client.put("/api/settings/general", json={
            "wake_word": "hey_jarvis",
            "language": "en",
            "voice_speed": 1.0,
            "wake_word_threshold": 0.5
        })
        assert response.status_code == 200
        data = response.json()
        assert data["language"] == "en"

    def test_put_general_settings_updates_voice_speed(self, client: TestClient):
        """Voice Speed 업데이트"""
        response = client.put("/api/settings/general", json={
            "wake_word": "hey_jarvis",
            "language": "ko",
            "voice_speed": 1.5,
            "wake_word_threshold": 0.5
        })
        assert response.status_code == 200
        data = response.json()
        assert data["voice_speed"] == 1.5

    def test_put_general_settings_updates_threshold(self, client: TestClient):
        """Threshold 업데이트"""
        response = client.put("/api/settings/general", json={
            "wake_word": "hey_jarvis",
            "language": "ko",
            "voice_speed": 1.0,
            "wake_word_threshold": 0.7
        })
        assert response.status_code == 200
        data = response.json()
        assert data["wake_word_threshold"] == 0.7

    def test_put_general_settings_returns_propagation_results(self, client: TestClient):
        """전파 결과 반환"""
        response = client.put("/api/settings/general", json={
            "wake_word": "hey_jarvis",
            "language": "ko",
            "voice_speed": 1.0,
            "wake_word_threshold": 0.5
        })
        assert response.status_code == 200
        data = response.json()
        # propagation_results가 있어야 함 (성공 여부 관계없이)
        assert "propagation_results" in data or "status" in data


class TestGeneralSettingsPersistence:
    """General Settings DB 저장 테스트"""

    def test_general_settings_saved_to_db(self, client: TestClient):
        """설정이 DB에 저장됨"""
        # 설정 변경
        client.put("/api/settings/general", json={
            "wake_word": "ok_google",
            "language": "ja",
            "voice_speed": 0.8,
            "wake_word_threshold": 0.3
        })

        # 다시 조회
        response = client.get("/api/settings/general")
        data = response.json()

        assert data["wake_word"] == "ok_google"
        assert data["language"] == "ja"
        assert data["voice_speed"] == 0.8
        assert data["wake_word_threshold"] == 0.3

    def test_general_settings_loaded_on_page_refresh(self, client: TestClient):
        """페이지 새로고침 시 저장된 값 로드"""
        # 설정 변경
        client.put("/api/settings/general", json={
            "wake_word": "alexa",
            "language": "en",
            "voice_speed": 1.2,
            "wake_word_threshold": 0.6
        })

        # 새로운 GET 요청 (새로고침 시뮬레이션)
        response = client.get("/api/settings/general")
        data = response.json()

        assert data["wake_word"] == "alexa"
        assert data["language"] == "en"
        assert data["voice_speed"] == 1.2
        assert data["wake_word_threshold"] == 0.6


class TestGeneralSettingsValidation:
    """General Settings 유효성 검사 테스트"""

    def test_voice_speed_min_boundary(self, client: TestClient):
        """Voice Speed 최소값 경계 테스트 (0.5)"""
        response = client.put("/api/settings/general", json={
            "wake_word": "hey_jarvis",
            "language": "ko",
            "voice_speed": 0.5,
            "wake_word_threshold": 0.5
        })
        assert response.status_code == 200

    def test_voice_speed_max_boundary(self, client: TestClient):
        """Voice Speed 최대값 경계 테스트 (2.0)"""
        response = client.put("/api/settings/general", json={
            "wake_word": "hey_jarvis",
            "language": "ko",
            "voice_speed": 2.0,
            "wake_word_threshold": 0.5
        })
        assert response.status_code == 200

    def test_threshold_min_boundary(self, client: TestClient):
        """Threshold 최소값 경계 테스트 (0.1)"""
        response = client.put("/api/settings/general", json={
            "wake_word": "hey_jarvis",
            "language": "ko",
            "voice_speed": 1.0,
            "wake_word_threshold": 0.1
        })
        assert response.status_code == 200

    def test_threshold_max_boundary(self, client: TestClient):
        """Threshold 최대값 경계 테스트 (0.9)"""
        response = client.put("/api/settings/general", json={
            "wake_word": "hey_jarvis",
            "language": "ko",
            "voice_speed": 1.0,
            "wake_word_threshold": 0.9
        })
        assert response.status_code == 200


# Pytest fixtures
@pytest.fixture
def client():
    """FastAPI TestClient fixture"""
    from services.backend.app.main import app
    return TestClient(app)
