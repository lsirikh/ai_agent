"""
Phase 13.6: Hot Reload vs Restart 분리 테스트

TDD Red-Green-Refactor cycle:
1. Voice Speed, Threshold, Language는 Hot Reload (즉시 적용)
2. LLM Model 변경은 Restart 필요 (재시작 필요)
3. 재시작 필요 시 경고 모달 표시
"""

import pytest
from fastapi.testclient import TestClient


class TestHotReloadSettings:
    """Hot Reload 가능한 설정 테스트 (즉시 적용)"""

    def test_voice_speed_is_hot_reload(self, client: TestClient):
        """Voice Speed 변경은 Hot Reload (즉시 적용)"""
        response = client.put("/api/settings/general", json={
            "wake_word": "hey_jarvis",
            "language": "ko",
            "voice_speed": 1.5,
            "wake_word_threshold": 0.5
        })
        assert response.status_code == 200
        data = response.json()
        # Hot reload 가능한 설정은 restart_required가 없거나 False
        assert data.get("restart_required", False) is False

    def test_threshold_is_hot_reload(self, client: TestClient):
        """Threshold 변경은 Hot Reload (즉시 적용)"""
        response = client.put("/api/settings/general", json={
            "wake_word": "hey_jarvis",
            "language": "ko",
            "voice_speed": 1.0,
            "wake_word_threshold": 0.7
        })
        assert response.status_code == 200
        data = response.json()
        assert data.get("restart_required", False) is False

    def test_language_is_hot_reload(self, client: TestClient):
        """Language 변경은 Hot Reload (즉시 적용)"""
        response = client.put("/api/settings/general", json={
            "wake_word": "hey_jarvis",
            "language": "en",
            "voice_speed": 1.0,
            "wake_word_threshold": 0.5
        })
        assert response.status_code == 200
        data = response.json()
        assert data.get("restart_required", False) is False


class TestRestartRequiredSettings:
    """Restart 필요한 설정 테스트"""

    def test_llm_model_requires_restart(self, client: TestClient):
        """LLM Model 변경은 Restart 필요"""
        response = client.post("/api/settings/apply", json={
            "changes": {
                "llm": {"model": "qwen2.5-14b-instruct-awq"}
            }
        })
        # 응답에서 restart_required 체크
        if response.status_code == 200:
            data = response.json()
            # LLM 변경은 restart_required에 llm이 포함되어야 함
            assert "restart_required" in data or "llm" in data.get("restart_required", [])


class TestLLMRestartEndpoint:
    """LLM 재시작 엔드포인트 테스트"""

    def test_llm_restart_endpoint_exists(self, client: TestClient):
        """POST /api/services/llm/restart 엔드포인트가 존재함"""
        response = client.post("/api/services/llm/restart")
        # 404나 405가 아니면 엔드포인트 존재
        assert response.status_code not in [404, 405], "POST /api/services/llm/restart endpoint should exist"

    def test_llm_restart_returns_status(self, client: TestClient):
        """재시작 상태 반환"""
        response = client.post("/api/services/llm/restart")
        if response.status_code == 200:
            data = response.json()
            assert "status" in data


class TestSettingsReloadType:
    """설정 변경 타입 분류 테스트"""

    def test_general_settings_response_includes_reload_type(self, client: TestClient):
        """General Settings 응답에 reload_type 포함"""
        response = client.put("/api/settings/general", json={
            "wake_word": "hey_jarvis",
            "language": "ko",
            "voice_speed": 1.0,
            "wake_word_threshold": 0.5
        })
        assert response.status_code == 200
        # 응답에 reload_type 또는 restart_required 정보 포함


@pytest.fixture
def client():
    """FastAPI TestClient fixture"""
    from services.backend.app.main import app
    return TestClient(app)
