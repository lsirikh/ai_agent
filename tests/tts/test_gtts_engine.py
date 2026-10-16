"""
gTTS Engine Tests

Phase 10.1.5: Google TTS Engine 구현 테스트
TDD: Red → Green → Refactor
"""
import pytest
import numpy as np


class TestGTTSEngineImplementsInterface:
    """gTTSEngine이 TTSEngine 인터페이스를 구현하는지 테스트"""

    def test_gtts_engine_implements_interface(self):
        """gTTSEngine이 TTSEngine 추상 클래스를 상속하는지 확인"""
        from services.tts.app.engines.base import TTSEngine
        from services.tts.app.engines.gtts_engine import GTTSEngine

        assert issubclass(GTTSEngine, TTSEngine)

    def test_gtts_engine_can_be_instantiated(self):
        """gTTSEngine이 인스턴스화될 수 있는지 확인"""
        from services.tts.app.engines.gtts_engine import GTTSEngine

        engine = GTTSEngine()
        assert engine is not None

    def test_gtts_engine_properties(self):
        """gTTSEngine의 속성이 올바른지 확인"""
        from services.tts.app.engines.gtts_engine import GTTSEngine

        engine = GTTSEngine()

        assert engine.name == "gtts"
        assert engine.display_name == "Google TTS"
        assert engine.sample_rate == 22050  # gTTS 기본 샘플 레이트
        assert "ko" in engine.supported_languages
        assert engine.requires_gpu is False
        assert engine.requires_internet is True


class TestGTTSEngineSynthesize:
    """gTTSEngine 합성 기능 테스트"""

    def test_gtts_engine_synthesize(self):
        """gTTSEngine.synthesize()가 올바른 오디오를 반환하는지 확인"""
        from services.tts.app.engines.gtts_engine import GTTSEngine

        engine = GTTSEngine()
        audio = engine.synthesize("안녕하세요")

        assert isinstance(audio, np.ndarray)
        assert audio.dtype == np.float32

    def test_gtts_engine_synthesize_empty_text(self):
        """빈 텍스트에 대해 빈 배열 반환"""
        from services.tts.app.engines.gtts_engine import GTTSEngine

        engine = GTTSEngine()
        audio = engine.synthesize("")

        assert isinstance(audio, np.ndarray)
        assert len(audio) == 0

    def test_gtts_engine_get_available_voices(self):
        """get_available_voices()가 올바른 형식을 반환하는지 확인"""
        from services.tts.app.engines.gtts_engine import GTTSEngine

        engine = GTTSEngine()
        voices = engine.get_available_voices()

        assert isinstance(voices, list)
        assert len(voices) > 0

        for voice in voices:
            assert "id" in voice
            assert "name" in voice
            assert "language" in voice

    def test_gtts_engine_is_available(self):
        """is_available()이 올바르게 동작하는지 확인"""
        from services.tts.app.engines.gtts_engine import GTTSEngine

        engine = GTTSEngine()
        result = engine.is_available()

        assert isinstance(result, bool)
