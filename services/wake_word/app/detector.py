"""
Wake Word Detector

Phase 3.1: OpenWakeWord 기반 Wake Word 감지
Phase 17.1: Pipeline Logging 추가
Phase 40: OpenWakeWord 실제 모델 통합
"""
import json
import time
from typing import Any, Dict, Optional

import numpy as np

from .pipeline_logger import get_logger


# Wake Word ID → OpenWakeWord 모델 이름 매핑
# OpenWakeWord 지원 모델: hey_jarvis, alexa, hey_mycroft
WAKE_WORD_MODELS = {
    "hey_jarvis": "hey_jarvis_v0.1",
    "alexa": "alexa_v0.1",
    "hey_mycroft": "hey_mycroft_v0.1",
}


class WakeWordDetector:
    """
    Wake Word 감지기

    OpenWakeWord를 사용하여 "Hey Jarvis" 또는 다른 Wake Word를 감지합니다.

    Attributes:
        confidence_threshold: Wake Word 감지를 위한 최소 신뢰도 (0.0-1.0)
        sample_rate: 입력 오디오 샘플레이트 (기본 16kHz)
        cooldown_seconds: 연속 감지 방지를 위한 쿨다운 시간
        wake_word: 현재 활성화된 Wake Word ID
    """

    # 환경별 모델 설정
    MODEL_CONFIGS = {
        "development": {
            "model_path": "openwakeword",
            "inference_framework": "onnx",
        },
        "production_jetson": {
            "model_path": "openwakeword",
            "inference_framework": "onnx",
        }
    }

    def __init__(
        self,
        confidence_threshold: float = 0.3,
        sample_rate: int = 16000,
        cooldown_seconds: float = 2.0,
        environment: str = "development",
        redis_client: Optional[Any] = None,
        redis_channel: str = "edgevoice:wake_word:detected",
        wake_word: str = "hey_jarvis"
    ):
        """
        WakeWordDetector 초기화

        Args:
            confidence_threshold: 감지 임계값 (0.0-1.0)
            sample_rate: 오디오 샘플레이트 (Hz)
            cooldown_seconds: 중복 감지 방지 쿨다운 (초)
            environment: 실행 환경 (development/production_jetson)
            redis_client: Redis 클라이언트 (비동기)
            redis_channel: Redis 발행 채널
            wake_word: 감지할 Wake Word ID (hey_jarvis, alexa, etc.)
        """
        self.confidence_threshold = confidence_threshold
        self.sample_rate = sample_rate
        self.cooldown_seconds = cooldown_seconds
        self.environment = environment
        self.redis_client = redis_client
        self.redis_channel = redis_channel
        self.wake_word = wake_word

        # 내부 상태
        self._last_detection_time: Optional[float] = None
        self._is_in_cooldown = False
        self._use_mock = False  # Mock 모델 사용 여부

        # Pipeline logger
        self._logger = get_logger("wake_word")

        # 모델 로드
        self.model = self._load_model()

    def _load_model(self) -> Any:
        """
        OpenWakeWord 모델 로드

        Phase 40: 실제 OpenWakeWord 모델 로드

        Returns:
            로드된 모델 객체 (OpenWakeWord Model 또는 Mock)
        """
        try:
            from openwakeword.model import Model

            # 현재 선택된 Wake Word에 해당하는 모델 이름 가져오기
            model_name = WAKE_WORD_MODELS.get(self.wake_word, "hey_jarvis_v0.1")

            # OpenWakeWord 모델 로드 (ONNX 모드 사용 - tflite와 numpy 호환성 문제 방지)
            self.model = Model(
                wakeword_models=[model_name],
                inference_framework="onnx"
            )
            self._use_mock = False
            print(f"[WakeWord] Loaded OpenWakeWord model: {model_name} (ONNX)")
            return self.model

        except ImportError as e:
            print(f"[WakeWord] OpenWakeWord not installed: {e}")
            print("[WakeWord] Falling back to Mock model")
            return self._create_mock_model()
        except Exception as e:
            print(f"[WakeWord] Failed to load OpenWakeWord model: {e}")
            print("[WakeWord] Falling back to Mock model")
            return self._create_mock_model()

    def _create_mock_model(self) -> Any:
        """
        테스트용 Mock 모델 생성

        Returns:
            Mock 모델 객체
        """
        self._use_mock = True
        config = self.MODEL_CONFIGS.get(self.environment, self.MODEL_CONFIGS["development"])

        class MockModel:
            def __init__(self, wake_word: str):
                self.config = config
                self.wake_word = wake_word

            def predict(self, audio: np.ndarray) -> Dict[str, float]:
                # Mock: 항상 낮은 확률 반환
                return {self.wake_word: 0.1}

        return MockModel(self.wake_word)

    def _run_inference(self, audio_chunk: np.ndarray) -> Dict[str, float]:
        """
        모델 추론 실행

        Phase 40: OpenWakeWord 모델 추론

        Args:
            audio_chunk: 오디오 청크 (float32 배열, 16kHz)

        Returns:
            Wake Word별 확률 딕셔너리
        """
        if self._use_mock:
            # Mock 모델 사용
            return self.model.predict(audio_chunk)

        # OpenWakeWord는 int16 오디오 데이터 기대
        if audio_chunk.dtype == np.float32:
            # float32 [-1.0, 1.0] → int16 [-32768, 32767]
            audio_int16 = (audio_chunk * 32767).astype(np.int16)
        else:
            audio_int16 = audio_chunk

        # OpenWakeWord 모델 예측 실행
        # predict()는 내부적으로 오디오를 축적하고 프레임 단위로 처리
        prediction = self.model.predict(audio_int16)

        # OpenWakeWord 반환 형식: {model_name: probability}
        # 예: {'hey_jarvis_v0.1': 0.85}
        return prediction

    def detect(self, audio_chunk: np.ndarray) -> Dict[str, Any]:
        """
        오디오 청크에서 Wake Word 감지

        Args:
            audio_chunk: 오디오 데이터 (float32, sample_rate Hz)

        Returns:
            감지 결과 딕셔너리:
            - detected: Wake Word 감지 여부
            - wake_word: 감지된 Wake Word 이름 (감지 시)
            - confidence: 신뢰도 점수 (감지 시)
            - cooldown: 쿨다운 상태 여부 (쿨다운 중일 때)
        """
        # 쿨다운 체크
        if self._is_in_cooldown:
            current_time = time.time()
            if self._last_detection_time:
                elapsed = current_time - self._last_detection_time
                if elapsed < self.cooldown_seconds:
                    return {
                        "detected": False,
                        "cooldown": True
                    }
                else:
                    self._is_in_cooldown = False

        # 추론 실행
        predictions = self._run_inference(audio_chunk)

        # 가장 높은 확률의 Wake Word 찾기
        best_wake_word = None
        best_confidence = 0.0

        for wake_word, confidence in predictions.items():
            if confidence > best_confidence:
                best_wake_word = wake_word
                best_confidence = confidence

        # 디버그: 확률이 0.05 이상일 때 로그 출력 (Phase 40.5)
        if best_confidence >= 0.03:
            print(f"[WakeWord] Detection: {best_wake_word} = {best_confidence:.2%} (threshold: {self.confidence_threshold:.2%})")

        # 임계값 체크
        if best_confidence >= self.confidence_threshold:
            self._last_detection_time = time.time()
            self._is_in_cooldown = True
            # 버퍼에 남은 이 호출어로 다시 감지되지 않게 비운다
            # (실측: 질문 인식 직후 재감지)
            if hasattr(self.model, "reset"):
                self.model.reset()

            return {
                "detected": True,
                "wake_word": best_wake_word,
                "confidence": best_confidence
            }

        # 미감지 시에도 확률 정보 반환 (Pipeline Log용)
        return {
            "detected": False,
            "wake_word": best_wake_word,
            "confidence": best_confidence
        }

    async def detect_and_publish(self, audio_chunk: np.ndarray) -> Dict[str, Any]:
        """
        Wake Word 감지 후 Redis로 이벤트 발행

        Args:
            audio_chunk: 오디오 데이터

        Returns:
            감지 결과
        """
        result = self.detect(audio_chunk)

        # Log cooldown events (DEBUG level)
        # Phase 43: log() 메서드 사용으로 event와 message 분리
        if result.get("cooldown"):
            await self._logger.log(
                event="wake_word_cooldown",
                data={
                    "message": f"Cooldown active ({self.cooldown_seconds}s remaining)",
                    "cooldown_seconds": self.cooldown_seconds,
                    "threshold": self.confidence_threshold
                },
                level="debug"
            )
            return result

        # Phase 41: 확률이 5% 이상일 때 Pipeline Log에 디버그 로그 발행
        # Phase 43: log() 메서드 사용으로 event와 message 분리
        # Phase 48: 이벤트명 단축 (detection_probability → detect_prob)
        confidence = result.get("confidence", 0)
        if confidence >= 0.05:
            wake_word = result.get("wake_word", "unknown")
            await self._logger.log(
                event="detect_prob",
                data={
                    "message": f"{confidence:.1%} (threshold: {self.confidence_threshold:.0%})",
                    "wake_word": wake_word,
                    "confidence": float(confidence) if confidence else 0,
                    "threshold": self.confidence_threshold,
                    "detected": result["detected"]
                },
                level="debug"
            )

        if result["detected"]:
            wake_word = result["wake_word"]
            confidence = result["confidence"]

            # 콘솔 로그 출력 (Phase 40.5)
            print(f"[WakeWord] ★★★ DETECTED! {wake_word} = {confidence:.2%} ★★★")

            # Log wake word detection
            await self._logger.info(
                "wake_word_detected",
                f"Wake word '{wake_word}' detected (confidence: {confidence:.2f})",
                metadata={
                    "wake_word": wake_word,
                    "confidence": float(confidence),  # numpy.float32 → Python float
                    "threshold": self.confidence_threshold
                }
            )

            # Log listening mode activation (Phase 17.2)
            await self._logger.info(
                "listening_mode_activated",
                "음성 수신 모드 전환 - 사용자 명령을 기다리는 중",
                metadata={
                    "wake_word": wake_word,
                    "previous_state": "IDLE",
                    "new_state": "LISTENING"
                }
            )

            # Publish to Redis
            if self.redis_client:
                message = json.dumps({
                    "type": "wake_word_detected",
                    "wake_word": wake_word,
                    "confidence": float(confidence),  # numpy.float32 → Python float
                    "timestamp": time.time()
                })
                await self.redis_client.publish(self.redis_channel, message)

                # Log Redis publish
                await self._logger.info(
                    "wake_word_published",
                    f"Wake word event published to Redis channel: {self.redis_channel}",
                    metadata={
                        "channel": self.redis_channel,
                        "wake_word": wake_word
                    }
                )

        return result

    def set_confidence_threshold(self, threshold: float) -> None:
        """
        신뢰도 임계값 동적 변경

        Args:
            threshold: 새로운 임계값 (0.0-1.0)
        """
        if not 0.0 <= threshold <= 1.0:
            raise ValueError("Threshold must be between 0.0 and 1.0")
        self.confidence_threshold = threshold

    def set_wake_word(self, wake_word: str) -> bool:
        """
        Wake Word 변경 및 모델 재로드

        Phase 40: 동적 Wake Word 변경

        Args:
            wake_word: 새로운 Wake Word ID (hey_jarvis, alexa, etc.)

        Returns:
            성공 여부
        """
        if wake_word not in WAKE_WORD_MODELS:
            print(f"[WakeWord] Unknown wake word: {wake_word}")
            print(f"[WakeWord] Available: {list(WAKE_WORD_MODELS.keys())}")
            return False

        if wake_word == self.wake_word:
            print(f"[WakeWord] Already using: {wake_word}")
            return True

        old_wake_word = self.wake_word
        self.wake_word = wake_word

        # 모델 재로드
        self.model = self._load_model()
        self.reset()

        print(f"[WakeWord] Changed wake word: {old_wake_word} → {wake_word}")
        return True

    def get_available_wake_words(self) -> Dict[str, str]:
        """
        사용 가능한 Wake Word 목록 반환

        Returns:
            {wake_word_id: model_name} 딕셔너리
        """
        return WAKE_WORD_MODELS.copy()

    def get_status(self) -> Dict[str, Any]:
        """
        현재 Detector 상태 반환

        Returns:
            상태 정보 딕셔너리
        """
        return {
            "wake_word": self.wake_word,
            "model_name": WAKE_WORD_MODELS.get(self.wake_word, "unknown"),
            "confidence_threshold": self.confidence_threshold,
            "use_mock": self._use_mock,
            "is_in_cooldown": self._is_in_cooldown,
            "cooldown_seconds": self.cooldown_seconds,
            "sample_rate": self.sample_rate
        }

    def reset(self) -> None:
        """감지 상태 리셋"""
        self._last_detection_time = None
        self._is_in_cooldown = False
