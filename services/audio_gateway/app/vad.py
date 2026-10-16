"""
Voice Activity Detection (VAD)

Phase 3.2: Silero VAD 기반 음성 활동 감지
Phase 35.4: Mock 모델 교체 - 실제 Silero VAD 로드
"""
import asyncio
import logging
import time
from typing import Any, Dict, Optional

import numpy as np

# Silero VAD 관련 import
try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False

logger = logging.getLogger(__name__)


class VoiceActivityDetector:
    """
    음성 활동 감지기

    Silero VAD를 사용하여 오디오에서 음성을 감지합니다.

    Attributes:
        threshold: 음성 감지 임계값 (0.0-1.0)
        sample_rate: 입력 오디오 샘플레이트
        min_speech_duration_ms: 최소 음성 지속 시간 (ms)
        min_silence_duration_ms: 최소 무음 지속 시간 (ms)
    """

    # 환경별 모델 설정
    MODEL_CONFIGS = {
        "development": {
            "model_path": "silero_vad",
            "use_onnx": True,
        },
        "production_jetson": {
            "model_path": "silero_vad",
            "use_onnx": True,
        }
    }

    def __init__(
        self,
        threshold: float = 0.5,
        sample_rate: int = 16000,
        min_speech_duration_ms: int = 250,
        min_silence_duration_ms: int = 300,
        environment: str = "development"
    ):
        """
        VoiceActivityDetector 초기화

        Args:
            threshold: 음성 감지 임계값 (0.0-1.0)
            sample_rate: 오디오 샘플레이트 (Hz)
            min_speech_duration_ms: 최소 음성 지속 시간 (ms)
            min_silence_duration_ms: 최소 무음 지속 시간 (ms)
            environment: 실행 환경
        """
        self.threshold = threshold
        self.sample_rate = sample_rate
        self.min_speech_duration_ms = min_speech_duration_ms
        self.min_silence_duration_ms = min_silence_duration_ms
        self.environment = environment

        # 내부 상태
        self._is_speaking = False
        self._speech_start_time: Optional[float] = None
        self._silence_start_time: Optional[float] = None
        self._consecutive_speech_frames = 0
        self._consecutive_silence_frames = 0

        # Silero VAD는 16kHz에서 512 샘플 청크만 지원
        self._vad_chunk_size = 512  # Silero VAD 요구사항
        self._chunk_duration_ms = 32  # 512 samples @ 16kHz = 32ms

        # 모델 로드
        self.model = self._load_model()

    def _load_model(self) -> Any:
        """
        Silero VAD 모델 로드

        Phase 35.4: 실제 Silero VAD 모델 로드, 실패 시 Mock으로 폴백

        Returns:
            로드된 모델 객체
        """
        config = self.MODEL_CONFIGS.get(self.environment, self.MODEL_CONFIGS["development"])

        # Silero VAD 모델 로드 시도
        if TORCH_AVAILABLE:
            try:
                model, utils = torch.hub.load(
                    repo_or_dir='snakers4/silero-vad',
                    model='silero_vad',
                    force_reload=False,
                    onnx=config.get("use_onnx", True),
                    # 컨테이너에는 y/N 신뢰 프롬프트에 답할 터미널이 없다(EOF → Mock 폴백)
                    trust_repo=True
                )
                logger.info("Silero VAD model loaded successfully")
                return model
            except Exception as e:
                logger.warning(f"Failed to load Silero VAD model: {e}. Falling back to MockModel.")

        # Fallback: Mock 모델 객체
        logger.warning("Using MockModel for VAD (torch not available or model load failed)")

        class MockModel:
            def __init__(self):
                self.config = config

            def __call__(self, audio: np.ndarray, sr: int) -> float:
                # 실제 모델에서는 음성 확률 반환
                return 0.3

            def reset_states(self) -> None:
                """Silero VAD 호환 인터페이스"""
                pass

        return MockModel()

    def _run_inference(self, audio_chunk: np.ndarray) -> float:
        """
        모델 추론 실행

        Args:
            audio_chunk: 오디오 청크 (float32 배열)

        Returns:
            음성 확률 (0.0-1.0)
        """
        # MockModel인 경우 (클래스 이름으로 구분)
        if self.model.__class__.__name__ == 'MockModel':
            return self.model(audio_chunk, self.sample_rate)

        # Silero VAD 모델인 경우 torch tensor로 변환 필요
        if TORCH_AVAILABLE:
            try:
                # numpy array를 torch tensor로 변환
                audio_tensor = torch.from_numpy(audio_chunk.astype(np.float32))

                # Silero VAD는 (audio, sample_rate) 형태로 호출
                result = self.model(audio_tensor, self.sample_rate)

                # 결과가 tensor인 경우 float로 변환
                if hasattr(result, 'item'):
                    return float(result.item())
                return float(result)
            except Exception as e:
                logger.error(f"VAD inference error: {e}")
                return 0.0

        return 0.0

    @property
    def is_currently_speaking(self) -> bool:
        """현재 음성 상태 반환"""
        return self._is_speaking

    def detect(self, audio_chunk: np.ndarray) -> Dict[str, Any]:
        """
        오디오 청크에서 음성 활동 감지

        Args:
            audio_chunk: 오디오 데이터 (float32), 임의의 크기 가능

        Returns:
            감지 결과 딕셔너리:
            - is_speech: 음성 감지 여부
            - probability: 음성 확률
            - speech_started: 음성 시작 이벤트 (선택)
            - speech_ended: 음성 종료 이벤트 (선택)
        """
        # 입력 청크를 512 샘플 단위로 분할 처리
        # Silero VAD는 16kHz에서 512 샘플만 지원
        probabilities = []

        for i in range(0, len(audio_chunk), self._vad_chunk_size):
            chunk = audio_chunk[i:i + self._vad_chunk_size]

            # 청크가 512 샘플보다 작으면 패딩
            if len(chunk) < self._vad_chunk_size:
                chunk = np.pad(chunk, (0, self._vad_chunk_size - len(chunk)), mode='constant')

            prob = self._run_inference(chunk)
            probabilities.append(prob)

        # 평균 확률 계산 (또는 최대값 사용 가능)
        probability = max(probabilities) if probabilities else 0.0

        # 현재 프레임이 음성인지 판단
        is_speech_frame = probability >= self.threshold

        result = {
            "is_speech": is_speech_frame,
            "probability": probability
        }

        # 음성 상태 전이 처리
        if is_speech_frame:
            self._consecutive_silence_frames = 0

            if not self._is_speaking:
                self._consecutive_speech_frames += 1

                # 최소 음성 지속 시간 체크
                speech_duration = self._consecutive_speech_frames * self._chunk_duration_ms
                if speech_duration >= self.min_speech_duration_ms:
                    self._is_speaking = True
                    self._speech_start_time = time.time()
                    result["speech_started"] = True
            else:
                self._consecutive_speech_frames += 1
        else:
            self._consecutive_speech_frames = 0

            if self._is_speaking:
                self._consecutive_silence_frames += 1

                # 최소 무음 지속 시간 체크
                silence_duration = self._consecutive_silence_frames * self._chunk_duration_ms
                if silence_duration >= self.min_silence_duration_ms:
                    self._is_speaking = False
                    self._silence_start_time = time.time()
                    result["speech_ended"] = True

        return result

    async def detect_async(self, audio_chunk: np.ndarray) -> Dict[str, Any]:
        """
        비동기 음성 활동 감지

        Args:
            audio_chunk: 오디오 데이터

        Returns:
            감지 결과
        """
        # 동기 detect를 비동기로 래핑
        return self.detect(audio_chunk)

    def set_threshold(self, threshold: float) -> None:
        """
        임계값 동적 변경

        Args:
            threshold: 새로운 임계값 (0.0-1.0)
        """
        if not 0.0 <= threshold <= 1.0:
            raise ValueError("Threshold must be between 0.0 and 1.0")
        self.threshold = threshold

    def reset(self) -> None:
        """VAD 상태 리셋"""
        self._is_speaking = False
        self._speech_start_time = None
        self._silence_start_time = None
        self._consecutive_speech_frames = 0
        self._consecutive_silence_frames = 0

        # Silero VAD 모델 상태도 리셋
        if hasattr(self.model, 'reset_states'):
            self.model.reset_states()

    def get_speech_duration(self) -> Optional[float]:
        """
        현재 음성 지속 시간 반환

        Returns:
            음성 지속 시간 (초), 음성 중이 아니면 None
        """
        if self._is_speaking and self._speech_start_time:
            return time.time() - self._speech_start_time
        return None
