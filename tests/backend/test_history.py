"""
Backend API Chat History Tests

Phase 5.4: Backend API - Chat History 테스트
"""
import json
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


class TestGetHistory:
    """대화 기록 조회 테스트"""

    def test_get_history(self):
        """대화 기록을 조회할 수 있어야 한다"""
        from services.backend.app.main import app

        client = TestClient(app)

        with patch("services.backend.app.routes.history.get_history_store") as mock_store:
            mock_store.return_value.get_messages.return_value = [
                {
                    "id": "msg-001",
                    "session_id": "session-001",
                    "role": "user",
                    "content": "안녕하세요",
                    "timestamp": "2024-01-01T10:00:00"
                },
                {
                    "id": "msg-002",
                    "session_id": "session-001",
                    "role": "assistant",
                    "content": "안녕하세요! 무엇을 도와드릴까요?",
                    "timestamp": "2024-01-01T10:00:01"
                }
            ]

            response = client.get("/api/history")

        assert response.status_code == 200
        data = response.json()
        assert "messages" in data
        assert len(data["messages"]) == 2

    def test_get_history_empty(self):
        """대화 기록이 없을 때 빈 목록 반환"""
        from services.backend.app.main import app

        client = TestClient(app)

        with patch("services.backend.app.routes.history.get_history_store") as mock_store:
            mock_store.return_value.get_messages.return_value = []

            response = client.get("/api/history")

        assert response.status_code == 200
        data = response.json()
        assert data["messages"] == []


class TestHistorySessionFilter:
    """세션별 필터 테스트"""

    def test_get_history_with_session_filter(self):
        """세션별로 대화 기록을 필터링할 수 있어야 한다"""
        from services.backend.app.main import app

        client = TestClient(app)

        with patch("services.backend.app.routes.history.get_history_store") as mock_store:
            mock_store.return_value.get_messages.return_value = [
                {
                    "id": "msg-001",
                    "session_id": "session-001",
                    "role": "user",
                    "content": "질문",
                    "timestamp": "2024-01-01T10:00:00"
                }
            ]

            response = client.get("/api/history?session_id=session-001")

        assert response.status_code == 200
        mock_store.return_value.get_messages.assert_called_once()
        call_kwargs = mock_store.return_value.get_messages.call_args
        assert call_kwargs.kwargs.get("session_id") == "session-001" or \
               (call_kwargs.args and call_kwargs.args[0] == "session-001")

    def test_list_sessions(self):
        """세션 목록을 조회할 수 있어야 한다"""
        from services.backend.app.main import app

        client = TestClient(app)

        with patch("services.backend.app.routes.history.get_history_store") as mock_store:
            mock_store.return_value.list_sessions.return_value = [
                {"session_id": "session-001", "created_at": "2024-01-01T10:00:00", "message_count": 10},
                {"session_id": "session-002", "created_at": "2024-01-02T10:00:00", "message_count": 5}
            ]

            response = client.get("/api/history/sessions")

        assert response.status_code == 200
        data = response.json()
        assert "sessions" in data
        assert len(data["sessions"]) == 2


class TestHistoryPagination:
    """페이지네이션 테스트"""

    def test_get_history_pagination(self):
        """페이지네이션을 지원해야 한다"""
        from services.backend.app.main import app

        client = TestClient(app)

        with patch("services.backend.app.routes.history.get_history_store") as mock_store:
            mock_store.return_value.get_messages.return_value = [
                {"id": f"msg-{i}", "session_id": "session-001", "role": "user", "content": f"메시지 {i}", "timestamp": f"2024-01-01T10:00:{i:02d}"}
                for i in range(10)
            ]

            response = client.get("/api/history?limit=10&offset=0")

        assert response.status_code == 200
        data = response.json()
        assert len(data["messages"]) <= 10

    def test_get_history_with_offset(self):
        """offset으로 페이지를 건너뛸 수 있어야 한다"""
        from services.backend.app.main import app

        client = TestClient(app)

        with patch("services.backend.app.routes.history.get_history_store") as mock_store:
            mock_store.return_value.get_messages.return_value = []

            response = client.get("/api/history?limit=10&offset=20")

        assert response.status_code == 200
        mock_store.return_value.get_messages.assert_called_once()


