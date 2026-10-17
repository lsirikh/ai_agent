"""
LLM Models Catalog

Phase 10.3.1: LLM 모델 카탈로그 정의
"""
from typing import Dict, List, Any


# ===== Downloaded Models Only (8 models) =====
# These are the models that have been downloaded locally
LLM_MODELS: Dict[str, Dict[str, Any]] = {
    # Qwen3.5 (2026-03, Apache-2.0): 이미지 입력 내장 — 대화·비전을 한 모델로.
    # RedHatAI 4-bit(w4a16) 빌드 ~11GB. vLLM: --tool-call-parser qwen3_coder,
    # --reasoning-parser qwen3, 생각 모드는 끈다(enable_thinking=false)
    "qwen3.5-9b": {
        "display_name": "Qwen 3.5 9B (4-bit, 이미지 이해)",
        "vram_gb": 14,
        "context_length": 16384,
        "korean_quality": "좋음",
        "recommended_for": "대화·도구·이미지 이해 (권장)",
        "quantization": "W4A16",
        "parameters": "9B",
        "vision": True,
        "hf_path": "RedHatAI/Qwen3.5-9B-quantized.w4a16"
    },
    # Qwen 모델 시리즈 (다운로드됨)
    "qwen2.5-3b-instruct": {
        "display_name": "Qwen 2.5 3B Instruct",
        "vram_gb": 2,
        "context_length": 32768,
        "korean_quality": "중간",
        "recommended_for": "경량 환경",
        "quantization": "None",
        "parameters": "3B",
        "hf_path": "Qwen/Qwen2.5-3B-Instruct"
    },
    "qwen2.5-7b-instruct-awq": {
        "display_name": "Qwen 2.5 7B AWQ",
        "vram_gb": 5,
        "context_length": 32768,
        "korean_quality": "좋음",
        "recommended_for": "일반 용도 (이전 기본)",
        "quantization": "AWQ",
        "parameters": "7B",
        "hf_path": "Qwen/Qwen2.5-7B-Instruct-AWQ"
    },
    "qwen2.5-14b-instruct-awq": {
        "display_name": "Qwen 2.5 14B AWQ",
        "vram_gb": 10,
        "context_length": 32768,
        "korean_quality": "좋음",
        "recommended_for": "품질/속도 균형",
        "quantization": "AWQ",
        "parameters": "14B",
        "hf_path": "Qwen/Qwen2.5-14B-Instruct-AWQ"
    },
    "qwen2.5-72b-instruct-awq": {
        "display_name": "Qwen 2.5 72B AWQ",
        "vram_gb": 40,
        "context_length": 32768,
        "korean_quality": "매우 좋음",
        "recommended_for": "최고 품질 응답 (고성능 GPU 필요)",
        "quantization": "AWQ",
        "parameters": "72B",
        "hf_path": "Qwen/Qwen2.5-72B-Instruct-AWQ"
    },

    # Phi-4 모델 (다운로드됨)
    "phi-4-mini-instruct": {
        "display_name": "Phi-4 Mini Instruct",
        "vram_gb": 5,
        "context_length": 16384,
        "korean_quality": "중간",
        "recommended_for": "수학/코딩 특화, 빠른 추론",
        "quantization": "None",
        "parameters": "3.8B",
        "hf_path": "microsoft/Phi-4-mini-instruct"
    },

    # DeepSeek R1 모델 (다운로드됨)
    "deepseek-r1-distill-qwen-7b": {
        "display_name": "DeepSeek R1 Distill Qwen 7B",
        "vram_gb": 5,
        "context_length": 32768,
        "korean_quality": "좋음",
        "recommended_for": "추론 특화 경량 모델",
        "quantization": "None",
        "parameters": "7B",
        "hf_path": "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B"
    },
    "deepseek-r1-distill-qwen-14b": {
        "display_name": "DeepSeek R1 Distill Qwen 14B",
        "vram_gb": 10,
        "context_length": 32768,
        "korean_quality": "좋음",
        "recommended_for": "추론/분석 균형",
        "quantization": "None",
        "parameters": "14B",
        "hf_path": "deepseek-ai/DeepSeek-R1-Distill-Qwen-14B"
    },
    "deepseek-r1-distill-llama-8b": {
        "display_name": "DeepSeek R1 Distill Llama 8B",
        "vram_gb": 6,
        "context_length": 32768,
        "korean_quality": "중간",
        "recommended_for": "Llama 기반 추론",
        "quantization": "None",
        "parameters": "8B",
        "hf_path": "deepseek-ai/DeepSeek-R1-Distill-Llama-8B"
    },
}


def get_models_by_vram(max_vram: int) -> List[Dict[str, Any]]:
    """
    VRAM 제한에 맞는 모델 목록 반환

    Args:
        max_vram: 최대 VRAM (GB)

    Returns:
        VRAM 조건을 만족하는 모델 목록 (VRAM 오름차순 정렬)
    """
    filtered = [
        {"id": model_id, **model_info}
        for model_id, model_info in LLM_MODELS.items()
        if model_info["vram_gb"] <= max_vram
    ]

    # VRAM 기준 오름차순 정렬
    return sorted(filtered, key=lambda x: x["vram_gb"])


def get_all_models() -> List[Dict[str, Any]]:
    """
    모든 LLM 모델 목록 반환

    Returns:
        전체 모델 목록 (VRAM 오름차순 정렬)
    """
    return [
        {"id": model_id, **model_info}
        for model_id, model_info in sorted(
            LLM_MODELS.items(),
            key=lambda x: x[1]["vram_gb"]
        )
    ]
