"""
Settings Options Endpoint Tests

Phase 10.3.2: Settings Options API 테스트
TDD: Red → Green → Refactor
"""
import pytest


class TestGetSettingsOptionsEndpoint:
    """GET /api/settings/options 엔드포인트 테스트"""

    def test_get_settings_options_endpoint(self):
        """GET /api/settings/options 엔드포인트가 존재하는지 확인"""
        from fastapi.testclient import TestClient
        from services.backend.app.main import app

        client = TestClient(app)
        response = client.get("/api/settings/options")

        assert response.status_code == 200


class TestOptionsIncludesTTSEngines:
    """TTS 엔진 목록 포함 테스트"""

    def test_options_includes_tts_engines(self):
        """응답에 TTS 엔진 목록이 포함되어 있는지 확인"""
        from fastapi.testclient import TestClient
        from services.backend.app.main import app

        client = TestClient(app)
        response = client.get("/api/settings/options")

        data = response.json()
        assert "tts_engines" in data
        assert isinstance(data["tts_engines"], list)
        assert len(data["tts_engines"]) > 0

        # 각 엔진 항목 구조 확인
        for engine in data["tts_engines"]:
            assert "id" in engine
            assert "display_name" in engine


class TestOptionsIncludesSTTModels:
    """STT 모델 목록 포함 테스트"""

    def test_options_includes_stt_models(self):
        """응답에 STT 모델 목록이 포함되어 있는지 확인"""
        from fastapi.testclient import TestClient
        from services.backend.app.main import app

        client = TestClient(app)
        response = client.get("/api/settings/options")

        data = response.json()
        assert "stt_models" in data
        assert isinstance(data["stt_models"], list)
        assert len(data["stt_models"]) > 0

        # 각 모델 항목 구조 확인
        for model in data["stt_models"]:
            assert "id" in model
            assert "display_name" in model
            assert "vram_gb" in model


class TestOptionsIncludesLLMModels:
    """LLM 모델 목록 포함 테스트"""

    def test_options_includes_llm_models(self):
        """응답에 LLM 모델 목록이 포함되어 있는지 확인"""
        from fastapi.testclient import TestClient
        from services.backend.app.main import app

        client = TestClient(app)
        response = client.get("/api/settings/options")

        data = response.json()
        assert "llm_models" in data
        assert isinstance(data["llm_models"], list)
        assert len(data["llm_models"]) > 0

        # 각 모델 항목 구조 확인
        for model in data["llm_models"]:
            assert "id" in model
            assert "display_name" in model
            assert "vram_gb" in model


class TestOptionsResponseStructure:
    """응답 구조 테스트"""

    def test_options_response_structure(self):
        """응답이 올바른 구조를 가지고 있는지 확인"""
        from fastapi.testclient import TestClient
        from services.backend.app.main import app

        client = TestClient(app)
        response = client.get("/api/settings/options")

        data = response.json()

        # 필수 필드 확인
        required_fields = ["tts_engines", "stt_models", "llm_models"]
        for field in required_fields:
            assert field in data

    def test_options_includes_current_settings(self):
        """응답에 현재 설정값이 포함되어 있는지 확인"""
        from fastapi.testclient import TestClient
        from services.backend.app.main import app

        client = TestClient(app)
        response = client.get("/api/settings/options")

        data = response.json()

        # 현재 설정 필드 확인
        assert "current" in data
        current = data["current"]
        assert "tts_engine" in current
        assert "stt_model" in current
        assert "llm_model" in current