class TestExportHistoryJSON:
    """JSON 내보내기 테스트"""

    def test_export_history_json(self):
        """대화 기록을 JSON으로 내보낼 수 있어야 한다"""
        from services.backend.app.main import app

        client = TestClient(app)

        with patch("services.backend.app.routes.history.get_history_store") as mock_store:
            mock_store.return_value.get_messages.return_value = [
                {
                    "id": "msg-001",
                    "session_id": "session-001",
                    "role": "user",
                    "content": "안녕하세요",
                    "timestamp": "2024-01-01T10:00:00"
                },
                {
                    "id": "msg-002",
                    "session_id": "session-001",
                    "role": "assistant",
                    "content": "안녕하세요!",
                    "timestamp": "2024-01-01T10:00:01"
                }
            ]

            response = client.get("/api/history/export?format=json")

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/json"

        data = response.json()
        assert "messages" in data
        assert len(data["messages"]) == 2

    def test_export_history_json_with_session(self):
        """특정 세션의 대화 기록을 JSON으로 내보낼 수 있어야 한다"""
        from services.backend.app.main import app

        client = TestClient(app)

        with patch("services.backend.app.routes.history.get_history_store") as mock_store:
            mock_store.return_value.get_messages.return_value = [
                {"id": "msg-001", "session_id": "session-001", "role": "user", "content": "질문", "timestamp": "2024-01-01T10:00:00"}
            ]

            response = client.get("/api/history/export?format=json&session_id=session-001")

        assert response.status_code == 200


class TestExportHistoryCSV:
    """CSV 내보내기 테스트"""

    def test_export_history_csv(self):
        """대화 기록을 CSV로 내보낼 수 있어야 한다"""
        from services.backend.app.main import app

        client = TestClient(app)

        with patch("services.backend.app.routes.history.get_history_store") as mock_store:
            mock_store.return_value.get_messages.return_value = [
                {
                    "id": "msg-001",
                    "session_id": "session-001",
                    "role": "user",
                    "content": "안녕하세요",
                    "timestamp": "2024-01-01T10:00:00"
                },
                {
                    "id": "msg-002",
                    "session_id": "session-001",
                    "role": "assistant",
                    "content": "안녕하세요!",
                    "timestamp": "2024-01-01T10:00:01"
                }
            ]

            response = client.get("/api/history/export?format=csv")

        assert response.status_code == 200
        assert "text/csv" in response.headers["content-type"]

        content = response.text
        assert "id" in content or "session_id" in content  # CSV 헤더 확인
        assert "msg-001" in content
        assert "안녕하세요" in content

    def test_export_invalid_format(self):
        """지원하지 않는 형식은 거부해야 한다"""
        from services.backend.app.main import app

        client = TestClient(app)

        response = client.get("/api/history/export?format=xml")

        assert response.status_code == 400


class TestAddMessage:
    """메시지 추가 테스트"""

    def test_add_message(self):
        """대화 기록에 메시지를 추가할 수 있어야 한다"""
        from services.backend.app.main import app

        client = TestClient(app)

        with patch("services.backend.app.routes.history.get_history_store") as mock_store:
            mock_store.return_value.add_message.return_value = "msg-new-001"
            mock_store.return_value.get_messages.return_value = [
                {
                    "id": "msg-new-001",
                    "session_id": "session-001",
                    "role": "user",
                    "content": "새로운 메시지",
                    "timestamp": "2024-01-01T10:00:00"
                }
            ]

            response = client.post("/api/history/messages", json={
                "session_id": "session-001",
                "role": "user",
                "content": "새로운 메시지"
            })

        assert response.status_code == 200
        data = response.json()
        assert "id" in data

    def test_add_message_creates_session(self):
        """새 세션 ID로 메시지 추가 시 세션이 생성되어야 한다"""
        from services.backend.app.main import app

        client = TestClient(app)

        with patch("services.backend.app.routes.history.get_history_store") as mock_store:
            mock_store.return_value.add_message.return_value = "msg-new-002"
            mock_store.return_value.get_messages.return_value = [
                {
                    "id": "msg-new-002",
                    "session_id": "new-session",
                    "role": "user",
                    "content": "첫 번째 메시지",
                    "timestamp": "2024-01-01T10:00:00"
                }
            ]

            response = client.post("/api/history/messages", json={
                "session_id": "new-session",
                "role": "user",
                "content": "첫 번째 메시지"
            })

        assert response.status_code == 200


class TestClearHistory:
    """기록 삭제 테스트"""

    def test_clear_session_history(self):
        """특정 세션의 대화 기록을 삭제할 수 있어야 한다"""
        from services.backend.app.main import app

        client = TestClient(app)

        with patch("services.backend.app.routes.history.get_history_store") as mock_store:
            mock_store.return_value.clear_session.return_value = True

            response = client.delete("/api/history/sessions/session-001")

        assert response.status_code == 200
        data = response.json()
        assert data["deleted"] is True

    def test_clear_all_history(self):
        """전체 대화 기록을 삭제할 수 있어야 한다"""
        from services.backend.app.main import app

        client = TestClient(app)

        with patch("services.backend.app.routes.history.get_history_store") as mock_store:
            mock_store.return_value.clear_all.return_value = True

            response = client.delete("/api/history/all")

        assert response.status_code == 200
        data = response.json()
        assert data["deleted"] is True
