"""
Tests for Session Context API

Phase 15.4: Session Context Endpoints
- GET /api/sessions/{id}/context - 세션 컨텍스트 조회
- DELETE /api/sessions/{id}/context - 세션 컨텍스트 초기화
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """FastAPI TestClient fixture"""
    from services.backend.app.main import app
    return TestClient(app)


class TestGetSessionContext:
    """GET /api/sessions/{id}/context 테스트"""

    def test_get_session_context_endpoint_exists(self, client):
        """GET /api/sessions/{id}/context 엔드포인트가 존재해야 함"""
        response = client.get("/api/sessions/test-session-123/context")
        # 404 Not Found가 아닌 다른 응답이어야 함 (엔드포인트 존재)
        assert response.status_code != 404

    def test_get_session_context_returns_message_count(self, client):
        """세션 컨텍스트 조회 시 메시지 수를 반환해야 함"""
        with patch("services.backend.app.routes.sessions.get_history_store") as mock_get_store:
            mock_store = MagicMock()
            mock_store.get_messages.return_value = [
                {"role": "user", "content": "메시지1"},
                {"role": "assistant", "content": "응답1"},
                {"role": "user", "content": "메시지2"},
                {"role": "assistant", "content": "응답2"}
            ]
            mock_get_store.return_value = mock_store

            response = client.get("/api/sessions/test-session-123/context")

            assert response.status_code == 200
            data = response.json()
            assert "message_count" in data
            assert data["message_count"] == 4

    def test_get_session_context_returns_session_id(self, client):
        """세션 컨텍스트 조회 시 세션 ID를 반환해야 함"""
        with patch("services.backend.app.routes.sessions.get_history_store") as mock_get_store:
            mock_store = MagicMock()
            mock_store.get_messages.return_value = []
            mock_get_store.return_value = mock_store

            response = client.get("/api/sessions/my-session-456/context")

            assert response.status_code == 200
            data = response.json()
            assert "session_id" in data
            assert data["session_id"] == "my-session-456"

    def test_get_session_context_empty_session(self, client):
        """빈 세션도 정상 응답해야 함"""
        with patch("services.backend.app.routes.sessions.get_history_store") as mock_get_store:
            mock_store = MagicMock()
            mock_store.get_messages.return_value = []
            mock_get_store.return_value = mock_store

            response = client.get("/api/sessions/empty-session/context")

            assert response.status_code == 200
            data = response.json()
            assert data["message_count"] == 0


class TestDeleteSessionContext:
    """DELETE /api/sessions/{id}/context 테스트"""

    def test_delete_session_context_endpoint_exists(self, client):
        """DELETE /api/sessions/{id}/context 엔드포인트가 존재해야 함"""
        response = client.delete("/api/sessions/test-session-123/context")
        # 404 Not Found가 아닌 다른 응답이어야 함 (엔드포인트 존재)
        assert response.status_code != 404

    def test_delete_session_context_clears_messages(self, client):
        """세션 컨텍스트 삭제 시 메시지가 삭제되어야 함"""
        with patch("services.backend.app.routes.sessions.get_history_store") as mock_get_store:
            mock_store = MagicMock()
            mock_store.clear_session.return_value = True
            mock_get_store.return_value = mock_store

            response = client.delete("/api/sessions/test-session-123/context")

            assert response.status_code == 200
            mock_store.clear_session.assert_called_once_with("test-session-123")

    def test_delete_session_context_returns_status(self, client):
        """세션 컨텍스트 삭제 후 상태를 반환해야 함"""
        with patch("services.backend.app.routes.sessions.get_history_store") as mock_get_store:
            mock_store = MagicMock()
            mock_store.clear_session.return_value = True
            mock_get_store.return_value = mock_store

            response = client.delete("/api/sessions/test-session-123/context")

            assert response.status_code == 200
            data = response.json()
            assert "status" in data
            assert data["status"] == "cleared"
            assert data["session_id"] == "test-session-123"

    def test_delete_session_context_nonexistent_session(self, client):
        """존재하지 않는 세션도 정상 응답해야 함 (idempotent)"""
        with patch("services.backend.app.routes.sessions.get_history_store") as mock_get_store:
            mock_store = MagicMock()
            mock_store.clear_session.return_value = False  # 삭제할 것이 없음
            mock_get_store.return_value = mock_store

            response = client.delete("/api/sessions/nonexistent-session/context")

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "cleared"
