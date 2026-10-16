"""
E2E Test Fixtures

Phase 6.2: E2E 테스트용 공통 fixtures
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
import asyncio
import numpy as np


@pytest.fixture
def mock_audio_input():
    """Mock audio input stream"""
    # 16kHz, 16-bit audio (1 second)
    sample_rate = 16000
    duration = 1.0
    samples = int(sample_rate * duration)
    audio_data = np.random.randint(-32768, 32767, size=samples, dtype=np.int16)
    return {
        "audio": audio_data.tobytes(),
        "sample_rate": sample_rate,
        "channels": 1,
        "duration": duration
    }


@pytest.fixture
def mock_audio_output():
    """Mock audio output stream"""
    output = MagicMock()
    output.play = AsyncMock()
    output.stop = MagicMock()
    output.is_playing = False
    return output


@pytest.fixture
def mock_services():
    """Mock all services for E2E testing"""
    services = {
        "stt": MagicMock(),
        "llm": MagicMock(),
        "tts": MagicMock(),
        "wake_word": MagicMock(),
        "rag": MagicMock(),
        "embedding": MagicMock(),
    }

    # STT mock
    services["stt"].transcribe = AsyncMock(return_value={
        "text": "안녕하세요",
        "confidence": 0.95,
        "language": "ko"
    })
    services["stt"].health = AsyncMock(return_value={"status": "healthy"})

    # LLM mock
    services["llm"].generate = AsyncMock(return_value={
        "text": "안녕하세요! 무엇을 도와드릴까요?",
        "tokens_used": 20
    })

    async def mock_stream():
        tokens = ["안녕", "하세요", "!", " ", "무엇", "을", " ", "도와", "드릴", "까요", "?"]
        for token in tokens:
            yield {"token": token, "finished": False}
        yield {"token": "", "finished": True}

    services["llm"].generate_stream = mock_stream
    services["llm"].health = AsyncMock(return_value={"status": "healthy"})

    # TTS mock
    services["tts"].synthesize = AsyncMock(return_value={
        "audio": np.random.randint(-32768, 32767, size=24000, dtype=np.int16).tobytes(),
        "sample_rate": 24000,
        "duration": 1.0
    })
    services["tts"].health = AsyncMock(return_value={"status": "healthy"})

    # Wake Word mock
    services["wake_word"].detect = AsyncMock(return_value={
        "detected": True,
        "confidence": 0.9,
        "keyword": "헤이 로봇"
    })
    services["wake_word"].health = AsyncMock(return_value={"status": "healthy"})

    # RAG mock
    services["rag"].retrieve = AsyncMock(return_value=[
        {"content": "관련 문서 내용", "score": 0.85, "metadata": {"source": "doc1.txt"}}
    ])
    services["rag"].add_document = AsyncMock(return_value={"id": "doc-123", "chunks": 5})
    services["rag"].health = AsyncMock(return_value={"status": "healthy"})

    # Embedding mock
    services["embedding"].embed = AsyncMock(return_value={
        "embedding": np.random.randn(1024).tolist(),
        "dimension": 1024
    })
    services["embedding"].health = AsyncMock(return_value={"status": "healthy"})

    return services


@pytest.fixture
def mock_redis_pubsub():
    """Mock Redis pub/sub for event testing"""
    pubsub = MagicMock()
    pubsub.subscribe = AsyncMock()
    pubsub.unsubscribe = AsyncMock()
    pubsub.publish = AsyncMock()

    events_queue = asyncio.Queue()

    async def get_message():
        try:
            return await asyncio.wait_for(events_queue.get(), timeout=0.1)
        except asyncio.TimeoutError:
            return None

    pubsub.get_message = get_message
    pubsub.put_event = events_queue.put

    return pubsub


@pytest.fixture
def mock_database():
    """Mock database for E2E testing"""
    db = MagicMock()

    sessions = []
    messages = []
    documents = []

    async def create_session():
        session_id = f"session-{len(sessions)}"
        sessions.append({"id": session_id, "created_at": "2024-01-01T12:00:00"})
        return session_id

    async def add_message(session_id, role, content):
        msg_id = f"msg-{len(messages)}"
        messages.append({
            "id": msg_id,
            "session_id": session_id,
            "role": role,
            "content": content,
            "timestamp": "2024-01-01T12:00:00"
        })
        return msg_id

    async def get_messages(session_id=None, limit=50, offset=0):
        filtered = messages
        if session_id:
            filtered = [m for m in messages if m["session_id"] == session_id]
        return filtered[offset:offset + limit]

    async def add_document(filename, content):
        doc_id = f"doc-{len(documents)}"
        documents.append({
            "id": doc_id,
            "filename": filename,
            "content": content,
            "uploaded_at": "2024-01-01T12:00:00"
        })
        return doc_id

    db.create_session = create_session
    db.add_message = add_message
    db.get_messages = get_messages
    db.add_document = add_document
    db.sessions = sessions
    db.messages = messages
    db.documents = documents

    return db


@pytest.fixture
def e2e_config():
    """E2E test configuration"""
    return {
        "backend_url": "http://localhost:11000",
        "stt_url": "http://localhost:11001",
        "tts_url": "http://localhost:11002",
        "llm_url": "http://localhost:11003",
        "embedding_url": "http://localhost:11004",
        "timeout": 30,
        "retry_count": 3,
    }
