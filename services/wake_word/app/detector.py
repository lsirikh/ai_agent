"""
Wake Word Detector

Phase 3.1: OpenWakeWord 기반 Wake Word 감지
Phase 17.1: Pipeline Logging 추가
Phase 40: OpenWakeWord 실제 모델 통합
"""
import asyncio
import json
import os
import re
import time
from collections import deque
from typing import Any, Awaitable, Callable, Dict, Optional

import numpy as np

from .pipeline_logger import get_logger


# Wake Word ID → OpenWakeWord 모델 이름 매핑
# OpenWakeWord 지원 모델: hey_jarvis, alexa, hey_mycroft
WAKE_WORD_MODELS = {
    "hey_jarvis": "hey_jarvis_v0.1",
    "alexa": "alexa_v0.1",
    "hey_mycroft": "hey_mycroft_v0.1",
}


# STT 로 받아 적은 글에 호출어가 있는지 ('헤이 자비스!' · '헤이자비스' · 'Hey Jarvis')
WAKE_TEXT = re.compile(r"[자쟈재저제차챠]\s*[비삐]\s*[스즈쓰]|jarvis", re.IGNORECASE)
VERIFY_SECONDS = 2.5  # STT 로 확인할 최근 소리 길이
# 짧은 말을 STT 로 받아 적었을 때 호출어로 보는 꼴: '헤이 자비스' 로 시작해야 한다
# (답이나 대화 속 '자비스' 로는 깨지 않게). STT 는 '자비스' 를 '차비스' 로도 적는다
WAKE_START = re.compile(
    r"^\W*(헤이|해이|에이|하이|hey|hi)\W*([자쟈재저제차챠]\s*[비삐]\s*[스즈쓰]|jarvis)",
    re.IGNORECASE,
)


