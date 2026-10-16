"""
MeloTTS Engine Tests

Phase 10.1.2: MeloTTS Engine 구현 테스트
TDD: Red → Green → Refactor
"""
import pytest
import numpy as np
from unittest.mock import patch, MagicMock


class TestMeloEngineImplementsInterface:
    """MeloTTSEngine이 TTSEngine 인터페이스를 구현하는지 테스트"""

    def test_melo_engine_implements_interface(self):
        """MeloTTSEngine이 TTSEngine 추상 클래스를 상속하는지 확인"""
        from services.tts.app.engines.base import TTSEngine
        from services.tts.app.engines.melo_engine import MeloTTSEngine

        assert issubclass(MeloTTSEngine, TTSEngine)

    def test_melo_engine_can_be_instantiated(self):
        """MeloTTSEngine이 인스턴스화될 수 있는지 확인"""
        from services.tts.app.engines.melo_engine import MeloTTSEngine

        engine = MeloTTSEngine()
        assert engine is not None


class TestMeloEngineNameAndProperties:
    """MeloTTSEngine 속성 테스트"""

    def test_melo_engine_name_and_properties(self):
        """MeloTTSEngine의 이름과 속성이 올바른지 확인"""
        from services.tts.app.engines.melo_engine import MeloTTSEngine

        engine = MeloTTSEngine()

        # 기본 속성 확인
        assert engine.name == "melo"
        assert engine.display_name == "MeloTTS Korean"
        assert engine.sample_rate == 44100
        assert "ko" in engine.supported_languages
        assert engine.requires_gpu is False  # CPU도 지원
        assert engine.requires_internet is False


class TestMeloEngineMecabPatch:
    """MeCab 패치 테스트"""

    def test_melo_engine_mecab_patch(self):
        """MeCab 패치가 g2pkk 모듈에 적용되는지 확인"""
        from services.tts.app.engines.melo_engine import MeloTTSEngine

        engine = MeloTTSEngine()

        # 패치 적용 후 g2pkk 모듈 확인
        # _apply_mecab_patch가 내부적으로 호출되어야 함
        # 실제 동작은 melo 모델 로드 시 확인
        assert hasattr(engine, '_apply_mecab_patch')
        assert callable(engine._apply_mecab_patch)


class TestMeloEngineSynthesize:
    """MeloTTSEngine 합성 기능 테스트"""

    def test_melo_engine_synthesize(self):
        """MeloTTSEngine.synthesize()가 올바른 오디오를 반환하는지 확인"""
        from services.tts.app.engines.melo_engine import MeloTTSEngine

        engine = MeloTTSEngine()

        # 모델이 없는 경우 더미 오디오 반환 테스트
        audio = engine.synthesize("안녕하세요")

        # 반환 타입 확인
        assert isinstance(audio, np.ndarray)
        assert audio.dtype == np.float32

    def test_melo_engine_synthesize_empty_text(self):
        """빈 텍스트에 대해 빈 배열 반환"""
        from services.tts.app.engines.melo_engine import MeloTTSEngine

        engine = MeloTTSEngine()
        audio = engine.synthesize("")

        assert isinstance(audio, np.ndarray)
        assert len(audio) == 0

    def test_melo_engine_synthesize_with_speed(self):
        """속도 조절 파라미터가 적용되는지 확인"""
        from services.tts.app.engines.melo_engine import MeloTTSEngine

        engine = MeloTTSEngine()

        # 속도 파라미터를 받아들이는지 확인
        audio = engine.synthesize("테스트", speed=1.5)
        assert isinstance(audio, np.ndarray)


class TestMeloEngineIsAvailable:
    """MeloTTSEngine 사용 가능 여부 테스트"""

    def test_melo_engine_is_available_returns_bool(self):
        """is_available()이 bool을 반환하는지 확인"""
        from services.tts.app.engines.melo_engine import MeloTTSEngine

        engine = MeloTTSEngine()
        result = engine.is_available()

        assert isinstance(result, bool)

    def test_melo_engine_get_available_voices(self):
        """get_available_voices()가 올바른 형식을 반환하는지 확인"""
        from services.tts.app.engines.melo_engine import MeloTTSEngine

        engine = MeloTTSEngine()
        voices = engine.get_available_voices()

        assert isinstance(voices, list)
        if len(voices) > 0:
            assert "id" in voices[0]
            assert "name" in voices[0]
            assert "language" in voices[0]
