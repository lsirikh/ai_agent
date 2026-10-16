"""
Kokoro TTS Engine Tests

Phase 10.1.3: Kokoro Engine 리팩토링 테스트
TDD: Red → Green → Refactor
"""
import pytest
import numpy as np


class TestKokoroEngineImplementsInterface:
    """KokoroTTSEngine이 TTSEngine 인터페이스를 구현하는지 테스트"""

    def test_kokoro_engine_implements_interface(self):
        """KokoroTTSEngine이 TTSEngine 추상 클래스를 상속하는지 확인"""
        from services.tts.app.engines.base import TTSEngine
        from services.tts.app.engines.kokoro_engine import KokoroTTSEngine

        assert issubclass(KokoroTTSEngine, TTSEngine)

    def test_kokoro_engine_can_be_instantiated(self):
        """KokoroTTSEngine이 인스턴스화될 수 있는지 확인"""
        from services.tts.app.engines.kokoro_engine import KokoroTTSEngine

        engine = KokoroTTSEngine()
        assert engine is not None

    def test_kokoro_engine_properties(self):
        """KokoroTTSEngine의 속성이 올바른지 확인"""
        from services.tts.app.engines.kokoro_engine import KokoroTTSEngine

        engine = KokoroTTSEngine()

        assert engine.name == "kokoro"
        assert engine.display_name == "Kokoro TTS"
        assert engine.sample_rate == 24000
        assert "en" in engine.supported_languages
        assert engine.requires_internet is False


class TestKokoroEngineSynthesize:
    """KokoroTTSEngine 합성 기능 테스트"""

    def test_kokoro_engine_synthesize(self):
        """KokoroTTSEngine.synthesize()가 올바른 오디오를 반환하는지 확인"""
        from services.tts.app.engines.kokoro_engine import KokoroTTSEngine

        engine = KokoroTTSEngine()
        audio = engine.synthesize("Hello, world!")

        assert isinstance(audio, np.ndarray)
        assert audio.dtype == np.float32

    def test_kokoro_engine_synthesize_empty_text(self):
        """빈 텍스트에 대해 빈 배열 반환"""
        from services.tts.app.engines.kokoro_engine import KokoroTTSEngine

        engine = KokoroTTSEngine()
        audio = engine.synthesize("")

        assert isinstance(audio, np.ndarray)
        assert len(audio) == 0


class TestKokoroEngineVoiceSelection:
    """KokoroTTSEngine 음성 선택 테스트"""

    def test_kokoro_engine_voice_selection(self):
        """음성 선택이 작동하는지 확인"""
        from services.tts.app.engines.kokoro_engine import KokoroTTSEngine

        engine = KokoroTTSEngine()
        voices = engine.get_available_voices()

        assert isinstance(voices, list)
        assert len(voices) > 0

        # 각 음성 항목 구조 확인
        for voice in voices:
            assert "id" in voice
            assert "name" in voice
            assert "language" in voice

    def test_kokoro_engine_synthesize_with_voice(self):
        """특정 음성으로 합성이 가능한지 확인"""
        from services.tts.app.engines.kokoro_engine import KokoroTTSEngine

        engine = KokoroTTSEngine()
        voices = engine.get_available_voices()

        if len(voices) > 0:
            audio = engine.synthesize("Test", voice=voices[0]["id"])
            assert isinstance(audio, np.ndarray)
