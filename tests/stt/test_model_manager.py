"""
STT Model Manager Tests

Phase 10.2: STT Model Manager 구현 테스트
TDD: Red → Green → Refactor
"""
import pytest
from enum import Enum


class TestWhisperModelSizeEnum:
    """WhisperModelSize enum 테스트"""

    def test_whisper_model_size_enum(self):
        """WhisperModelSize enum이 올바르게 정의되어 있는지 확인"""
        from services.stt.app.model_manager import WhisperModelSize

        assert issubclass(WhisperModelSize, str)
        assert issubclass(WhisperModelSize, Enum)

        # 기본 모델들 확인
        assert WhisperModelSize.TINY == "tiny"
        assert WhisperModelSize.BASE == "base"
        assert WhisperModelSize.SMALL == "small"
        assert WhisperModelSize.MEDIUM == "medium"
        assert WhisperModelSize.LARGE_V3 == "large-v3"
        assert WhisperModelSize.LARGE_V3_TURBO == "large-v3-turbo"


class TestModelInfoDict:
    """MODEL_INFO 딕셔너리 테스트"""

    def test_model_info_dict(self):
        """MODEL_INFO가 올바른 구조를 가지는지 확인"""
        from services.stt.app.model_manager import STTModelManager

        manager = STTModelManager()

        # MODEL_INFO 존재 확인
        assert hasattr(manager, 'MODEL_INFO')

        # 필수 모델 존재 확인
        assert "tiny" in manager.MODEL_INFO
        assert "small" in manager.MODEL_INFO
        assert "large-v3" in manager.MODEL_INFO
        assert "large-v3-turbo" in manager.MODEL_INFO

        # 모델 정보 구조 확인
        for model_id, info in manager.MODEL_INFO.items():
            assert "display_name" in info
            assert "size_mb" in info
            assert "vram_gb" in info


class TestKoreanModelIncluded:
    """한국어 최적화 모델 포함 테스트"""

    def test_korean_model_included(self):
        """한국어 파인튜닝 모델이 포함되어 있는지 확인"""
        from services.stt.app.model_manager import STTModelManager

        manager = STTModelManager()

        # 한국어 최적화 모델 확인
        korean_model_id = "ghost613/faster-whisper-large-v3-turbo-korean"
        assert korean_model_id in manager.MODEL_INFO

        korean_info = manager.MODEL_INFO[korean_model_id]
        assert "korean" in korean_info.get("recommended_for", "").lower() or \
               "korean" in korean_info.get("display_name", "").lower()


class TestSTTModelManagerInitialization:
    """STTModelManager 초기화 테스트"""

    def test_stt_model_manager_initialization(self):
        """STTModelManager가 올바르게 초기화되는지 확인"""
        from services.stt.app.model_manager import STTModelManager

        manager = STTModelManager()
        assert manager is not None
        assert manager.get_current_model_name() is not None


class TestSTTModelManagerLoadModel:
    """STTModelManager 모델 로드 테스트"""

    def test_stt_model_manager_load_model(self):
        """모델 로드가 성공하는지 확인 (실제 로드 없이 설정만 확인)"""
        from services.stt.app.model_manager import STTModelManager

        manager = STTModelManager()

        # 로드 전 현재 모델 확인
        current = manager.get_current_model_name()
        assert current in manager.MODEL_INFO


class TestSTTModelManagerHotSwap:
    """STTModelManager hot-swap 테스트"""

    def test_stt_model_manager_hot_swap(self):
        """모델 hot-swap이 가능한지 확인"""
        from services.stt.app.model_manager import STTModelManager

        manager = STTModelManager()

        # 모델 전환 시도
        result = manager.switch_model("tiny")
        assert result is True
        assert manager.get_current_model_name() == "tiny"

        result = manager.switch_model("small")
        assert result is True
        assert manager.get_current_model_name() == "small"

    def test_stt_model_manager_invalid_model(self):
        """잘못된 모델로 전환 시 실패하는지 확인"""
        from services.stt.app.model_manager import STTModelManager

        manager = STTModelManager()

        result = manager.switch_model("invalid_model")
        assert result is False


class TestSTTModelManagerGetAvailableModels:
    """사용 가능한 모델 목록 조회 테스트"""

    def test_stt_model_manager_get_available_models(self):
        """사용 가능한 모델 목록을 조회할 수 있는지 확인"""
        from services.stt.app.model_manager import STTModelManager

        manager = STTModelManager()
        models = manager.get_available_models()

        assert isinstance(models, list)
        assert len(models) >= 7  # tiny, base, small, medium, large-v3, large-v3-turbo, korean

        # 모델 정보 구조 확인
        for model in models:
            assert "id" in model
            assert "display_name" in model


class TestSTTModelManagerGetCurrentModel:
    """현재 모델 조회 테스트"""

    def test_stt_model_manager_get_current_model(self):
        """현재 모델을 조회할 수 있는지 확인"""
        from services.stt.app.model_manager import STTModelManager

        manager = STTModelManager()
        current = manager.get_current_model_name()

        assert isinstance(current, str)
        assert current in manager.MODEL_INFO
