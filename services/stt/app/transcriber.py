"""
StreamingTranscriber - Faster-Whisper 기반 음성 인식

Phase 1.1: STT 서비스 핵심 클래스
"""
import os
from typing import AsyncGenerator, Optional

import numpy as np

try:
    from faster_whisper import WhisperModel
except ImportError:
    WhisperModel = None  # 테스트 시 모킹 가능


class StreamingTranscriber:
    """
    실시간 스트리밍 음성 인식

    특징:
    - GPU 가속 (CUDA)
    - VAD 필터로 무음 구간 자동 제거
    - 환경별 모델 설정 (개발/프로덕션)
    """

    # 환경별 모델 매핑
    MODEL_CONFIGS = {
        "development": {
            "model_size": "small",  # GPU 메모리 절약을 위해 small 모델 사용
            "compute_type": "int8",  # CPU 모드에서는 int8 사용
            "device": "cpu"  # cuDNN 문제로 인해 CPU 모드 사용
        },
        "production_jetson": {
            "model_size": "small",
            "compute_type": "int8",
            "device": "cuda"
        },
        "cpu": {
            "model_size": "small",
            "compute_type": "int8",
            "device": "cpu"
        }
    }

    def __init__(self, environment: str = "development"):
        """
        Transcriber 초기화

        Args:
            environment: 환경 설정 키 (development, production_jetson, cpu)
        """
        # 환경 변수 우선 적용
        env_override = os.getenv("STT_ENVIRONMENT")
        if env_override and env_override in self.MODEL_CONFIGS:
            environment = env_override

        if environment not in self.MODEL_CONFIGS:
            raise ValueError(f"Unknown environment: {environment}")

        self.config = self.MODEL_CONFIGS[environment].copy()

        # 개별 환경 변수로 오버라이드 가능
        if os.getenv("MODEL_SIZE"):
            self.config["model_size"] = os.getenv("MODEL_SIZE")
        if os.getenv("DEVICE"):
            self.config["device"] = os.getenv("DEVICE")
        if os.getenv("COMPUTE_TYPE"):
            self.config["compute_type"] = os.getenv("COMPUTE_TYPE")

        self.sample_rate = 16000

        # Whisper 모델 로드
        print(f"[STT] Loading Whisper model: {self.config['model_size']} on {self.config['device']} ({self.config['compute_type']})")
        self.model = WhisperModel(
            self.config["model_size"],
            device=self.config["device"],
            compute_type=self.config["compute_type"]
        )
        print("[STT] Model loaded successfully")

    def transcribe(
        self,
        audio: np.ndarray,
        language: Optional[str] = None,
        beam_size: int = 5
    ) -> dict:
        """
        오디오를 텍스트로 변환

        Args:
            audio: 오디오 데이터 (float32, 16kHz)
            language: 언어 코드 (예: "ko", "en"). None이면 자동 감지
            beam_size: 빔 서치 크기

        Returns:
            {
                "text": str,          # 전사된 텍스트
                "confidence": float,  # 신뢰도 (0.0 ~ 1.0)
                "language": str,      # 감지된 언어
                "segments": list      # 세그먼트 상세 정보
            }
        """
        # VAD 파라미터
        vad_parameters = {
            "threshold": 0.5,
            "min_speech_duration_ms": 250,
            "min_silence_duration_ms": 1000
        }

        # 전사 수행
        segments, info = self.model.transcribe(
            audio,
            language=language,
            beam_size=beam_size,
            vad_filter=True,
            vad_parameters=vad_parameters
        )

        # 결과 수집
        segments_list = list(segments)
        full_text = " ".join(seg.text.strip() for seg in segments_list)

        # 신뢰도 계산 (평균 log probability를 확률로 변환)
        if segments_list:
            avg_logprob = sum(seg.avg_logprob for seg in segments_list) / len(segments_list)
            confidence = float(np.exp(avg_logprob))
        else:
            confidence = 0.0

        # 언어 정보
        detected_language = language or getattr(info, "language", "unknown")

        return {
            "text": full_text.strip(),
            "confidence": min(max(confidence, 0.0), 1.0),  # 0~1 범위로 클램프
            "language": detected_language,
            "segments": [
                {
                    "text": seg.text.strip(),
                    "start": seg.start,
                    "end": seg.end,
                    "confidence": float(np.exp(seg.avg_logprob))
                }
                for seg in segments_list
            ]
        }

    async def transcribe_stream(
        self,
        audio_generator: AsyncGenerator[bytes, None],
        language: str = "ko",
        min_chunk_seconds: float = 1.0
    ) -> AsyncGenerator[dict, None]:
        """
        스트리밍 전사

        Args:
            audio_generator: 오디오 바이트 스트림 (int16, 16kHz)
            language: 언어 코드
            min_chunk_seconds: 최소 처리 단위 (초)

        Yields:
            {"text": str, "is_final": bool, "confidence": float}
        """
        buffer = np.array([], dtype=np.float32)
        min_samples = int(self.sample_rate * min_chunk_seconds)

        async for audio_bytes in audio_generator:
            # bytes → numpy float32
            audio_np = np.frombuffer(audio_bytes, dtype=np.int16)
            audio_float = audio_np.astype(np.float32) / 32768.0
            buffer = np.concatenate([buffer, audio_float])

            # 충분한 오디오가 쌓이면 처리
            if len(buffer) >= min_samples:
                result = self.transcribe(buffer, language=language)

                if result["text"]:
                    yield {
                        "text": result["text"],
                        "is_final": False,
                        "confidence": result["confidence"]
                    }

                # 버퍼 클리어
                buffer = np.array([], dtype=np.float32)

        # 남은 버퍼 처리
        if len(buffer) > 0:
            result = self.transcribe(buffer, language=language)
            if result["text"]:
                yield {
                    "text": result["text"],
                    "is_final": True,
                    "confidence": result["confidence"]
                }
