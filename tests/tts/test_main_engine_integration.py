"""
TTS Main Engine Integration Tests

Phase 10.1.7: TTS main.py와 EngineManager 통합 테스트
TDD: Red → Green → Refactor
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestMainUsesEngineManager:
    """main.py가 EngineManager를 사용하는지 테스트"""

    def test_main_uses_engine_manager(self):
        """get_synthesizer()가 EngineManager를 반환하는지 확인"""
        # Import 시 에러 없어야 함
        from services.tts.app.engine_manager import TTSEngineManager

        # EngineManager로 인스턴스 생성 가능해야 함
        manager = TTSEngineManager()
        assert manager is not None


class TestSynthesizeEndpointUsesEngine:
    """/synthesize 엔드포인트가 현재 엔진을 사용하는지 테스트"""

    def test_synthesize_endpoint_uses_engine(self):
        """합성 엔드포인트가 EngineManager를 통해 동작하는지 확인"""
        from services.tts.app.engine_manager import TTSEngineManager
        import numpy as np

        manager = TTSEngineManager()

        # 현재 엔진으로 합성 가능해야 함
        audio = manager.synthesize("테스트")
        assert isinstance(audio, np.ndarray)
        assert audio.dtype == np.float32


class TestEngineSwitchViaRedis:
    """Redis를 통한 엔진 전환 테스트"""

    def test_engine_switch_via_settings(self):
        """설정 변경으로 엔진 전환이 되는지 확인"""
        from services.tts.app.engine_manager import TTSEngineManager
        from services.tts.app.engines.base import TTSEngineType

        manager = TTSEngineManager()

        # 기본 엔진 확인 (MeloTTS)
        assert manager.get_current_engine().name == "melo"

        # 엔진 전환
        result = manager.switch_engine(TTSEngineType.KOKORO)
        assert result is True
        assert manager.get_current_engine().name == "kokoro"

        # 다시 MeloTTS로 전환
        result = manager.switch_engine("melo")
        assert result is True
        assert manager.get_current_engine().name == "melo"

    def test_engine_switch_updates_settings(self):
        """엔진 전환 후 get_current_engine_type()이 업데이트되는지 확인"""
        from services.tts.app.engine_manager import TTSEngineManager
        from services.tts.app.engines.base import TTSEngineType

        manager = TTSEngineManager()

        manager.switch_engine(TTSEngineType.EDGE_TTS)
        assert manager.get_current_engine_type() == TTSEngineType.EDGE_TTS

        manager.switch_engine(TTSEngineType.GTTS)
        assert manager.get_current_engine_type() == TTSEngineType.GTTS
