"""
TTS Engine Manager Tests

Phase 10.1.6: TTS Engine Manager 구현 테스트
TDD: Red → Green → Refactor
"""
import pytest
import numpy as np


class TestEngineManagerInitialization:
    """TTSEngineManager 초기화 테스트"""

    def test_engine_manager_initialization(self):
        """TTSEngineManager가 올바르게 초기화되는지 확인"""
        from services.tts.app.engine_manager import TTSEngineManager

        manager = TTSEngineManager()
        assert manager is not None

    def test_engine_manager_has_default_engine(self):
        """TTSEngineManager가 기본 엔진을 가지고 있는지 확인"""
        from services.tts.app.engine_manager import TTSEngineManager

        manager = TTSEngineManager()
        engine = manager.get_current_engine()
        assert engine is not None


class TestEngineManagerGetEngine:
    """TTSEngineManager 엔진 조회 테스트"""

    def test_engine_manager_get_engine(self):
        """특정 엔진을 조회할 수 있는지 확인"""
        from services.tts.app.engine_manager import TTSEngineManager
        from services.tts.app.engines.base import TTSEngineType

        manager = TTSEngineManager()

        # MeloTTS 엔진 조회
        engine = manager.get_engine(TTSEngineType.MELO)
        assert engine is not None
        assert engine.name == "melo"

    def test_engine_manager_get_engine_by_string(self):
        """문자열로 엔진을 조회할 수 있는지 확인"""
        from services.tts.app.engine_manager import TTSEngineManager

        manager = TTSEngineManager()

        engine = manager.get_engine("kokoro")
        assert engine is not None
        assert engine.name == "kokoro"


class TestEngineManagerSwitchEngine:
    """TTSEngineManager 엔진 전환 테스트"""

    def test_engine_manager_switch_engine(self):
        """엔진을 전환할 수 있는지 확인 (hot-swap)"""
        from services.tts.app.engine_manager import TTSEngineManager
        from services.tts.app.engines.base import TTSEngineType

        manager = TTSEngineManager()

        # MeloTTS로 전환
        result = manager.switch_engine(TTSEngineType.MELO)
        assert result is True
        assert manager.get_current_engine().name == "melo"

        # Kokoro로 전환
        result = manager.switch_engine(TTSEngineType.KOKORO)
        assert result is True
        assert manager.get_current_engine().name == "kokoro"

    def test_engine_manager_switch_invalid_engine(self):
        """잘못된 엔진 타입으로 전환 시 실패하는지 확인"""
        from services.tts.app.engine_manager import TTSEngineManager

        manager = TTSEngineManager()

        result = manager.switch_engine("invalid_engine")
        assert result is False


class TestEngineManagerListEngines:
    """TTSEngineManager 엔진 목록 조회 테스트"""

    def test_engine_manager_list_engines(self):
        """사용 가능한 엔진 목록을 조회할 수 있는지 확인"""
        from services.tts.app.engine_manager import TTSEngineManager

        manager = TTSEngineManager()
        engines = manager.list_engines()

        assert isinstance(engines, list)
        assert len(engines) >= 4  # melo, kokoro, gtts, edge_tts

        # 각 엔진 정보 확인
        engine_names = [e["name"] for e in engines]
        assert "melo" in engine_names
        assert "kokoro" in engine_names
        assert "gtts" in engine_names
        assert "edge_tts" in engine_names


class TestEngineManagerDefaultEngine:
    """TTSEngineManager 기본 엔진 테스트"""

    def test_engine_manager_default_engine(self):
        """기본 엔진이 MeloTTS인지 확인"""
        from services.tts.app.engine_manager import TTSEngineManager

        manager = TTSEngineManager()
        engine = manager.get_current_engine()

        assert engine.name == "melo"

    def test_engine_manager_synthesize_with_current_engine(self):
        """현재 엔진으로 합성이 되는지 확인"""
        from services.tts.app.engine_manager import TTSEngineManager

        manager = TTSEngineManager()
        audio = manager.synthesize("테스트")

        assert isinstance(audio, np.ndarray)
        assert audio.dtype == np.float32
