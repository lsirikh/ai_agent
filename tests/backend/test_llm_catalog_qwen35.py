"""
최신 모델로 교체 (사용자 요청 2026-10-17): Qwen3.5-9B(4-bit, 이미지 입력 내장) 하나로
대화 모델(Qwen2.5-7B)과 비전 모델(Qwen2.5-VL-3B)을 함께 대체한다.
"""


def test_catalog_has_qwen35_9b_as_recommended() -> None:
    from services.backend.app.models.llm_models import LLM_MODELS

    info = LLM_MODELS["qwen3.5-9b"]
    assert info["hf_path"] == "RedHatAI/Qwen3.5-9B-quantized.w4a16"
    assert info["vision"] is True
    assert "권장" in info["recommended_for"]


def test_served_model_maps_to_catalog_entry() -> None:
    from services.backend.app.routes.settings import llm_option_id

    assert llm_option_id("RedHatAI/Qwen3.5-9B-quantized.w4a16") == "qwen3.5-9b"


def test_settings_can_write_qwen35_to_env() -> None:
    # 설정 화면에서 고르면 .env 의 LLM_MODEL 로 쓰인다
    from services.backend.app.services.env_writer import MODEL_ID_MAP

    assert MODEL_ID_MAP["qwen3.5-9b"] == "RedHatAI/Qwen3.5-9B-quantized.w4a16"
