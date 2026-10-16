"""
Model Selection Pipeline Integration Tests

Phase 10.5.3: 모델 선택 파이프라인 통합 테스트
TDD: Red → Green → Refactor
"""
import pytest
from unittest.mock import MagicMock, patch, AsyncMock


class TestFullPipelineWithMeloTTS:
    """MeloTTS로 전체 파이프라인 테스트"""

    def test_full_pipeline_with_melo_tts(self):
        """MeloTTS 엔진을 사용하여 전체 파이프라인이 동작하는지 확인"""
        from services.tts.app.engine_manager import TTSEngineManager

        # Create manager with MeloTTS as default
        manager = TTSEngineManager(default_engine="melo")

        # Verify MeloTTS is current engine
        assert manager.get_current_engine_name() == "melo"

        # Get engine info
        engine = manager.get_current_engine()
        info = engine.get_info()

        # MeloTTS should support Korean
        assert "ko" in info.get("supported_languages", [])

        # MeloTTS should have correct sample rate
        assert info.get("sample_rate") == 44100


class TestFullPipelineWithKoreanSTT:
    """한국어 STT로 전체 파이프라인 테스트"""

    def test_full_pipeline_with_korean_stt(self):
        """한국어 최적화 STT 모델을 사용하여 파이프라인이 동작하는지 확인"""
        from services.stt.app.model_manager import STTModelManager

        # Create manager with Korean optimized model
        manager = STTModelManager(default_model="small")

        # Switch to Korean model
        result = manager.switch_model("ghost613/faster-whisper-large-v3-turbo-korean")
        assert result is True

        # Verify Korean model is active
        current = manager.get_current_model_name()
        assert "korean" in current.lower()


class TestDashboardSettingsAffectPipeline:
    """대시보드 설정이 파이프라인에 반영되는지 테스트"""

    def test_dashboard_settings_affect_pipeline(self):
        """대시보드에서 변경한 설정이 파이프라인에 반영되는지 확인"""
        from fastapi.testclient import TestClient
        from services.backend.app.main import app

        client = TestClient(app)

        # 1. Get current settings
        response = client.get("/api/settings")
        assert response.status_code == 200
        initial_settings = response.json()

        # 2. Apply new settings via dashboard API
        new_settings = {
            "changes": {
                "tts": {"engine": "edge_tts"},
                "stt": {"model": "medium"},
                "llm": {"temperature": 0.8}
            }
        }
        response = client.post("/api/settings/apply", json=new_settings)
        assert response.status_code == 200
        apply_result = response.json()

        # 3. Verify settings were applied
        assert apply_result["applied"]["tts"] is True
        assert apply_result["applied"]["stt"] is True
        assert apply_result["applied"]["llm"] is True

        # 4. Get updated settings
        response = client.get("/api/settings")
        assert response.status_code == 200
        updated_settings = response.json()

        # 5. Verify changes are reflected
        assert updated_settings["tts"]["engine"] == "edge_tts"
        assert updated_settings["stt"]["model"] == "medium"
        assert updated_settings["llm"]["temperature"] == 0.8


class TestSettingsOptionsEndpoint:
    """설정 옵션 엔드포인트 통합 테스트"""

    def test_settings_options_endpoint_returns_all_options(self):
        """설정 옵션 엔드포인트가 모든 옵션을 반환하는지 확인"""
        from fastapi.testclient import TestClient
        from services.backend.app.main import app

        client = TestClient(app)

        response = client.get("/api/settings/options")
        assert response.status_code == 200

        data = response.json()

        # Should have TTS engines
        assert "tts_engines" in data
        assert len(data["tts_engines"]) >= 4  # melo, kokoro, edge_tts, gtts

        # Should have STT models
        assert "stt_models" in data
        assert len(data["stt_models"]) >= 5  # tiny, base, small, medium, large-v3, etc.

        # Should have LLM models
        assert "llm_models" in data
        assert len(data["llm_models"]) > 0

        # Should have current settings
        assert "current" in data


class TestHotSwapBehavior:
    """Hot-swap 동작 통합 테스트"""

    def test_tts_engine_change_is_hot_swap(self):
        """TTS 엔진 변경이 hot-swap인지 확인 (재시작 불필요)"""
        from fastapi.testclient import TestClient
        from services.backend.app.main import app

        client = TestClient(app)

        response = client.post("/api/settings/apply", json={
            "changes": {
                "tts": {"engine": "kokoro"}
            }
        })

        assert response.status_code == 200
        data = response.json()

        # TTS should not require restart
        assert "tts" not in data.get("restart_required", [])

    def test_stt_model_change_is_hot_swap(self):
        """STT 모델 변경이 hot-swap인지 확인 (재시작 불필요)"""
        from fastapi.testclient import TestClient
        from services.backend.app.main import app

        client = TestClient(app)

        response = client.post("/api/settings/apply", json={
            "changes": {
                "stt": {"model": "small"}
            }
        })

        assert response.status_code == 200
        data = response.json()

        # STT should not require restart
        assert "stt" not in data.get("restart_required", [])

    def test_llm_model_change_requires_restart(self):
        """LLM 모델 변경이 재시작을 필요로 하는지 확인"""
        from fastapi.testclient import TestClient
        from services.backend.app.main import app

        client = TestClient(app)

        response = client.post("/api/settings/apply", json={
            "changes": {
                "llm": {"model": "phi-4"}
            }
        })

        assert response.status_code == 200
        data = response.json()

        # LLM model change should require restart
        assert "llm" in data.get("restart_required", [])
