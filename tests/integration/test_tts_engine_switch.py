"""
TTS Engine Switch Integration Tests

Phase 10.5.1: TTS 엔진 전환 통합 테스트
TDD: Red → Green → Refactor
"""
import pytest
from unittest.mock import MagicMock, patch, AsyncMock


class TestSwitchFromKokoroToMelo:
    """Kokoro에서 MeloTTS로 전환 테스트"""

    def test_switch_from_kokoro_to_melo(self):
        """Kokoro에서 MeloTTS로 엔진 전환이 동작하는지 확인"""
        from services.tts.app.engine_manager import TTSEngineManager

        # Create manager with default engine (kokoro)
        manager = TTSEngineManager(default_engine="kokoro")

        # Verify initial engine
        initial_engine = manager.get_current_engine_name()
        assert initial_engine == "kokoro"

        # Switch to melo
        result = manager.switch_engine("melo")
        assert result is True

        # Verify engine switched
        new_engine = manager.get_current_engine_name()
        assert new_engine == "melo"


class TestSwitchToEdgeTTS:
    """Edge-TTS로 전환 테스트"""

    def test_switch_to_edge_tts(self):
        """Edge-TTS로 엔진 전환이 동작하는지 확인"""
        from services.tts.app.engine_manager import TTSEngineManager

        # Create manager
        manager = TTSEngineManager()

        # Switch to edge_tts
        result = manager.switch_engine("edge_tts")
        assert result is True

        # Verify engine switched
        current_engine = manager.get_current_engine_name()
        assert current_engine == "edge_tts"


class TestSettingsTriggersSwitch:
    """설정 변경으로 엔진 전환 트리거 테스트"""

    def test_settings_triggers_switch(self):
        """Backend 설정 변경이 TTS 엔진 전환을 트리거하는지 확인"""
        from fastapi.testclient import TestClient
        from services.backend.app.main import app

        client = TestClient(app)

        # Apply settings change for TTS engine
        response = client.post("/api/settings/apply", json={
            "changes": {
                "tts": {"engine": "edge_tts"}
            }
        })

        assert response.status_code == 200
        data = response.json()
        assert data["applied"]["tts"] is True

        # TTS engine change should be hot-swap (no restart required)
        assert "tts" not in data.get("restart_required", [])


class TestEngineAvailability:
    """엔진 사용 가능성 테스트"""

    def test_get_available_engines(self):
        """사용 가능한 엔진 목록을 가져올 수 있는지 확인"""
        from services.tts.app.engine_manager import TTSEngineManager

        manager = TTSEngineManager()
        engines = manager.get_available_engines()

        assert isinstance(engines, list)
        assert len(engines) > 0

        # Each engine should have name and display_name
        for engine in engines:
            assert "name" in engine
            assert "display_name" in engine

    def test_invalid_engine_switch_fails(self):
        """존재하지 않는 엔진으로 전환 시도가 실패하는지 확인"""
        from services.tts.app.engine_manager import TTSEngineManager

        manager = TTSEngineManager()

        # Try to switch to invalid engine
        result = manager.switch_engine("nonexistent_engine")
        assert result is False


class TestEngineHotSwap:
    """엔진 hot-swap 테스트"""

    def test_engine_hot_swap_is_instant(self):
        """엔진 전환이 즉시 이루어지는지 확인 (재시작 불필요)"""
        from services.tts.app.engine_manager import TTSEngineManager
        import time

        manager = TTSEngineManager()

        # Record start time
        start_time = time.time()

        # Switch engines multiple times
        manager.switch_engine("edge_tts")
        manager.switch_engine("gtts")
        manager.switch_engine("kokoro")

        # Should complete quickly (< 1 second for all switches)
        elapsed = time.time() - start_time
        assert elapsed < 1.0, f"Engine switches took too long: {elapsed}s"
