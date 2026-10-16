"""
Edge-TTS Engine

Phase 10.1.4: Microsoft Edge TTS 엔진 구현
"""
import asyncio
import io
from typing import List, Optional

import numpy as np

from .base import TTSEngine


class EdgeTTSEngine(TTSEngine):
    """Microsoft Edge TTS 엔진 - 무료 클라우드 TTS"""

    # 한국어 및 영어 음성 목록
    AVAILABLE_VOICES = [
        # 한국어
        {"id": "ko-KR-SunHiNeural", "name": "선희 (여성)", "language": "ko", "gender": "Female"},
        {"id": "ko-KR-InJoonNeural", "name": "인준 (남성)", "language": "ko", "gender": "Male"},
        {"id": "ko-KR-HyunsuNeural", "name": "현수 (남성)", "language": "ko", "gender": "Male"},
        # 영어 (US)
        {"id": "en-US-JennyNeural", "name": "Jenny (Female)", "language": "en", "gender": "Female"},
        {"id": "en-US-GuyNeural", "name": "Guy (Male)", "language": "en", "gender": "Male"},
        {"id": "en-US-AriaNeural", "name": "Aria (Female)", "language": "en", "gender": "Female"},
        {"id": "en-US-DavisNeural", "name": "Davis (Male)", "language": "en", "gender": "Male"},
        # 일본어
        {"id": "ja-JP-NanamiNeural", "name": "七海 (Female)", "language": "ja", "gender": "Female"},
        {"id": "ja-JP-KeitaNeural", "name": "慶太 (Male)", "language": "ja", "gender": "Male"},
        # 중국어
        {"id": "zh-CN-XiaoxiaoNeural", "name": "晓晓 (Female)", "language": "zh", "gender": "Female"},
        {"id": "zh-CN-YunxiNeural", "name": "云希 (Male)", "language": "zh", "gender": "Male"},
    ]

    def __init__(
        self,
        voice: Optional[str] = None,
        speed: float = 1.0
    ):
        """
        EdgeTTSEngine 초기화

        Args:
            voice: 음성 ID (기본: "ko-KR-SunHiNeural")
            speed: 발화 속도 (0.5 ~ 2.0)
        """
        self._voice = voice or "ko-KR-SunHiNeural"
        self._speed = speed

    @property
    def name(self) -> str:
        return "edge_tts"

    @property
    def display_name(self) -> str:
        return "Microsoft Edge TTS"

    @property
    def sample_rate(self) -> int:
        return 24000

    @property
    def supported_languages(self) -> List[str]:
        return ["ko", "en", "ja", "zh", "es", "fr", "de"]

    @property
    def requires_gpu(self) -> bool:
        return False

    @property
    def requires_internet(self) -> bool:
        return True

    async def _synthesize_async(
        self,
        text: str,
        voice: str,
        speed: float = 1.0
    ) -> bytes:
        """비동기 합성

        Args:
            text: 합성할 텍스트
            voice: 음성 ID
            speed: 발화 속도

        Returns:
            bytes: MP3 오디오 데이터
        """
        try:
            import edge_tts

            # 속도 조절 문자열 생성
            if speed >= 1.0:
                rate = f"+{int((speed - 1) * 100)}%"
            else:
                rate = f"{int((speed - 1) * 100)}%"

            communicate = edge_tts.Communicate(text, voice, rate=rate)
            audio_data = b""

            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_data += chunk["data"]

            return audio_data

        except Exception as e:
            print(f"Edge-TTS async synthesis error: {e}")
            return b""

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
            voice: 음성 ID (None이면 기본 음성)
            speed: 발화 속도 (기본 1.0)

        Returns:
            np.ndarray: float32 오디오 데이터 (24000Hz)
        """
        if not text or not text.strip():
            return np.array([], dtype=np.float32)

        use_voice = voice or self._voice
        use_speed = speed or self._speed

        # 동기 컨텍스트에서 비동기 호출
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 이미 실행 중인 이벤트 루프가 있는 경우
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        asyncio.run,
                        self._synthesize_async(text, use_voice, use_speed)
                    )
                    mp3_data = future.result()
            else:
                mp3_data = loop.run_until_complete(
                    self._synthesize_async(text, use_voice, use_speed)
                )
        except RuntimeError:
            mp3_data = asyncio.run(
                self._synthesize_async(text, use_voice, use_speed)
            )

        return self._mp3_to_numpy(mp3_data)

    def get_available_voices(self) -> List[dict]:
        """사용 가능한 음성 목록 반환"""
        return self.AVAILABLE_VOICES.copy()

    def is_available(self) -> bool:
        """엔진 사용 가능 여부"""
        try:
            import edge_tts
            return True
        except ImportError:
            return False
