"""
gTTS Engine

Phase 10.1.5: Google Text-to-Speech 엔진 구현
"""
import io
from typing import List, Optional

import numpy as np

from .base import TTSEngine


class GTTSEngine(TTSEngine):
    """Google TTS 엔진 - 온라인 TTS"""

    # 지원 언어 및 음성 목록
    AVAILABLE_VOICES = [
        {"id": "ko", "name": "Korean", "language": "ko"},
        {"id": "en", "name": "English", "language": "en"},
        {"id": "ja", "name": "Japanese", "language": "ja"},
        {"id": "zh-CN", "name": "Chinese (Simplified)", "language": "zh"},
        {"id": "es", "name": "Spanish", "language": "es"},
        {"id": "fr", "name": "French", "language": "fr"},
        {"id": "de", "name": "German", "language": "de"},
    ]

    def __init__(
        self,
        lang: Optional[str] = None,
        slow: bool = False
    ):
        """
        GTTSEngine 초기화

        Args:
            lang: 언어 코드 (기본: "ko")
            slow: 느린 발음 여부
        """
        self._lang = lang or "ko"
        self._slow = slow

    @property
    def name(self) -> str:
        return "gtts"

    @property
    def display_name(self) -> str:
        return "Google TTS"

    @property
    def sample_rate(self) -> int:
        return 22050  # gTTS 기본 샘플 레이트

    @property
    def supported_languages(self) -> List[str]:
        return ["ko", "en", "ja", "zh", "es", "fr", "de"]

    @property
    def requires_gpu(self) -> bool:
        return False

    @property
    def requires_internet(self) -> bool:
        return True

    def _mp3_to_numpy(self, mp3_data: bytes) -> np.ndarray:
        """MP3 데이터를 numpy 배열로 변환

        Args:
            mp3_data: MP3 바이트 데이터

        Returns:
            np.ndarray: float32 오디오 데이터
        """
        if not mp3_data:
            return np.array([], dtype=np.float32)

        try:
            from pydub import AudioSegment

            audio = AudioSegment.from_mp3(io.BytesIO(mp3_data))
            audio = audio.set_frame_rate(self.sample_rate)
            audio = audio.set_channels(1)

            samples = np.array(audio.get_array_of_samples(), dtype=np.float32)
            samples = samples / 32768.0  # int16 → float32

            return samples

        except ImportError:
            # pydub이 없는 경우 더미 반환
            print("pydub not available, returning dummy audio")
            return np.zeros(1000, dtype=np.float32)
        except Exception as e:
            print(f"MP3 conversion error: {e}")
            return np.array([], dtype=np.float32)

    def synthesize(
        self,
        text: str,
        voice: Optional[str] = None,
        speed: float = 1.0
    ) -> np.ndarray:
        """텍스트를 음성으로 합성

        Args:
            text: 합성할 텍스트
            voice: 언어 코드 (None이면 기본 언어)
            speed: 발화 속도 (gTTS는 slow 파라미터만 지원)

        Returns:
            np.ndarray: float32 오디오 데이터 (22050Hz)
        """
        if not text or not text.strip():
            return np.array([], dtype=np.float32)

        use_lang = voice or self._lang
        use_slow = self._slow or speed < 0.8

        try:
            from gtts import gTTS

            tts = gTTS(text=text, lang=use_lang, slow=use_slow)

            # 메모리에 저장
            mp3_fp = io.BytesIO()
            tts.write_to_fp(mp3_fp)
            mp3_fp.seek(0)

            return self._mp3_to_numpy(mp3_fp.read())

        except ImportError:
            # gtts가 없는 경우 더미 반환
            duration = len(text) * 0.1
            samples = int(self.sample_rate * duration)
            return np.zeros(samples, dtype=np.float32)
        except Exception as e:
            print(f"gTTS synthesis error: {e}")
            return np.array([], dtype=np.float32)

    def get_available_voices(self) -> List[dict]:
        """사용 가능한 음성 목록 반환"""
        return self.AVAILABLE_VOICES.copy()

    def is_available(self) -> bool:
        """엔진 사용 가능 여부"""
        try:
            from gtts import gTTS
            return True
        except ImportError:
            return False
