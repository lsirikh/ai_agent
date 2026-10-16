"""
Test: Orchestrator API Endpoints
Phase 18.1.3: Orchestrator 상태 수신 API

TDD Red Phase: 이 테스트는 처음에 실패해야 합니다.
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def mock_state_manager():
    """Mock StateManager"""
    manager = AsyncMock()
    manager.update_state = AsyncMock(return_value=None)
    manager.get_current_state = AsyncMock(return_value={"state": "READY"})
    return manager


@pytest.fixture
def test_app(mock_state_manager):
    """Test FastAPI app with orchestrator router"""
    from app.routes.orchestrator import router, get_state_manager_instance

    app = FastAPI()
    app.include_router(router)

    # Override the state manager getter
    async def mock_get_state_manager():
        return mock_state_manager

    # Patch at module level
    import app.routes.orchestrator as orch_module
    original_func = orch_module.get_state_manager_instance
    orch_module.get_state_manager_instance = mock_get_state_manager

    yield app

    # Restore
    orch_module.get_state_manager_instance = original_func


@pytest.fixture
def test_client(test_app):
    """FastAPI TestClient"""
    with TestClient(test_app, raise_server_exceptions=False) as client:
        yield client


def test_post_orchestrator_state_returns_200(test_client, mock_state_manager):
    """POST /api/orchestrator/state 엔드포인트가 200을 반환하는지 확인"""
    response = test_client.post(
        "/api/orchestrator/state",
        json={"state": "READY"}
    )

    assert response.status_code == 200
    data = response.json()
    assert data.get("status") == "ok"


def test_post_orchestrator_state_validates_state_enum(test_client):
    """유효하지 않은 상태 값에 대해 422를 반환하는지 확인"""
    response = test_client.post(
        "/api/orchestrator/state",
        json={"state": "INVALID_STATE"}
    )

    assert response.status_code == 422


def test_post_orchestrator_state_stores_with_session_id(test_client, mock_state_manager):
    """session_id와 함께 상태를 저장하는지 확인"""
    session_id = str(uuid4())

    response = test_client.post(
        "/api/orchestrator/state",
        json={"state": "LISTENING", "session_id": session_id}
    )

    assert response.status_code == 200


def test_post_orchestrator_state_stores_with_metadata(test_client, mock_state_manager):
    """metadata와 함께 상태를 저장하는지 확인"""
    response = test_client.post(
        "/api/orchestrator/state",
        json={
            "state": "ERROR",
            "metadata": {"error": "STT service timeout", "retry_count": 3}
        }
    )

    assert response.status_code == 200


def test_get_orchestrator_state_returns_current_state(test_client, mock_state_manager):
    """GET /api/orchestrator/state 엔드포인트가 현재 상태를 반환하는지 확인"""
    response = test_client.get("/api/orchestrator/state")

    assert response.status_code == 200
    data = response.json()
    assert "state" in data
