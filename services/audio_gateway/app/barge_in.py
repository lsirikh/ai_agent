"""
Barge-in Detection

Phase 3.3: TTS 재생 중 사용자 음성 감지 (Barge-in)
"""
import json
import time
from enum import Enum, auto
from typing import Any, Dict, Optional

import numpy as np

from .vad import VoiceActivityDetector


class PlaybackState(Enum):
    """재생 상태"""
    IDLE = auto()      # 재생 중 아님
    PLAYING = auto()   # TTS 재생 중
    PAUSED = auto()    # 일시 정지


class BargeInDetector:
    """
    Barge-in 감지기

    TTS 재생 중 사용자가 말하기 시작하면 감지합니다.
    VAD를 사용하여 음성을 감지하고, 에너지 임계값도 적용합니다.

    Attributes:
        min_speech_duration_ms: 최소 음성 지속 시간 (ms)
        energy_threshold: 에너지 임계값
        vad_threshold: VAD 임계값
        cooldown_ms: Barge-in 후 재감지 방지 쿨다운 (ms)
    """

    def __init__(
        self,
        min_speech_duration_ms: int = 200,
        energy_threshold: float = 0.01,
        vad_threshold: float = 0.5,
        cooldown_ms: int = 1000,
        sample_rate: int = 16000,
        redis_client: Optional[Any] = None,
        redis_channel: str = "edgevoice:barge_in:detected",
        vad: Optional[VoiceActivityDetector] = None
    ):
        """
        BargeInDetector 초기화

        Args:
            min_speech_duration_ms: 최소 음성 지속 시간
            energy_threshold: 오디오 에너지 임계값
            vad_threshold: VAD 신뢰도 임계값
            cooldown_ms: 재감지 방지 쿨다운 시간
            sample_rate: 오디오 샘플레이트
            redis_client: Redis 클라이언트 (비동기)
            redis_channel: Redis 발행 채널
            vad: 외부에서 주입할 VAD 인스턴스 (M1 해결: 중복 인스턴스 방지)
        """
        self.min_speech_duration_ms = min_speech_duration_ms
        self.energy_threshold = energy_threshold
        self.vad_threshold = vad_threshold
        self.cooldown_ms = cooldown_ms
        self.sample_rate = sample_rate
        self.redis_client = redis_client
        self.redis_channel = redis_channel

        # VAD 초기화 - 외부 주입 또는 내부 생성 (하위 호환성)
        if vad is not None:
            self.vad = vad
        else:
            self.vad = VoiceActivityDetector(
                threshold=vad_threshold,
                sample_rate=sample_rate,
                min_speech_duration_ms=min_speech_duration_ms
            )

        # 내부 상태
        self._playback_state = PlaybackState.IDLE
        self._last_barge_in_time: Optional[float] = None
        self._in_cooldown = False

    @property
    def playback_state(self) -> PlaybackState:
        """현재 재생 상태 반환"""
        return self._playback_state

    def set_playback_state(self, state: PlaybackState) -> None:
        """
        재생 상태 설정

        Args:
            state: 새로운 재생 상태
        """
        self._playback_state = state

        # PLAYING으로 전환 시 VAD 리셋
        if state == PlaybackState.PLAYING:
            self.vad.reset()

    def _calculate_energy(self, audio_chunk: np.ndarray) -> float:
        """
        오디오 에너지 계산 (RMS)

        Args:
            audio_chunk: 오디오 데이터

        Returns:
            RMS 에너지 값
        """
        return float(np.sqrt(np.mean(audio_chunk ** 2)))

    def detect(self, audio_chunk: np.ndarray) -> Dict[str, Any]:
        """
        Barge-in 감지

        Args:
            audio_chunk: 오디오 데이터 (float32)

        Returns:
            감지 결과 딕셔너리:
            - barge_in_detected: Barge-in 감지 여부
            - in_cooldown: 쿨다운 중 여부
            - energy: 오디오 에너지
            - vad_result: VAD 결과
        """
        result = {
            "barge_in_detected": False,
            "in_cooldown": False,
            "energy": 0.0
        }

        # PLAYING 상태가 아니면 Barge-in 미감지
        if self._playback_state != PlaybackState.PLAYING:
            return result

        # 쿨다운 체크
        if self._in_cooldown:
            current_time = time.time()
            if self._last_barge_in_time:
                elapsed_ms = (current_time - self._last_barge_in_time) * 1000
                if elapsed_ms < self.cooldown_ms:
                    result["in_cooldown"] = True
                    return result
                else:
                    self._in_cooldown = False

        # 에너지 계산
        energy = self._calculate_energy(audio_chunk)
        result["energy"] = energy

        # 에너지 임계값 체크
        if energy < self.energy_threshold:
            return result

        # VAD 감지
        vad_result = self.vad.detect(audio_chunk)
        result["vad_result"] = vad_result

        # speech_started 이벤트 발생 시 Barge-in 감지
        if vad_result.get("speech_started", False):
            result["barge_in_detected"] = True
            self._last_barge_in_time = time.time()
            self._in_cooldown = True

        return result

    async def detect_and_publish(self, audio_chunk: np.ndarray) -> Dict[str, Any]:
        """
        Barge-in 감지 후 Redis로 이벤트 발행

        Args:
            audio_chunk: 오디오 데이터

        Returns:
            감지 결과
        """
        result = self.detect(audio_chunk)

        if result["barge_in_detected"] and self.redis_client:
            message = json.dumps({
                "type": "barge_in_detected",
                "timestamp": time.time(),
                "energy": result["energy"]
            })
            await self.redis_client.publish(self.redis_channel, message)

        return result

    def reset(self) -> None:
        """상태 리셋"""
        self._playback_state = PlaybackState.IDLE
        self._last_barge_in_time = None
        self._in_cooldown = False
        self.vad.reset()
