"""
LLM Models Catalog Tests

Phase 10.3.1: LLM 모델 카탈로그 테스트
TDD: Red → Green → Refactor
"""
import pytest


class TestLLMModelsDict:
    """LLM_MODELS 딕셔너리 테스트"""

    def test_llm_models_dict(self):
        """LLM_MODELS 딕셔너리가 존재하는지 확인"""
        from services.backend.app.models.llm_models import LLM_MODELS

        assert isinstance(LLM_MODELS, dict)
        assert len(LLM_MODELS) > 0


class TestLLMModelsIncludesQwen:
    """Qwen 모델 포함 테스트"""

    def test_llm_models_includes_qwen(self):
        """LLM_MODELS에 Qwen 모델이 포함되어 있는지 확인"""
        from services.backend.app.models.llm_models import LLM_MODELS

        qwen_models = [k for k in LLM_MODELS.keys() if "qwen" in k.lower()]
        assert len(qwen_models) > 0

        # Qwen 모델 정보 확인
        for model_id in qwen_models:
            model = LLM_MODELS[model_id]
            assert "display_name" in model
            assert "vram_gb" in model
            assert "context_length" in model


class TestLLMModelsIncludesPhi4:
    """Phi-4 모델 포함 테스트"""

    def test_llm_models_includes_phi4(self):
        """LLM_MODELS에 Phi-4 모델이 포함되어 있는지 확인"""
        from services.backend.app.models.llm_models import LLM_MODELS

        phi_models = [k for k in LLM_MODELS.keys() if "phi" in k.lower()]
        assert len(phi_models) > 0

        # Phi 모델 정보 확인
        for model_id in phi_models:
            model = LLM_MODELS[model_id]
            assert "display_name" in model
            assert "vram_gb" in model


class TestLLMModelsIncludesDeepSeekR1:
    """DeepSeek R1 모델 포함 테스트"""

    def test_llm_models_includes_deepseek_r1(self):
        """LLM_MODELS에 DeepSeek R1 모델이 포함되어 있는지 확인"""
        from services.backend.app.models.llm_models import LLM_MODELS

        deepseek_models = [k for k in LLM_MODELS.keys() if "deepseek" in k.lower()]
        assert len(deepseek_models) > 0

        # DeepSeek 모델 정보 확인
        for model_id in deepseek_models:
            model = LLM_MODELS[model_id]
            assert "display_name" in model
            assert "vram_gb" in model


class TestGetModelsByVram:
    """VRAM으로 필터링 테스트"""

    def test_get_models_by_vram(self):
        """VRAM으로 모델 필터링이 가능한지 확인"""
        from services.backend.app.models.llm_models import get_models_by_vram

        # 8GB 이하 모델 필터링
        small_models = get_models_by_vram(max_vram=8)
        assert isinstance(small_models, list)

        # 모든 필터링된 모델이 8GB 이하인지 확인
        for model in small_models:
            assert model["vram_gb"] <= 8

    def test_get_models_by_vram_returns_sorted(self):
        """VRAM 필터링 결과가 정렬되어 있는지 확인"""
        from services.backend.app.models.llm_models import get_models_by_vram

        models = get_models_by_vram(max_vram=16)

        # VRAM 기준 오름차순 정렬 확인
        vram_values = [m["vram_gb"] for m in models]
        assert vram_values == sorted(vram_values)


class TestLLMModelInfo:
    """LLM 모델 정보 구조 테스트"""

    def test_llm_model_has_required_fields(self):
        """모든 LLM 모델이 필수 필드를 가지고 있는지 확인"""
        from services.backend.app.models.llm_models import LLM_MODELS

        required_fields = [
            "display_name",
            "vram_gb",
            "context_length",
            "korean_quality",
            "recommended_for"
        ]

        for model_id, model in LLM_MODELS.items():
            for field in required_fields:
                assert field in model, f"Model {model_id} missing field: {field}"
