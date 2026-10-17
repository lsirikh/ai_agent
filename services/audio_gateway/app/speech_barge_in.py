"""
말소리로 끼어들기 (사용자 요청 2026-10-17: '헤이 자비스' 없이 내가 말하면 끊어 줘)

- PlaybackTracker: 앱으로 보낸 답 음성의 길이로 실제 재생 구간과
  그때의 소리 크기를 안다. (TTS 의 합성 시작·끝은 문장당 약 0.2초라
  그것으로는 재생 중인지 알 수 없었다)
- SpeechBargeIn: 재생 중 마이크 소리를 그 시각 재생 크기와 견준다.
  에코(EdgeVoice 자신의 목소리)는 재생 크기에 비례하므로, 평소 비율보다
  뚜렷이 큰 사람 목소리가 0.3초 이어질 때만 끼어들기로 본다
  (노이즈 캔슬링·다중 마이크 없이 쓰는 이중 발화 감지).
"""

import time
from collections import deque
from statistics import median
from typing import Callable

import numpy as np

SEGMENT_SECONDS = 0.1


class PlaybackTracker:
    def __init__(
        self, sample_rate: int = 24000, clock: Callable[[], float] = time.monotonic
    ):
        self.sample_rate = sample_rate
        self.clock = clock
        self._until = 0.0
        self._segments: deque = deque(maxlen=600)  # (시작, 끝, 크기) 최근 1분

    def add(self, samples: np.ndarray) -> None:
        """앱으로 보낸 음성(float32). 앞서 보낸 것 뒤에 이어서 재생된다."""
        start = max(self.clock(), self._until)
        step = int(self.sample_rate * SEGMENT_SECONDS)
        for i in range(0, len(samples), step):
            piece = samples[i : i + step]
            end = start + len(piece) / self.sample_rate
            self._segments.append((start, end, float(np.sqrt(np.mean(piece**2)))))
            start = end
        self._until = start

    def playing(self, margin: float = 0.6) -> bool:
        """재생 중(끝난 뒤 margin 초까지 — 원격 데스크톱 등 소리 지연)."""
        return self.clock() < self._until + margin

    def level(self, window: float = 1.2) -> float:
        """최근 window 초 동안 재생된 소리의 가장 큰 크기.

        에코가 늦게 들어오는 것(원격 데스크톱 등)을 감안해 창을 넉넉히 본다.
        """
        now = self.clock()
        return max(
            (
                rms
                for start, end, rms in self._segments
                if end >= now - window and start <= now
            ),
            default=0.0,
        )

    def clear(self) -> None:
        self._until = self.clock()
        self._segments.clear()


class SpeechBargeIn:
    def __init__(
        self,
        margin: float = 2.5,
        min_level: float = 0.03,
        vad_threshold: float = 0.6,
        need_chunks: int = 3,
        default_echo_ratio: float = 1.0,
    ):
        self.margin = margin
        self.min_level = min_level
        self.vad_threshold = vad_threshold
        self.need_chunks = need_chunks
        self.default_echo_ratio = default_echo_ratio
        self._ratios: deque = deque(maxlen=100)  # 끼어들지 않은 구간의 마이크/재생 비율
        self._streak = 0

    def echo_ratio(self) -> float:
        return (
            median(self._ratios) if len(self._ratios) >= 5 else self.default_echo_ratio
        )

    def feed(self, mic_rms: float, vad_prob: float, far_level: float) -> bool:
        """100ms 마이크 조각 하나. 끼어들기면 True."""
        expected_echo = self.echo_ratio() * far_level
        loud = mic_rms > max(self.min_level, self.margin * expected_echo)
        if not loud and far_level > 1e-3:
            # 에코만 들리는 구간으로 비율을 익힌다
            self._ratios.append(mic_rms / far_level)
        if loud and vad_prob >= self.vad_threshold:
            self._streak += 1
        else:
            self._streak = 0
        return self._streak >= self.need_chunks

    def reset(self) -> None:
        self._streak = 0
