"""
말소리로 끼어들기 (사용자 요청 2026-10-17: '헤이 자비스' 없이 내가 말하면 끊어 줘)

- PlaybackTracker: 앱으로 보낸 답 음성의 길이로 실제 재생 구간과
  그때의 소리 크기를 안다. (TTS 의 합성 시작·끝은 문장당 약 0.2초라
  그것으로는 재생 중인지 알 수 없었다)
- EchoDelay: 마이크 소리 크기와 재생 크기가 같이 오르내리는 시차로
  에코가 몇 초 늦게 들어오는지 익힌다(원격 데스크톱 등).
- SpeechBargeIn: 재생 중 마이크 소리를 그 시각 재생 크기와 견준다.
  에코(EdgeVoice 자신의 목소리)는 재생 크기에 비례하므로, 평소 비율보다
  뚜렷이 큰 사람 목소리가 0.3초 이어질 때만 끼어들기로 본다
  (노이즈 캔슬링·다중 마이크 없이 쓰는 이중 발화 감지).
"""

import time
from bisect import bisect_right
from collections import deque
from typing import Callable, Optional, Sequence

import numpy as np

SEGMENT_SECONDS = 0.1
KEEP_SECONDS = 5.0  # 재생이 끝난 조각을 들고 있는 시간(에코 지연 대비)


class PlaybackTracker:
    def __init__(
        self, sample_rate: int = 24000, clock: Callable[[], float] = time.monotonic
    ):
        self.sample_rate = sample_rate
        self.clock = clock
        self._until = 0.0
        # (시작, 끝, 크기). 개수로 자르지 않는다 — 긴 답은 1분 넘게 미리 쌓인다
        self._segments: list = []
        self._starts: list = []  # 시작 시각(정렬) — 시각으로 빨리 찾는다

    def add(self, samples: np.ndarray) -> None:
        """앱으로 보낸 음성(float32). 앞서 보낸 것 뒤에 이어서 재생된다."""
        now = self.clock()
        played = 0  # 이미 재생이 끝난 것
        while (
            played < len(self._segments)
            and self._segments[played][1] < now - KEEP_SECONDS
        ):
            played += 1
        del self._segments[:played], self._starts[:played]
        start = max(now, self._until)
        step = int(self.sample_rate * SEGMENT_SECONDS)
        for i in range(0, len(samples), step):
            piece = samples[i : i + step]
            end = start + len(piece) / self.sample_rate
            self._segments.append((start, end, float(np.sqrt(np.mean(piece**2)))))
            self._starts.append(start)
            start = end
        self._until = start

    def playing(self, margin: float = 0.6) -> bool:
        """재생 중(끝난 뒤 margin 초까지 — 원격 데스크톱 등 소리 지연)."""
        return self.clock() < self._until + margin

    def level(self, window: float = 1.2) -> float:
        """최근 window 초 동안 재생된 소리의 가장 큰 크기.

        에코가 늦게 들어오는 것(원격 데스크톱 등)을 감안해 창을 넉넉히 본다.
        """
        half = window / 2
        return self.around(self.clock() - half, half)

    def around(self, moment: float, half: float) -> float:
        """moment ± half 초 동안 재생된 소리의 가장 큰 크기."""
        level = 0.0
        i = bisect_right(self._starts, moment + half) - 1
        while i >= 0 and self._segments[i][1] >= moment - half:
            level = max(level, self._segments[i][2])
            i -= 1
        return level

    def clear(self) -> None:
        """남은 재생을 지운다(끼어들기·중단 — 앱도 곧바로 재생을 멈춘다)."""
        self._until = 0.0
        self._segments.clear()
        self._starts.clear()


def _chunk_middle(tracker: PlaybackTracker) -> float:
    """방금 들어온 마이크 조각(지금까지 100ms)의 가운데 시각."""
    return tracker.clock() - SEGMENT_SECONDS / 2


