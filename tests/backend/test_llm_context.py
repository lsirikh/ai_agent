"""
Tests for LLM Context Settings API

Phase 15.1: LLMContextSettings API 구현
- Model & Schema 테스트
- API Endpoints 테스트
"""

import pytest
from pydantic import ValidationError


class TestLLMContextSettingsModel:
    """LLMContextSettings 모델 테스트"""

    def test_llm_context_settings_model(self):
        """LLMContextSettings 모델이 정의되어 있어야 함"""
        from services.backend.app.routes.settings import LLMContextSettings

        # 기본값으로 생성 가능해야 함
        settings = LLMContextSettings()
        assert hasattr(settings, 'context_enabled')
        assert hasattr(settings, 'context_window_size')

    def test_context_window_size_validation(self):
        """context_window_size는 5-50 범위여야 함"""
        from services.backend.app.routes.settings import LLMContextSettings

        # 유효한 범위 내 값
        settings = LLMContextSettings(context_enabled=True, context_window_size=20)
        assert settings.context_window_size == 20

        # 최소값
        settings = LLMContextSettings(context_enabled=True, context_window_size=5)
        assert settings.context_window_size == 5

        # 최대값
        settings = LLMContextSettings(context_enabled=True, context_window_size=50)
        assert settings.context_window_size == 50

        # 범위 밖 값은 ValidationError 발생
        with pytest.raises(ValidationError):
            LLMContextSettings(context_enabled=True, context_window_size=2)

        with pytest.raises(ValidationError):
            LLMContextSettings(context_enabled=True, context_window_size=100)

    def test_context_enabled_default_true(self):
        """context_enabled 기본값은 True"""
        from services.backend.app.routes.settings import LLMContextSettings

        settings = LLMContextSettings()
        assert settings.context_enabled is True


class TestLLMContextSettingsAPI:
    """LLM Context Settings API 엔드포인트 테스트"""

    @pytest.fixture
    def client(self):
        """FastAPI TestClient"""
        from fastapi.testclient import TestClient
        from services.backend.app.main import app
        return TestClient(app)

    def test_get_llm_context_settings_endpoint(self, client):
        """GET /api/settings/llm/context 엔드포인트가 존재하고 응답함"""
        response = client.get("/api/settings/llm/context")

        assert response.status_code == 200
        data = response.json()
        assert "context_enabled" in data
        assert "context_window_size" in data

    def test_put_llm_context_settings_endpoint(self, client):
        """PUT /api/settings/llm/context 엔드포인트가 설정을 업데이트함"""
        payload = {
            "context_enabled": True,
            "context_window_size": 30
        }
        response = client.put("/api/settings/llm/context", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["context_enabled"] is True
        assert data["context_window_size"] == 30
        assert data["status"] == "applied"

    def test_llm_context_saved_to_db(self, client):
        """설정이 DB에 저장되어야 함"""
        # 저장
        payload = {
            "context_enabled": False,
            "context_window_size": 15
        }
        response = client.put("/api/settings/llm/context", json=payload)
        assert response.status_code == 200

        # 다시 읽기
        response = client.get("/api/settings/llm/context")
        assert response.status_code == 200
        data = response.json()
        assert data["context_enabled"] is False
        assert data["context_window_size"] == 15

    def test_llm_context_loaded_from_db(self, client):
        """DB에서 설정이 로드되어야 함"""
        # 먼저 저장
        payload = {
            "context_enabled": True,
            "context_window_size": 25
        }
        client.put("/api/settings/llm/context", json=payload)

        # 새로운 요청으로 로드 확인
        response = client.get("/api/settings/llm/context")
        assert response.status_code == 200
        data = response.json()
        assert data["context_window_size"] == 25

    def test_put_returns_estimated_tokens(self, client):
        """PUT 응답에 estimated_tokens_per_request가 포함되어야 함"""
        payload = {
            "context_enabled": True,
            "context_window_size": 20
        }
        response = client.put("/api/settings/llm/context", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert "estimated_tokens_per_request" in data

        # 예상 토큰 계산: 200 + (20 * 50) + 30 = 1230
        expected_tokens = 200 + (20 * 50) + 30
        assert data["estimated_tokens_per_request"] == expected_tokens

    def test_context_window_size_api_validation(self, client):
        """API에서 context_window_size 범위 검증"""
        # 너무 작은 값
        payload = {
            "context_enabled": True,
            "context_window_size": 2
        }
        response = client.put("/api/settings/llm/context", json=payload)
        assert response.status_code == 422

        # 너무 큰 값
        payload = {
            "context_enabled": True,
            "context_window_size": 100
        }
        response = client.put("/api/settings/llm/context", json=payload)
        assert response.status_code == 422
