"""
Integration Test Fixtures

Phase 6.1: 통합 테스트용 공통 픽스처
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import asyncio


@pytest.fixture
def mock_redis():
    """Mock Redis client for integration tests"""
    redis_mock = MagicMock()
    redis_mock.publish = AsyncMock(return_value=1)
    redis_mock.subscribe = AsyncMock()
    redis_mock.get = AsyncMock(return_value=None)
    redis_mock.set = AsyncMock(return_value=True)
    redis_mock.delete = AsyncMock(return_value=1)
    return redis_mock


@pytest.fixture
def mock_stt_service():
    """Mock STT Service"""
    service = MagicMock()
    service.transcribe = AsyncMock(return_value={
        "text": "안녕하세요",
        "confidence": 0.95,
        "language": "ko"
    })
    service.transcribe_stream = AsyncMock()
    return service


@pytest.fixture
def mock_llm_service():
    """Mock LLM Service"""
    service = MagicMock()
    service.generate = AsyncMock(return_value={
        "text": "안녕하세요! 무엇을 도와드릴까요?",
        "tokens_used": 50
    })

    async def mock_stream():
        tokens = ["안녕", "하세요", "!", " 무엇을", " 도와드릴까요", "?"]
        for token in tokens:
            yield {"token": token, "finished": False}
        yield {"token": "", "finished": True}

    service.generate_stream = mock_stream
    return service


@pytest.fixture
def mock_tts_service():
    """Mock TTS Service"""
    import numpy as np
    service = MagicMock()

    # Generate fake audio data
    sample_rate = 24000
    duration = 1.0
    samples = int(sample_rate * duration)
    audio_data = (np.sin(2 * np.pi * 440 * np.linspace(0, duration, samples)) * 32767).astype(np.int16)

    service.synthesize = AsyncMock(return_value={
        "audio": audio_data.tobytes(),
        "sample_rate": sample_rate,
        "duration": duration
    })

    async def mock_stream():
        chunk_size = 4800  # 0.2 seconds
        for i in range(0, len(audio_data), chunk_size):
            chunk = audio_data[i:i+chunk_size]
            yield {"audio": chunk.tobytes(), "finished": False}
        yield {"audio": b"", "finished": True}

    service.synthesize_stream = mock_stream
    return service


@pytest.fixture
def mock_embedding_service():
    """Mock Embedding Service"""
    import numpy as np
    service = MagicMock()
    service.embed = AsyncMock(return_value={
        "embedding": np.random.rand(1024).tolist(),
        "dimension": 1024
    })
    service.embed_batch = AsyncMock(return_value={
        "embeddings": [np.random.rand(1024).tolist() for _ in range(5)],
        "dimension": 1024
    })
    return service


@pytest.fixture
def mock_rag_service():
    """Mock RAG Service"""
    service = MagicMock()
    service.retrieve = AsyncMock(return_value=[
        {"content": "관련 문서 내용 1", "score": 0.9, "metadata": {"source": "doc1.txt"}},
        {"content": "관련 문서 내용 2", "score": 0.8, "metadata": {"source": "doc2.txt"}}
    ])
    service.add_document = AsyncMock(return_value={"id": "doc-001", "chunks": 5})
    return service


@pytest.fixture
def sample_audio_data():
    """Generate sample audio data for testing"""
    import numpy as np
    sample_rate = 16000
    duration = 2.0
    samples = int(sample_rate * duration)
    # Generate simple sine wave
    audio = (np.sin(2 * np.pi * 440 * np.linspace(0, duration, samples)) * 32767).astype(np.int16)
    return {
        "audio": audio.tobytes(),
        "sample_rate": sample_rate,
        "duration": duration
    }


@pytest.fixture
def event_loop():
    """Create event loop for async tests"""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()