class EchoDelay:
    """에코가 재생보다 몇 초 늦게 마이크에 들어오는지 익힌다.

    최근 마이크 크기와 '시차만큼 앞선' 재생 크기의 상관이 가장 큰 시차를 고른다.
    시차를 알면 그 순간의 재생 크기와만 견줘, 늦게 들어온 큰 에코를 사람 말로
    잘못 보지 않는다. 모르는 동안은 최근 1.2초 중 가장 큰 재생 크기와 견준다.
    """

    def __init__(
        self,
        max_delay: float = 1.5,
        history: int = 80,
        min_correlation: float = 0.6,
        every: int = 10,
    ):
        self.max_delay = max_delay
        self.min_correlation = min_correlation
        self.every = every
        self.delay: Optional[float] = None
        self._history: deque = deque(maxlen=history)  # (시각, 마이크 크기)
        self._seen = 0

    @property
    def known(self) -> bool:
        return self.delay is not None

    def far_level(self, tracker: PlaybackTracker) -> float:
        """지금 마이크에 들어오는 에코를 낸 재생 크기."""
        if self.delay is None:
            return tracker.level()
        return tracker.around(_chunk_middle(tracker) - self.delay, 0.15)

    def observe(self, mic_rms: float, tracker: PlaybackTracker) -> bool:
        """마이크 조각 하나를 기록한다. 시차를 새로 익혔거나 바꿨으면 True."""
        self._history.append((_chunk_middle(tracker), mic_rms))
        self._seen += 1
        if self._seen % self.every or len(self._history) < 30:
            return False
        found = self._estimate(tracker)
        if found is None or (
            self.delay is not None and abs(found - self.delay) < 0.1
        ):
            return False
        self.delay = found
        return True

    def recent_ratios(self, tracker: PlaybackTracker, min_far: float) -> list:
        """최근 마이크 크기 / 익힌 시차만큼 앞선 재생 크기 (에코 비율을 바로 익히게)."""
        if self.delay is None:
            return []
        pairs = [
            (rms, tracker.around(t - self.delay, 0.15)) for t, rms in self._history
        ]
        return [rms / far for rms, far in pairs if far >= min_far]

    def _estimate(self, tracker: PlaybackTracker) -> Optional[float]:
        times = [t for t, _ in self._history]
        mic = np.array([rms for _, rms in self._history])
        if mic.std() < 1e-4:
            return None
        best, best_corr = None, self.min_correlation
        for step in range(int(self.max_delay / SEGMENT_SECONDS) + 1):
            lag = step * SEGMENT_SECONDS
            far = np.array([tracker.around(t - lag, 0.04) for t in times])
            if far.std() < 1e-4:
                continue
            corr = float(np.corrcoef(mic, far)[0, 1])
            if corr > best_corr:
                best, best_corr = lag, corr
        return best


class SpeechBargeIn:
    def __init__(
        self,
        margin: float = 1.8,
        min_level: float = 0.03,
        vad_threshold: float = 0.6,
        need_chunks: int = 3,
        default_echo_ratio: float = 1.0,
        min_far: float = 0.02,
    ):
        self.margin = margin
        self.min_level = min_level
        self.vad_threshold = vad_threshold
        self.need_chunks = need_chunks
        self.default_echo_ratio = default_echo_ratio
        self.min_far = min_far
        self._ratios: deque = deque(maxlen=200)  # 끼어들지 않은 구간의 마이크/재생 비율
        self._streak = 0
        self.last: dict = {}

    def echo_ratio(self) -> float:
        """에코 비율의 위쪽(95%) — 가끔 크게 들어오는 에코도 사람 말로 보지 않게.

        (중앙값은 에코가 늦게 들어오기 전의 0 에 끌려 내려가 에코에 끊었다 — 실측)
        """
        if len(self._ratios) < 10:
            return self.default_echo_ratio
        return float(np.percentile(list(self._ratios), 95))

    def forget_echo(self, ratios: Sequence[float] = ()) -> None:
        """재생 크기를 보는 방법이 바뀌었다(에코 시차를 익힘) — 비율을 다시 익힌다.

        ratios: 바뀐 방법으로 다시 잰 최근 비율. 처음부터 익히는 동안 사용자 말이
        에코로 익혀져 끊지 못했다(실측).
        """
        self._ratios.clear()
        self._ratios.extend(ratios)

    def feed(
        self, mic_rms: float, vad_prob: float, far_level: float, learn: bool = True
    ) -> bool:
        """100ms 마이크 조각 하나. 끼어들기면 True.

        learn=False 면 에코 비율을 익히지 않는다(에코 시차를 모를 때 —
        기본 비율로 넉넉히 견준다).
        """
        expected_echo = self.echo_ratio() * far_level
        self.last = {"mic": mic_rms, "far": far_level, "ratio": self.echo_ratio()}
        loud = mic_rms > max(self.min_level, self.margin * expected_echo)
        if learn and not loud and far_level >= self.min_far:
            # 에코만 들리는 구간으로 비율을 익힌다
            self._ratios.append(mic_rms / far_level)
        if loud and vad_prob >= self.vad_threshold:
            self._streak += 1
        else:
            self._streak = 0
        return self._streak >= self.need_chunks

    def reset(self) -> None:
        self._streak = 0
