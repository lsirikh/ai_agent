"""
STT Model Manager

Phase 10.2: 동적 Whisper 모델 관리자 구현
"""
import gc
import os
from enum import Enum
from typing import Dict, List, Optional, Any


class WhisperModelSize(str, Enum):
    """Whisper 모델 크기 열거형"""
    TINY = "tiny"
    BASE = "base"
    SMALL = "small"
    MEDIUM = "medium"
    LARGE_V2 = "large-v2"
    LARGE_V3 = "large-v3"
    LARGE_V3_TURBO = "large-v3-turbo"
    LARGE_V3_TURBO_KOREAN = "ghost613/faster-whisper-large-v3-turbo-korean"


class STTModelManager:
    """STT 모델 동적 관리자

    특징:
    - Hot-swap: 모델 전환 가능 (메모리 해제 후 새 모델 로드)
    - 모델 정보 제공: VRAM, 속도, 한국어 품질 등
    - 한국어 최적화 모델 지원
    """

    MODEL_INFO = {
        "tiny": {
            "display_name": "Tiny",
            "size_mb": 39,
            "vram_gb": 1,
            "relative_speed": 32,
            "korean_quality": "낮음",
            "recommended_for": "빠른 테스트용"
        },
        "base": {
            "display_name": "Base",
            "size_mb": 74,
            "vram_gb": 1,
            "relative_speed": 16,
            "korean_quality": "낮음",
            "recommended_for": "기본 용도"
        },
        "small": {
            "display_name": "Small",
            "size_mb": 244,
            "vram_gb": 2,
            "relative_speed": 6,
            "korean_quality": "중간",
            "recommended_for": "균형 잡힌 성능"
        },
        "medium": {
            "display_name": "Medium",
            "size_mb": 769,
            "vram_gb": 5,
            "relative_speed": 2,
            "korean_quality": "좋음",
            "recommended_for": "고품질 필요 시"
        },
        "large-v2": {
            "display_name": "Large V2",
            "size_mb": 1550,
            "vram_gb": 10,
            "relative_speed": 1,
            "korean_quality": "매우 좋음",
            "recommended_for": "최고 품질"
        },
        "large-v3": {
            "display_name": "Large V3",
            "size_mb": 1550,
            "vram_gb": 10,
            "relative_speed": 1,
            "korean_quality": "매우 좋음",
            "recommended_for": "최고 품질"
        },
        "large-v3-turbo": {
            "display_name": "Large V3 Turbo",
            "size_mb": 809,
            "vram_gb": 6,
            "relative_speed": 5.4,
            "korean_quality": "좋음",
            "recommended_for": "속도/품질 균형"
        },
        "ghost613/faster-whisper-large-v3-turbo-korean": {
            "display_name": "Large V3 Turbo Korean",
            "size_mb": 809,
            "vram_gb": 6,
            "relative_speed": 5.4,
            "korean_quality": "매우 좋음",
            "recommended_for": "한국어 최적화 (권장)"
        }
    }

    def __init__(
        self,
        default_model: str = "small",
        device: Optional[str] = None,
        compute_type: Optional[str] = None
    ):
        """
        STTModelManager 초기화

        Args:
            default_model: 기본 모델 이름
            device: 장치 (cpu, cuda)
            compute_type: 컴퓨팅 타입 (int8, float16, float32)
        """
        self._current_model_name = default_model
        self._device = device or os.getenv("DEVICE", "cpu")
        self._compute_type = compute_type or os.getenv("COMPUTE_TYPE", "int8")
        self._model = None
        self._initialized = False

    def get_current_model_name(self) -> str:
        """현재 모델 이름 조회

        Returns:
            현재 모델 이름
        """
        return self._current_model_name

    def switch_model(self, model_name: str) -> bool:
        """모델 전환 (hot-swap)

        Args:
            model_name: 새 모델 이름

        Returns:
            True: 전환 성공, False: 전환 실패
        """
        if model_name not in self.MODEL_INFO:
            return False

        # 이전 모델 해제
        if self._model is not None:
            del self._model
            self._model = None
            gc.collect()

            # CUDA 메모리 해제
            if self._device == "cuda":
                try:
                    import torch
                    torch.cuda.empty_cache()
                except ImportError:
                    pass

        self._current_model_name = model_name
        self._initialized = False

        print(f"[STT] Model switched to: {model_name}")
        return True

    def load_model(self) -> bool:
        """현재 설정된 모델 로드

        Returns:
            True: 로드 성공, False: 로드 실패
        """
        if self._initialized and self._model is not None:
            return True

        try:
            from faster_whisper import WhisperModel

            print(f"[STT] Loading model: {self._current_model_name}")

            self._model = WhisperModel(
                self._current_model_name,
                device=self._device,
                compute_type=self._compute_type
            )
            self._initialized = True

            print(f"[STT] Model loaded: {self._current_model_name}")
            return True

        except Exception as e:
            print(f"[STT] Model load failed: {e}")
            return False

    def get_model(self) -> Optional[Any]:
        """현재 모델 인스턴스 조회

        Returns:
            WhisperModel 인스턴스 또는 None
        """
        if not self._initialized:
            self.load_model()
        return self._model

    def get_available_models(self) -> List[dict]:
        """사용 가능한 모델 목록 조회

        Returns:
            모델 정보 리스트
        """
        return [
            {
                "id": model_id,
                **info,
                "is_current": model_id == self._current_model_name
            }
            for model_id, info in self.MODEL_INFO.items()
        ]

    def get_model_info(self, model_name: Optional[str] = None) -> Optional[dict]:
        """특정 모델 정보 조회

        Args:
            model_name: 모델 이름 (None이면 현재 모델)

        Returns:
            모델 정보 딕셔너리 또는 None
        """
        name = model_name or self._current_model_name
        return self.MODEL_INFO.get(name)

    def get_device(self) -> str:
        """현재 장치 조회

        Returns:
            장치 문자열 (cpu, cuda)
        """
        return self._device

    def get_compute_type(self) -> str:
        """현재 컴퓨팅 타입 조회

        Returns:
            컴퓨팅 타입 문자열
        """
        return self._compute_type
