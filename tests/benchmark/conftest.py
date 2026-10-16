"""
Benchmark Test Fixtures

Phase 6.3: 벤치마크 테스트용 공통 fixtures
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
import asyncio
import time
import numpy as np
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class LatencyMeasurement:
    """지연 시간 측정 결과"""
    name: str
    start_time: float
    end_time: float
    duration_ms: float


class LatencyTracker:
    """지연 시간 추적기"""

    def __init__(self):
        self.measurements: List[LatencyMeasurement] = []
        self._current_start: Optional[float] = None
        self._current_name: Optional[str] = None

    def start(self, name: str):
        """측정 시작"""
        self._current_start = time.perf_counter()
        self._current_name = name

    def stop(self) -> LatencyMeasurement:
        """측정 종료"""
        end_time = time.perf_counter()
        duration_ms = (end_time - self._current_start) * 1000

        measurement = LatencyMeasurement(
            name=self._current_name,
            start_time=self._current_start,
            end_time=end_time,
            duration_ms=duration_ms
        )

        self.measurements.append(measurement)
        self._current_start = None
        self._current_name = None

        return measurement

    def get_average(self, name: str) -> float:
        """특정 측정의 평균 지연 시간"""
        filtered = [m for m in self.measurements if m.name == name]
        if not filtered:
            return 0.0
        return sum(m.duration_ms for m in filtered) / len(filtered)

    def get_p95(self, name: str) -> float:
        """특정 측정의 95 백분위 지연 시간"""
        filtered = [m.duration_ms for m in self.measurements if m.name == name]
        if not filtered:
            return 0.0
        filtered.sort()
        idx = int(len(filtered) * 0.95)
        return filtered[min(idx, len(filtered) - 1)]

    def get_p99(self, name: str) -> float:
        """특정 측정의 99 백분위 지연 시간"""
        filtered = [m.duration_ms for m in self.measurements if m.name == name]
        if not filtered:
            return 0.0
        filtered.sort()
        idx = int(len(filtered) * 0.99)
        return filtered[min(idx, len(filtered) - 1)]


@pytest.fixture
def latency_tracker():
    """지연 시간 추적기 fixture"""
    return LatencyTracker()


@pytest.fixture
def mock_fast_stt():
    """빠른 STT 서비스 mock"""
    service = MagicMock()

    async def fast_transcribe(audio):
        # 시뮬레이션: 50-150ms 지연
        await asyncio.sleep(np.random.uniform(0.05, 0.15))
        return {
            "text": "안녕하세요",
            "confidence": 0.95,
            "language": "ko"
        }

    service.transcribe = fast_transcribe
    return service


@pytest.fixture
def mock_fast_llm():
    """빠른 LLM 서비스 mock"""
    service = MagicMock()

    async def fast_generate(prompt, **kwargs):
        # 시뮬레이션: 100-200ms 지연
        await asyncio.sleep(np.random.uniform(0.1, 0.2))
        return {
            "text": "안녕하세요! 무엇을 도와드릴까요?",
            "tokens_used": 20
        }

    async def fast_stream():
        tokens = ["안녕", "하세요", "!", " ", "무엇", "을"]
        for token in tokens:
            # 시뮬레이션: 20-50ms per token
            await asyncio.sleep(np.random.uniform(0.02, 0.05))
            yield {"token": token, "finished": False}
        yield {"token": "", "finished": True}

    service.generate = fast_generate
    service.generate_stream = fast_stream
    return service


@pytest.fixture
def mock_fast_tts():
    """빠른 TTS 서비스 mock"""
    service = MagicMock()

    async def fast_synthesize(text):
        # 시뮬레이션: 100-300ms 지연 (텍스트 길이에 비례)
        base_delay = 0.1
        length_factor = len(text) * 0.01
        await asyncio.sleep(base_delay + length_factor)
        return {
            "audio": np.random.randint(-32768, 32767, size=24000, dtype=np.int16).tobytes(),
            "sample_rate": 24000,
            "duration": 1.0
        }

    service.synthesize = fast_synthesize
    return service


@pytest.fixture
def mock_fast_wake_word():
    """빠른 Wake Word 서비스 mock"""
    service = MagicMock()

    async def fast_detect(audio):
        # 시뮬레이션: 10-30ms 지연
        await asyncio.sleep(np.random.uniform(0.01, 0.03))
        return {
            "detected": True,
            "confidence": 0.9,
            "keyword": "헤이 로봇"
        }

    service.detect = fast_detect
    return service


@pytest.fixture
def mock_fast_embedding():
    """빠른 Embedding 서비스 mock"""
    service = MagicMock()

    async def fast_embed(text):
        # 시뮬레이션: 20-50ms 지연
        await asyncio.sleep(np.random.uniform(0.02, 0.05))
        return {
            "embedding": np.random.randn(1024).tolist(),
            "dimension": 1024
        }

    service.embed = fast_embed
    return service


@pytest.fixture
def mock_fast_rag():
    """빠른 RAG 서비스 mock"""
    service = MagicMock()

    async def fast_retrieve(query, **kwargs):
        # 시뮬레이션: 30-80ms 지연
        await asyncio.sleep(np.random.uniform(0.03, 0.08))
        return [
            {"content": "관련 문서 내용", "score": 0.85, "metadata": {"source": "doc.txt"}}
        ]

    service.retrieve = fast_retrieve
    return service


@pytest.fixture
def sample_audio_chunk():
    """샘플 오디오 청크 (30ms, 16kHz)"""
    sample_rate = 16000
    duration_ms = 30
    samples = int(sample_rate * duration_ms / 1000)
    return np.random.randint(-32768, 32767, size=samples, dtype=np.int16).tobytes()


@pytest.fixture
def benchmark_config():
    """벤치마크 설정"""
    return {
        "iterations": 10,
        "warmup_iterations": 2,
        "ttft_target_ms": 300,
        "first_audio_target_ms": 1000,
        "barge_in_target_ms": 300,
        "wake_word_target_ms": 100,
    }
