"""
한국어 TTS(MeloTTS) 어댑터

Redis 구독자는 synthesize(text) -> float32 24kHz mono 를 기대한다
(게이트웨이·클라이언트 재생 계약).
MeloTTS 는 44.1kHz 로 내보내므로 24kHz 로 바꿔 돌려준다.
"""

import threading
from typing import Any, Callable

import numpy as np

PIPELINE_SAMPLE_RATE = 24000


def _resample(audio: np.ndarray, source_rate: int, target_rate: int) -> np.ndarray:
    """음성용 선형 보간 리샘플링(추가 의존성 없이)."""
    if source_rate == target_rate or len(audio) == 0:
        return audio.astype(np.float32, copy=False)
    target_len = int(round(len(audio) * target_rate / source_rate))
    source_x = np.arange(len(audio), dtype=np.float64)
    target_x = np.linspace(0, len(audio) - 1, target_len)
    return np.interp(target_x, source_x, audio).astype(np.float32)


class MeloSynthesizer:
    """MeloTTS 한국어 엔진을 파이프라인 계약(float32 24kHz)에 맞춘다."""

    def __init__(self, engine: Any = None, speed: float = 1.0) -> None:
        if engine is None:
            from .engines.melo_engine import MeloTTSEngine

            engine = MeloTTSEngine()
        self._engine = engine
        self._speed = speed
        # 워밍업 스레드와 요청 스레드가 동시에 모델을 불러오거나
        # GPU 를 함께 쓰지 않게 한다
        self._lock = threading.Lock()

    def synthesize(self, text: str) -> np.ndarray:
        if not text or not text.strip():
            return np.array([], dtype=np.float32)
        with self._lock:
            audio = self._engine.synthesize(text, speed=self._speed)
        return _resample(
            np.asarray(audio, dtype=np.float32),
            self._engine.sample_rate,
            PIPELINE_SAMPLE_RATE,
        )


def warm_up(synthesizer: Any) -> None:
    """
    첫 합성 준비를 미리 끝낸다.

    MeloTTS 는 프로세스마다 첫 합성에서 한국어 BERT 를 준비하느라 약 60초가 걸린다.
    서비스 시작 시 한 번 합성해 두면 첫 음성 답변이 바로 나온다.
    """
    synthesizer.synthesize("안녕하세요.")


def create_voice_synthesizer(
    engine_name: str,
    kokoro_factory: Callable[[], Any],
    melo_engine: Any = None,
) -> Any:
    """TTS_ENGINE 설정으로 합성기를 고른다. melo 가 아니면 기존 Kokoro."""
    if (engine_name or "").lower() == "melo":
        return MeloSynthesizer(engine=melo_engine)
    return kokoro_factory()
