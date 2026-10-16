"""
Test: Pipeline Session API
Phase 18.3.3: 파이프라인 세션 API

TDD Red Phase: 이 테스트는 처음에 실패해야 합니다.
"""
import pytest
from unittest.mock import AsyncMock
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


def test_post_sessions_pipeline_endpoint_exists(test_client):
    """POST /api/sessions/pipeline 엔드포인트가 존재하는지 확인"""
    response = test_client.post(
        "/api/sessions/pipeline",
        json={"session_id": str(uuid4())}
    )
    # 404가 아니면 엔드포인트가 존재함
    assert response.status_code != 404


def test_post_sessions_pipeline_creates_voice_session(test_client):
    """POST /api/sessions/pipeline이 VOICE 타입 세션을 생성하는지 확인"""
    session_id = str(uuid4())

    response = test_client.post(
        "/api/sessions/pipeline",
        json={"session_id": session_id, "source": "orchestrator"}
    )

    assert response.status_code in [200, 201]
    data = response.json()
    assert data.get("type") == "voice" or data.get("session_type") == "voice"


def test_post_sessions_pipeline_returns_session_id(test_client):
    """POST /api/sessions/pipeline이 세션 ID를 반환하는지 확인"""
    session_id = str(uuid4())

    response = test_client.post(
        "/api/sessions/pipeline",
        json={"session_id": session_id}
    )

    assert response.status_code in [200, 201]
    data = response.json()
    assert "session_id" in data or "id" in data
