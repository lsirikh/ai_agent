"""
Test: Pipeline Message API
Phase 18.3.4: 파이프라인 메시지 API

TDD Red Phase: 이 테스트는 처음에 실패해야 합니다.
"""
import pytest
from uuid import uuid4
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def test_app():
    """Test FastAPI app with sessions router"""
    from app.routes.sessions import router
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def test_client(test_app):
    """FastAPI TestClient"""
    with TestClient(test_app, raise_server_exceptions=False) as client:
        yield client


def test_post_messages_pipeline_endpoint_exists(test_client):
    """POST /api/sessions/pipeline/messages 엔드포인트가 존재하는지 확인"""
    session_id = str(uuid4())

    response = test_client.post(
        "/api/sessions/pipeline/messages",
        json={
            "session_id": session_id,
            "role": "user",
            "content": "Hello"
        }
    )
    # 404가 아니면 엔드포인트가 존재함
    assert response.status_code != 404


def test_post_messages_pipeline_creates_with_source(test_client):
    """POST /api/sessions/pipeline/messages가 source 필드를 포함하는지 확인"""
    session_id = str(uuid4())

    response = test_client.post(
        "/api/sessions/pipeline/messages",
        json={
            "session_id": session_id,
            "role": "user",
            "content": "Hello from voice",
            "source": "voice"
        }
    )

    assert response.status_code in [200, 201]
    data = response.json()
    assert data.get("source") == "voice"


def test_post_messages_pipeline_stores_audio_url(test_client):
    """POST /api/sessions/pipeline/messages가 audio_url을 저장하는지 확인"""
    session_id = str(uuid4())
    audio_url = "http://localhost:11000/audio/test.wav"

    response = test_client.post(
        "/api/sessions/pipeline/messages",
        json={
            "session_id": session_id,
            "role": "assistant",
            "content": "Hello response",
            "source": "voice",
            "audio_url": audio_url
        }
    )

    assert response.status_code in [200, 201]
    data = response.json()
    assert data.get("audio_url") == audio_url


def test_post_messages_pipeline_returns_message_id(test_client):
    """POST /api/sessions/pipeline/messages가 메시지 ID를 반환하는지 확인"""
    session_id = str(uuid4())

    response = test_client.post(
        "/api/sessions/pipeline/messages",
        json={
            "session_id": session_id,
            "role": "user",
            "content": "Test message"
        }
    )

    assert response.status_code in [200, 201]
    data = response.json()
    assert "message_id" in data or "id" in data
