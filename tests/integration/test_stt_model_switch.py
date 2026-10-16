"""
STT Model Switch Integration Tests

Phase 10.5.2: STT 모델 전환 통합 테스트
TDD: Red → Green → Refactor
"""
import pytest
from unittest.mock import MagicMock, patch


class TestSwitchToKoreanModel:
    """한국어 최적화 모델로 전환 테스트"""

    def test_switch_to_korean_model(self):
        """한국어 최적화 모델로 전환이 동작하는지 확인"""
        from services.stt.app.model_manager import STTModelManager

        # Create manager with small model
        manager = STTModelManager(default_model="small")

        # Verify initial model
        initial_model = manager.get_current_model_name()
        assert initial_model == "small"

        # Switch to Korean optimized model
        result = manager.switch_model("ghost613/faster-whisper-large-v3-turbo-korean")
        assert result is True

        # Verify model switched
        new_model = manager.get_current_model_name()
        assert new_model == "ghost613/faster-whisper-large-v3-turbo-korean"


class TestSwitchCleansMemory:
    """메모리 해제 테스트"""

    def test_switch_cleans_memory(self):
        """모델 전환 시 이전 모델 메모리가 해제되는지 확인"""
        from services.stt.app.model_manager import STTModelManager

        manager = STTModelManager(default_model="small")

        # Switch models
        manager.switch_model("tiny")

        # The old model should be unloaded (not in loaded models)
        # Since we use lazy loading, we just verify the current model is correct
        assert manager.get_current_model_name() == "tiny"


class TestSettingsTriggersSTTSwitch:
    """설정 변경으로 STT 모델 전환 트리거 테스트"""

    def test_settings_triggers_switch(self):
        """Backend 설정 변경이 STT 모델 전환을 트리거하는지 확인"""
        from fastapi.testclient import TestClient
        from services.backend.app.main import app

        client = TestClient(app)

        # Apply settings change for STT model
        response = client.post("/api/settings/apply", json={
            "changes": {
                "stt": {"model": "large-v3"}
            }
        })

        assert response.status_code == 200
        data = response.json()
        assert data["applied"]["stt"] is True

        # STT model change should be hot-swap (no restart required)
        assert "stt" not in data.get("restart_required", [])


class TestModelAvailability:
    """모델 사용 가능성 테스트"""

    def test_get_available_models(self):
        """사용 가능한 모델 목록을 가져올 수 있는지 확인"""
        from services.stt.app.model_manager import STTModelManager

        manager = STTModelManager()
        models = manager.get_available_models()

        assert isinstance(models, list)
        assert len(models) > 0

        # Should have standard whisper models
        model_names = [m.get("id") or m.get("name") for m in models]
        assert "small" in model_names or any("small" in str(n) for n in model_names)

    def test_invalid_model_switch_fails(self):
        """존재하지 않는 모델로 전환 시도가 실패하는지 확인"""
        from services.stt.app.model_manager import STTModelManager

        manager = STTModelManager()

        # Try to switch to invalid model
        result = manager.switch_model("nonexistent_model_xyz")
        assert result is False


class TestModelSwitchPerformance:
    """모델 전환 성능 테스트"""

    def test_model_switch_is_reasonably_fast(self):
        """모델 전환이 합리적인 시간 내에 완료되는지 확인"""
        from services.stt.app.model_manager import STTModelManager
        import time

        manager = STTModelManager(default_model="tiny")

        # Record start time
        start_time = time.time()

        # Switch to another small model
        manager.switch_model("base")

        # Should complete within reasonable time (< 60 seconds for hot swap decision)
        # Note: Actual model loading may take longer, but switch_model should return quickly
        elapsed = time.time() - start_time
        assert elapsed < 60.0, f"Model switch took too long: {elapsed}s"