class UtteranceSpotter:
    """
    짧은 말(0.4~2.5초)을 소리 크기로 찾는다 — 끝나면(0.4초 조용) 그 소리를 돌려준다.
    한국어 발음 '헤이 자비스' 는 openwakeword 점수가 0~10% 라(끼어들기 시험 2026-10-18)
    이렇게 찾은 짧은 말을 STT 로 확인한다. 긴 말(TV·대화)은 건너뛴다.
    """

    def __init__(self, sample_rate: int = 16000, min_seconds: float = 0.4,
                 max_seconds: float = 2.5, end_silence: float = 0.4,
                 max_pause: float = 1.0):
        self.sample_rate = sample_rate
        self.min_seconds, self.max_seconds = min_seconds, max_seconds
        self.end_silence = end_silence
        self.max_pause = max_pause
        # 최근 10초 소리 크기 — 그중 조용한 쪽(10%)을 바탕 소음으로 본다
        # (가운데 값이면 긴 말 도중에 바탕이 말소리만큼 올라가 말이 끝난 것으로 봤다)
        self._recent: deque = deque(maxlen=100)
        self._buffer: list = []
        self._silent = 0.0
        self._speaking = False

    def feed(self, chunk: np.ndarray) -> Optional[np.ndarray]:
        rms = float(np.sqrt(np.mean(chunk ** 2))) if len(chunk) else 0.0
        floor = float(np.percentile(self._recent, 10)) if self._recent else 0.0
        self._recent.append(rms)
        loud = rms > max(0.01, 3 * floor)
        seconds = len(chunk) / self.sample_rate
        if loud:
            self._speaking = True
            self._silent = 0.0
            self._buffer.append(chunk)
            return None
        if not self._speaking:
            return None
        self._buffer.append(chunk)
        self._silent += seconds
        if self._silent < self.end_silence:
            return None
        audio = np.concatenate(self._buffer)
        spoken = len(audio) / self.sample_rate - self._silent
        if spoken < self.min_seconds and self._silent < self.max_pause:
            return None  # '헤이,' 뒤의 쉼 — 이어질 '자비스' 를 기다린다
        self.reset()
        return audio if self.min_seconds <= spoken <= self.max_seconds else None

    def reset(self) -> None:
        """듣고 있던 말을 잊는다."""
        self._buffer, self._speaking, self._silent = [], False, 0.0


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
        # 답을 말하는 동안은 스피커 소리가 섞여 호출어 점수가 낮아진다(실측 6.9~25.3%,
        # 조용할 때 74%). TTS 만 나올 때는 3% 를 넘지 않아 이때만 기준을 낮춘다
        self.answering = False
        self.barge_in_threshold = float(
            os.environ.get("WAKE_WORD_BARGE_IN_THRESHOLD", "0.15")
        )
        # 애매한 점수(이 값 이상 · 기준 미만)는 STT 로 '자비스' 가 있는지 확인한다.
        # 실측: 사용자의 호출어 22.5%·28.4% 를 놓쳤고, 부르지 않을 때도 15~30% 가 나왔다
        self.verify_threshold = float(
            os.environ.get("WAKE_WORD_VERIFY_THRESHOLD", "0.15")
        )
        self.verifier: Optional[Callable[[np.ndarray], Awaitable[str]]] = None
        self.verify_delay = 0.5  # 호출어 끝까지 듣고 확인한다
        self._recent: deque = deque()
        self._recent_samples = 0
        self._verify_task: Optional[asyncio.Task] = None
        self._verify_quiet_until = 0.0
        self._spotter = UtteranceSpotter(sample_rate=sample_rate)

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
        self._remember(audio_chunk)
        utterance = self._spotter.feed(audio_chunk)
        if utterance is not None and not self._is_in_cooldown:
            self._start_verify(
                {"wake_word": self.wake_word, "confidence": 0.0},
                audio=utterance, strict=True,
            )

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
        threshold = self.confidence_threshold
        if self.answering:
            threshold = min(threshold, self.barge_in_threshold)
        if best_confidence >= threshold:
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
            "confidence": best_confidence,
            "ambiguous": best_confidence >= self.verify_threshold,
        }

    def _remember(self, audio_chunk: np.ndarray) -> None:
        """STT 확인용으로 최근 VERIFY_SECONDS 초를 들고 있는다."""
        self._recent.append(audio_chunk)
        self._recent_samples += len(audio_chunk)
        limit = int(VERIFY_SECONDS * self.sample_rate)
        while self._recent and self._recent_samples - len(self._recent[0]) >= limit:
            self._recent_samples -= len(self._recent.popleft())

    def clear_buffer(self) -> None:
        """모델·확인용 버퍼에 남은 소리를 비운다.

        듣기 시작·끝에 부른다 — 남은 '헤이 자…' 로 다시 감지되지 않게.
        """
        if hasattr(self.model, "reset"):
            self.model.reset()
        self._recent.clear()
        self._recent_samples = 0
        self._spotter.reset()

    def _start_verify(
        self, result: Dict[str, Any], audio: Optional[np.ndarray] = None,
        strict: bool = False,
    ) -> None:
        busy = self._verify_task is not None and not self._verify_task.done()
        if busy or self.verifier is None or time.time() < self._verify_quiet_until:
            return
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return  # 이벤트 루프 밖(동기 detect 시험)에서는 확인하지 않는다
        wake_word = result.get("wake_word") or self.wake_word
        # 확인할 소리가 시작된 때 — 그 뒤에 이미 감지했으면 같은 호출어다
        seconds = VERIFY_SECONDS if audio is None else len(audio) / self.sample_rate
        since = time.time() - seconds
        self._verify_task = asyncio.create_task(
            self._verify(wake_word, result["confidence"], audio, strict, since)
        )

    async def _verify(
        self, wake_word: str, confidence: float,
        audio: Optional[np.ndarray] = None, strict: bool = False,
        since: float = 0.0,
    ) -> None:
        """
        애매한 점수: 최근 소리를 받아 적어 '자비스' 가 있으면 감지로 본다.
        strict(짧은 말로 찾은 것): '헤이 자비스' 로 시작할 때만.
        since 뒤에 이미 감지했으면(모델이 먼저 잡은 같은 호출어) 넘긴다.
        """
        if audio is None:
            await asyncio.sleep(self.verify_delay)
            audio = np.concatenate(list(self._recent)) if self._recent else np.zeros(0)
        try:
            text = await self.verifier(audio) or ""
        except Exception as e:
            text = ""
            await self._logger.warning("wake_verify_failed", f"STT 확인 실패: {e}")
        self._verify_quiet_until = time.time() + 1.5  # 같은 소리로 거듭 확인하지 않게
        await self._logger.log(
            event="wake_verify",
            data={"message": f"{confidence:.1%} → STT '{text[:40]}'", "text": text},
            level="debug",
        )
        pattern = WAKE_START if strict else WAKE_TEXT
        already = (self._last_detection_time or 0.0) >= since
        if self._is_in_cooldown or already or not pattern.search(text):
            return
        self._last_detection_time = time.time()
        self._is_in_cooldown = True
        self.clear_buffer()
        await self._publish_detection(wake_word, confidence)

    async def _publish_detection(self, wake_word: str, confidence: float) -> None:
        """감지를 로그로 남기고 Redis 로 알린다."""

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
            await self._publish_detection(result["wake_word"], result["confidence"])
        elif result.get("ambiguous"):
            self._start_verify(result)

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
