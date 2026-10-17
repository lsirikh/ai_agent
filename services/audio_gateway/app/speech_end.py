"""
질문이 끝났는지 소리 크기로도 판단한다 (사용자 요청 2026-10-18).

TV·선풍기·다른 사람 말소리가 있으면 VAD 가 계속 '말소리' 라고 해 녹음이
끝나지 않았다(실측 12.4초). 이번 질문에서 들은 사용자 목소리 크기를 익혀,
그보다 뚜렷이 작은 소리(기본 40% 미만, 약 -8dB)는 무음으로 본다.
"""

from collections import deque

import numpy as np

MIN_VOICE_RMS = 0.004  # 이보다 작으면 VAD 가 말소리라 해도 목소리가 아니다(VAD 꼬리)


class VoiceLevel:
    def __init__(
        self, ratio: float = 0.4, min_chunks: int = 5, learn_ratio: float = 0.6
    ):
        self.ratio = ratio
        self.min_chunks = min_chunks
        self.learn_ratio = learn_ratio
        self._levels: deque = deque(maxlen=200)  # 사용자 목소리로 본 조각의 크기
        self.last = ""  # 최근 판정 기록(V 목소리 · . 아님), 로그용

    def level(self) -> float:
        """이번 질문의 사용자 목소리 크기(크기 순 70% 지점)."""
        return float(np.percentile(list(self._levels), 70))

    def is_voice(self, rms: float, vad_speech: bool) -> bool:
        """사용자가 아직 말하는 중인 조각인지."""
        heard = self._judge(rms, vad_speech)
        self.last = (self.last + ("V" if heard else "."))[-10:]
        return heard

    def _judge(self, rms: float, vad_speech: bool) -> bool:
        if not vad_speech or rms < MIN_VOICE_RMS:
            return False
        if len(self._levels) < self.min_chunks:
            self._levels.append(rms)
            return True
        level = self.level()
        if rms < self.ratio * level:
            return False  # 목소리보다 뚜렷이 작다 — 배경 소리
        if rms >= self.learn_ratio * level:
            # 뚜렷한 목소리만 익힌다(작은 소리를 익히면 기준이 점점 내려간다 — 실측)
            self._levels.append(rms)
        return True

    @property
    def steady(self) -> bool:
        """두 조각(0.2초) 넘게 목소리가 이어지는지 — 배경의 큰 음절 하나는 아니다."""
        return self.last.endswith("VV")

    def describe(self) -> str:
        """로그용: 익힌 목소리 크기와 최근 판정."""
        known = f"{self.level():.3f}" if self._levels else "-"
        return f"{known} last={self.last}"

    def reset(self) -> None:
        self._levels.clear()
        self.last = ""
