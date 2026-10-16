"""
TTS Engine Base Class Tests

Phase 10.1.1: TTSEngine 추상 기본 클래스 테스트
TDD: Red → Green → Refactor
"""
import pytest
from abc import ABC
from enum import Enum
import numpy as np


class TestTTSEngineAbstractClass:
    """TTSEngine 추상 클래스 정의 테스트"""

    def test_tts_engine_abstract_class(self):
        """TTSEngine이 ABC를 상속하는 추상 클래스인지 확인"""
        from services.tts.app.engines.base import TTSEngine

        # TTSEngine은 ABC를 상속해야 함
        assert issubclass(TTSEngine, ABC)

        # TTSEngine을 직접 인스턴스화할 수 없어야 함
        with pytest.raises(TypeError):
            TTSEngine()

    def test_tts_engine_has_abstract_methods(self):
        """TTSEngine이 필수 추상 메서드를 정의하는지 확인"""
        from services.tts.app.engines.base import TTSEngine
        import inspect

        # 추상 메서드 목록
        abstract_methods = [
            'name',
            'display_name',
            'sample_rate',
            'supported_languages',
            'requires_gpu',
            'requires_internet',
            'synthesize',
            'get_available_voices',
            'is_available',
        ]

        # 모든 추상 메서드가 정의되어 있는지 확인
        for method_name in abstract_methods:
            assert hasattr(TTSEngine, method_name), f"TTSEngine should have {method_name}"


class TestTTSEngineTypeEnum:
    """TTSEngineType enum 정의 테스트"""

    def test_tts_engine_type_enum(self):
        """TTSEngineType enum이 올바르게 정의되어 있는지 확인"""
        from services.tts.app.engines.base import TTSEngineType

        # Enum 타입인지 확인
        assert issubclass(TTSEngineType, str)
        assert issubclass(TTSEngineType, Enum)

        # 필수 엔진 타입 확인
        assert TTSEngineType.MELO == "melo"
        assert TTSEngineType.KOKORO == "kokoro"
        assert TTSEngineType.GTTS == "gtts"
        assert TTSEngineType.EDGE_TTS == "edge_tts"

    def test_tts_engine_type_values(self):
        """TTSEngineType enum 값들이 문자열인지 확인"""
        from services.tts.app.engines.base import TTSEngineType

        for engine_type in TTSEngineType:
            assert isinstance(engine_type.value, str)


class TestTTSEngineGetInfoMethod:
    """TTSEngine get_info() 메서드 테스트"""

    def test_tts_engine_get_info_method(self):
        """get_info() 메서드가 올바른 정보를 반환하는지 확인"""
        from services.tts.app.engines.base import TTSEngine
        from typing import List

        # 구체적인 테스트용 구현 클래스 생성
        class MockTTSEngine(TTSEngine):
            @property
            def name(self) -> str:
                return "mock"

            @property
            def display_name(self) -> str:
                return "Mock TTS Engine"

            @property
            def sample_rate(self) -> int:
                return 24000

            @property
            def supported_languages(self) -> List[str]:
                return ["ko", "en"]

            @property
            def requires_gpu(self) -> bool:
                return False

            @property
            def requires_internet(self) -> bool:
                return False

            def synthesize(self, text: str, voice=None, speed=1.0) -> np.ndarray:
                return np.zeros(1000, dtype=np.float32)

            def get_available_voices(self) -> List[dict]:
                return [{"id": "default", "name": "Default Voice", "language": "ko"}]

            def is_available(self) -> bool:
                return True

        engine = MockTTSEngine()
        info = engine.get_info()

        # 필수 키 확인
        assert "name" in info
        assert "display_name" in info
        assert "sample_rate" in info
        assert "supported_languages" in info
        assert "requires_gpu" in info
        assert "requires_internet" in info
        assert "available" in info
        assert "voices" in info

        # 값 확인
        assert info["name"] == "mock"
        assert info["display_name"] == "Mock TTS Engine"
        assert info["sample_rate"] == 24000
        assert info["supported_languages"] == ["ko", "en"]
        assert info["requires_gpu"] is False
        assert info["requires_internet"] is False
        assert info["available"] is True
        assert len(info["voices"]) == 1

    def test_tts_engine_get_info_when_unavailable(self):
        """is_available()이 False일 때 voices가 빈 리스트인지 확인"""
        from services.tts.app.engines.base import TTSEngine
        from typing import List

        class UnavailableTTSEngine(TTSEngine):
            @property
            def name(self) -> str:
                return "unavailable"

            @property
            def display_name(self) -> str:
                return "Unavailable Engine"

            @property
            def sample_rate(self) -> int:
                return 22050

            @property
            def supported_languages(self) -> List[str]:
                return ["en"]

            @property
            def requires_gpu(self) -> bool:
                return True

            @property
            def requires_internet(self) -> bool:
                return False

            def synthesize(self, text: str, voice=None, speed=1.0) -> np.ndarray:
                return np.zeros(100, dtype=np.float32)

            def get_available_voices(self) -> List[dict]:
                return [{"id": "v1", "name": "Voice 1", "language": "en"}]

            def is_available(self) -> bool:
                return False

        engine = UnavailableTTSEngine()
        info = engine.get_info()

        assert info["available"] is False
        assert info["voices"] == []  # 사용 불가능할 때 voices는 빈 리스트
