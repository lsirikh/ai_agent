"""
Kokoro TTS Engine

Phase 10.1.3: Kokoro TTS 엔진 (TTSEngine 인터페이스 구현)
"""
import os
from typing import List, Optional

import numpy as np

from .base import TTSEngine


class KokoroTTSEngine(TTSEngine):
    """Kokoro TTS 엔진 - 영어 중심 고품질 TTS"""

    # 사용 가능한 음성 목록
    AVAILABLE_VOICES = [
        {"id": "af_heart", "name": "Heart (Female)", "language": "en"},
        {"id": "af_bella", "name": "Bella (Female)", "language": "en"},
        {"id": "af_nicole", "name": "Nicole (Female)", "language": "en"},
        {"id": "af_sarah", "name": "Sarah (Female)", "language": "en"},
        {"id": "af_sky", "name": "Sky (Female)", "language": "en"},
        {"id": "af_alloy", "name": "Alloy (Female)", "language": "en"},
        {"id": "af_nova", "name": "Nova (Female)", "language": "en"},
        {"id": "am_adam", "name": "Adam (Male)", "language": "en"},
        {"id": "am_michael", "name": "Michael (Male)", "language": "en"},
        {"id": "am_echo", "name": "Echo (Male)", "language": "en"},
        {"id": "am_eric", "name": "Eric (Male)", "language": "en"},
        {"id": "am_liam", "name": "Liam (Male)", "language": "en"},
        {"id": "am_onyx", "name": "Onyx (Male)", "language": "en"},
    ]

    def __init__(
        self,
        voice: Optional[str] = None,
        speed: float = 1.0,
        environment: str = "development"
    ):
        """
        KokoroTTSEngine 초기화

        Args:
            voice: 음성 ID (기본: "af_heart")
            speed: 발화 속도 (0.5 ~ 2.0)
            environment: 환경 설정
        """
        self._voice = voice or "af_heart"
        self._speed = speed
        self._environment = environment
        self._model = None
        self._initialized = False

    @property
    def name(self) -> str:
        return "kokoro"

    @property
    def display_name(self) -> str:
        return "Kokoro TTS"

    @property
    def sample_rate(self) -> int:
        return 24000

    @property
    def supported_languages(self) -> List[str]:
        return ["en"]  # 영어 중심

    @property
    def requires_gpu(self) -> bool:
        return True  # GPU 권장

    @property
    def requires_internet(self) -> bool:
        return False

    def _load_model(self) -> None:
        """Kokoro 모델 로드 (lazy loading)"""
        if self._initialized:
            return

        try:
            from kokoro import KPipeline
            self._model = KPipeline(lang_code="a")
            self._initialized = True
        except ImportError:
            self._model = None
            self._initialized = False

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
            np.ndarray: float32 오디오 데이터 (24000Hz)
        """
        if not text or not text.strip():
            return np.array([], dtype=np.float32)

        self._load_model()

        if self._model is None:
            # 모델이 없는 경우 더미 오디오 반환 (테스트용)
            duration = len(text) * 0.1
            samples = int(self.sample_rate * duration)
            return np.zeros(samples, dtype=np.float32)

        try:
            use_voice = voice or self._voice
            use_speed = speed or self._speed

            generator = self._model(
                text,
                voice=use_voice,
                speed=use_speed
            )

            audio_chunks = []
            for _, _, audio in generator:
                if audio is not None:
                    audio_chunks.append(audio)

            if audio_chunks:
                return np.concatenate(audio_chunks).astype(np.float32)
            return np.array([], dtype=np.float32)

        except Exception as e:
            print(f"Kokoro TTS synthesis error: {e}")
            return np.array([], dtype=np.float32)

    def get_available_voices(self) -> List[dict]:
        """사용 가능한 음성 목록 반환"""
        return self.AVAILABLE_VOICES.copy()

    def is_available(self) -> bool:
        """엔진 사용 가능 여부"""
        try:
            from kokoro import KPipeline
            return True
        except ImportError:
            return False
