"""
TTS Engine Base Class

Phase 10.1.1: 추상 기본 클래스 정의
"""
from abc import ABC, abstractmethod
from enum import Enum
from typing import List, Optional

import numpy as np


class TTSEngineType(str, Enum):
    """TTS 엔진 타입 열거형"""
    MELO = "melo"
    KOKORO = "kokoro"
    GTTS = "gtts"
    EDGE_TTS = "edge_tts"


class TTSEngine(ABC):
    """TTS 엔진 추상 기본 클래스"""

    @property
    @abstractmethod
    def name(self) -> str:
        """엔진 이름 (melo, kokoro, gtts, edge_tts)"""
        pass

    @property
    @abstractmethod
    def display_name(self) -> str:
        """표시용 이름"""
        pass

    @property
    @abstractmethod
    def sample_rate(self) -> int:
        """출력 샘플 레이트"""
        pass

    @property
    @abstractmethod
    def supported_languages(self) -> List[str]:
        """지원 언어 목록"""
        pass

    @property
    @abstractmethod
    def requires_gpu(self) -> bool:
        """GPU 필요 여부"""
        pass

    @property
    @abstractmethod
    def requires_internet(self) -> bool:
        """인터넷 필요 여부"""
        pass

    @abstractmethod
    def synthesize(
        self,
        text: str,
        voice: Optional[str] = None,
        speed: float = 1.0
    ) -> np.ndarray:
        """텍스트를 음성으로 합성

        Args:
            text: 합성할 텍스트
            voice: 음성 ID (None이면 기본 음성)
            speed: 발화 속도 (기본 1.0)

        Returns:
            np.ndarray: float32 오디오 데이터
        """
        pass

    @abstractmethod
    def get_available_voices(self) -> List[dict]:
        """사용 가능한 음성 목록 반환

        Returns:
            [{"id": "KR", "name": "Korean Female", "language": "ko"}, ...]
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """엔진 사용 가능 여부 (의존성 체크)"""
        pass

    def get_info(self) -> dict:
        """엔진 정보 반환"""
        available = self.is_available()
        return {
            "name": self.name,
            "display_name": self.display_name,
            "sample_rate": self.sample_rate,
            "supported_languages": self.supported_languages,
            "requires_gpu": self.requires_gpu,
            "requires_internet": self.requires_internet,
            "available": available,
            "voices": self.get_available_voices() if available else []
        }
