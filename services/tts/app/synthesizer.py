"""
Kokoro TTS Synthesizer

Phase 1.3: Kokoro 기반 음성 합성기 구현
"""
import io
import os
import wave
from typing import Any, AsyncGenerator, Optional

import numpy as np

# HuggingFace 캐시 경로 설정 (Docker 환경용)
if os.path.exists('/models/.cache/huggingface'):
    os.environ['HF_HOME'] = '/models/.cache/huggingface'


class KokoroTTS:
    """
    Kokoro TTS 음성 합성기

    Attributes:
        sample_rate: 샘플 레이트 (24000Hz)
        voice: 음성 ID
        speed: 발화 속도 (1.0 = 기본)
    """

    MODEL_CONFIGS = {
        "development": {
            "model_path": "kokoro-v0_19",
            "device": "cuda",
            "voice": "af_heart"
        },
        "production_jetson": {
            "model_path": "kokoro-v0_19",
            "device": "cuda",
            "voice": "af_heart"
        }
    }

    # 사용 가능한 음성 목록
    AVAILABLE_VOICES = [
        "af_heart",
        "af_bella",
        "af_nicole",
        "af_sarah",
        "af_sky",
        "af_alloy",
        "af_aoede",
        "af_jessica",
        "af_kore",
        "af_nova",
        "af_river",
        "am_adam",
        "am_michael",
        "am_echo",
        "am_eric",
        "am_fenrir",
        "am_liam",
        "am_onyx",
        "am_puck",
        "bf_emma",
        "bf_isabella",
        "bf_alice",
        "bf_lily",
        "bm_george",
        "bm_lewis",
        "bm_daniel",
        "bm_fable"
    ]

    def __init__(
        self,
        voice: Optional[str] = None,
        speed: float = 1.0,
        environment: str = "development",
        lazy_load: bool = True
    ):
        """
        KokoroTTS 초기화

        Args:
            voice: 음성 ID (기본: 환경 설정에 따름)
            speed: 발화 속도 (0.5 ~ 2.0)
            environment: 환경 설정 ("development" 또는 "production_jetson")
            lazy_load: True이면 첫 합성 시 모델 로드
        """
        self.environment = environment
        config = self.MODEL_CONFIGS.get(environment, self.MODEL_CONFIGS["development"])

        self.sample_rate = 24000
        self.voice = voice or config.get("voice", "af_default")
        self.speed = speed
        self.device = config.get("device", "cuda")
        self.model_path = config.get("model_path", "kokoro-v0_19")

        self._model = None
        self._voicepack = None

        if not lazy_load:
            self._load_model()

    def _load_model(self) -> Any:
        """
        Kokoro 모델 로드

        Returns:
            로드된 모델 객체
        """
        if self._model is not None:
            return self._model

        try:
            # Kokoro TTS 라이브러리 임포트
            from kokoro import KPipeline

            self._model = KPipeline(lang_code="a")  # 'a' for American English (supports Korean too)
            return self._model
        except ImportError:
            # 개발/테스트 환경에서 모델이 없는 경우
            return None

    def _ensure_model_loaded(self) -> None:
        """모델이 로드되었는지 확인하고, 안 되어 있으면 로드"""
        if self._model is None:
            self._load_model()

    def synthesize(self, text: str) -> np.ndarray:
        """
        텍스트를 음성으로 합성

        Args:
            text: 합성할 텍스트

        Returns:
            np.ndarray: float32 오디오 데이터 (24kHz)
        """
        if not text or not text.strip():
            return np.array([], dtype=np.float32)

        return self._synthesize_internal(text)

    def _synthesize_internal(self, text: str) -> np.ndarray:
        """
        내부 합성 로직

        Args:
            text: 합성할 텍스트

        Returns:
            np.ndarray: 합성된 오디오
        """
        self._ensure_model_loaded()

        if self._model is None:
            # 모델이 없는 경우 더미 오디오 반환 (테스트용)
            duration = len(text) * 0.1  # 대략 글자당 0.1초
            samples = int(self.sample_rate * duration)
            return np.zeros(samples, dtype=np.float32)

        try:
            # Kokoro 모델로 합성
            generator = self._model(
                text,
                voice=self.voice,
                speed=self.speed
            )

            # 모든 청크 수집
            audio_chunks = []
            for _, _, audio in generator:
                if audio is not None:
                    audio_chunks.append(audio)

            if audio_chunks:
                return np.concatenate(audio_chunks).astype(np.float32)
            return np.array([], dtype=np.float32)

        except Exception as e:
            # 에러 시 빈 오디오 반환
            print(f"TTS synthesis error: {e}")
            return np.array([], dtype=np.float32)

    async def synthesize_stream(
        self,
        text: str
    ) -> AsyncGenerator[np.ndarray, None]:
        """
        텍스트를 스트리밍으로 음성 합성

        Args:
            text: 합성할 텍스트

        Yields:
            np.ndarray: 오디오 청크
        """
        async for chunk in self._synthesize_stream_internal(text):
            yield chunk

    async def _synthesize_stream_internal(
        self,
        text: str
    ) -> AsyncGenerator[np.ndarray, None]:
        """
        내부 스트리밍 합성 로직

        Args:
            text: 합성할 텍스트

        Yields:
            np.ndarray: 오디오 청크
        """
        self._ensure_model_loaded()

        if self._model is None:
            # 모델이 없는 경우 더미 오디오 반환
            duration = len(text) * 0.1
            chunk_duration = 0.2  # 0.2초 청크
            chunk_samples = int(self.sample_rate * chunk_duration)
            total_samples = int(self.sample_rate * duration)

            for i in range(0, total_samples, chunk_samples):
                remaining = min(chunk_samples, total_samples - i)
                yield np.zeros(remaining, dtype=np.float32)
            return

        try:
            # Kokoro 모델로 스트리밍 합성
            generator = self._model(
                text,
                voice=self.voice,
                speed=self.speed
            )

            for _, _, audio in generator:
                if audio is not None:
                    yield audio.astype(np.float32)

        except Exception as e:
            print(f"TTS streaming error: {e}")

    def get_available_voices(self) -> list[str]:
        """
        사용 가능한 음성 목록 반환

        Returns:
            list[str]: 음성 ID 목록
        """
        return self.AVAILABLE_VOICES.copy()

    def set_voice(self, voice: str) -> None:
        """
        음성 변경

        Args:
            voice: 새 음성 ID
        """
        self.voice = voice

    def to_int16(self, audio: np.ndarray) -> np.ndarray:
        """
        float32 오디오를 int16으로 변환

        Args:
            audio: float32 오디오 (-1.0 ~ 1.0)

        Returns:
            np.ndarray: int16 오디오
        """
        # 클리핑 방지
        audio = np.clip(audio, -1.0, 1.0)
        return (audio * 32767).astype(np.int16)

    def to_wav_bytes(self, audio: np.ndarray) -> bytes:
        """
        오디오를 WAV 바이트로 변환

        Args:
            audio: float32 또는 int16 오디오

        Returns:
            bytes: WAV 파일 바이트
        """
        # float32면 int16으로 변환
        if audio.dtype == np.float32:
            audio = self.to_int16(audio)

        # WAV 파일 생성
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav_file:
            wav_file.setnchannels(1)  # 모노
            wav_file.setsampwidth(2)  # int16 = 2 bytes
            wav_file.setframerate(self.sample_rate)
            wav_file.writeframes(audio.tobytes())

        return buffer.getvalue()
