"""
질문이 끝났는지 소리 크기로도 판단한다 (사용자 요청 2026-10-18).

TV·선풍기·다른 사람 말소리가 있으면 VAD 가 계속 '말소리' 라고 해 녹음이
끝나지 않았다(실측 12.4초). 이번 질문에서 들은 사용자 목소리 크기를 익혀,
그보다 뚜렷이 작은 소리(기본 30% 미만, 약 -10dB)는 무음으로 본다.
"""

from collections import deque

import numpy as np


class VoiceLevel:
    def __init__(self, ratio: float = 0.3, min_chunks: int = 5):
        self.ratio = ratio
        self.min_chunks = min_chunks
        self._levels: deque = deque(maxlen=200)  # 사용자 목소리로 본 조각의 크기

    def level(self) -> float:
        """이번 질문의 사용자 목소리 크기(크기 순 70% 지점)."""
        return float(np.percentile(list(self._levels), 70))

    def is_voice(self, rms: float, vad_speech: bool) -> bool:
        """사용자가 아직 말하는 중인 조각인지."""
        if not vad_speech:
            return False
        if len(self._levels) >= self.min_chunks and rms < self.ratio * self.level():
            return False  # 목소리보다 뚜렷이 작다 — 배경 소리
        self._levels.append(rms)
        return True

    def reset(self) -> None:
        self._levels.clear()
