"""
Edge-TTS Engine Tests

Phase 10.1.4: Edge-TTS Engine 구현 테스트
TDD: Red → Green → Refactor
"""
import pytest
import numpy as np


class TestEdgeTTSEngineImplementsInterface:
    """EdgeTTSEngine이 TTSEngine 인터페이스를 구현하는지 테스트"""

    def test_edge_tts_engine_implements_interface(self):
        """EdgeTTSEngine이 TTSEngine 추상 클래스를 상속하는지 확인"""
        from services.tts.app.engines.base import TTSEngine
        from services.tts.app.engines.edge_tts_engine import EdgeTTSEngine

        assert issubclass(EdgeTTSEngine, TTSEngine)

    def test_edge_tts_engine_can_be_instantiated(self):
        """EdgeTTSEngine이 인스턴스화될 수 있는지 확인"""
        from services.tts.app.engines.edge_tts_engine import EdgeTTSEngine

        engine = EdgeTTSEngine()
        assert engine is not None

    def test_edge_tts_engine_properties(self):
        """EdgeTTSEngine의 속성이 올바른지 확인"""
        from services.tts.app.engines.edge_tts_engine import EdgeTTSEngine

        engine = EdgeTTSEngine()

        assert engine.name == "edge_tts"
        assert engine.display_name == "Microsoft Edge TTS"
        assert engine.sample_rate == 24000
        assert "ko" in engine.supported_languages
        assert "en" in engine.supported_languages
        assert engine.requires_gpu is False
        assert engine.requires_internet is True


class TestEdgeTTSEngineSynthesize:
    """EdgeTTSEngine 합성 기능 테스트"""

    def test_edge_tts_engine_synthesize(self):
        """EdgeTTSEngine.synthesize()가 올바른 오디오를 반환하는지 확인"""
        from services.tts.app.engines.edge_tts_engine import EdgeTTSEngine

        engine = EdgeTTSEngine()
        audio = engine.synthesize("안녕하세요")

        assert isinstance(audio, np.ndarray)
        assert audio.dtype == np.float32

    def test_edge_tts_engine_synthesize_empty_text(self):
        """빈 텍스트에 대해 빈 배열 반환"""
        from services.tts.app.engines.edge_tts_engine import EdgeTTSEngine

        engine = EdgeTTSEngine()
        audio = engine.synthesize("")

        assert isinstance(audio, np.ndarray)
        assert len(audio) == 0


class TestEdgeTTSEngineKoreanVoices:
    """EdgeTTSEngine 한국어 음성 테스트"""

    def test_edge_tts_engine_korean_voices(self):
        """한국어 음성이 포함되어 있는지 확인"""
        from services.tts.app.engines.edge_tts_engine import EdgeTTSEngine

        engine = EdgeTTSEngine()
        voices = engine.get_available_voices()

        assert isinstance(voices, list)
        assert len(voices) > 0

        # 한국어 음성 확인
        korean_voices = [v for v in voices if v.get("language") == "ko"]
        assert len(korean_voices) > 0

        # 음성 구조 확인
        for voice in voices:
            assert "id" in voice
            assert "name" in voice
            assert "language" in voice

    def test_edge_tts_engine_is_available(self):
        """is_available()이 올바르게 동작하는지 확인"""
        from services.tts.app.engines.edge_tts_engine import EdgeTTSEngine

        engine = EdgeTTSEngine()
        result = engine.is_available()

        assert isinstance(result, bool)
