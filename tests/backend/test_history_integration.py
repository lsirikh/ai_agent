"""
Test History Integration

Phase 14.3.2: History Router Integration Tests
- POST /api/history/messages saves to DB
- GET /api/history loads from DB
- GET /api/history/sessions loads from DB
- GET /api/history/export uses DB data
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport
from datetime import datetime, timezone
import uuid


class TestHistorySavedToDb:
    """Tests for POST /api/history/messages saving to DB."""

    @pytest.mark.asyncio
    async def test_history_saved_to_db(self):
        """
        Test that POST /api/history/messages saves message to the database.

        Requirements:
        - Call POST /api/history/messages
        - Verify message is stored (via HistoryStore which will be DB-backed)
        """
        from services.backend.app.main import app
        from services.backend.app.routes.history import get_history_store

        # Get or create the store
        store = get_history_store()
        initial_count = len(store._messages)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/history/messages",
                json={
                    "session_id": "test-session-123",
                    "role": "user",
                    "content": "Hello, this is a test message"
                }
            )

            assert response.status_code == 200
            data = response.json()
            assert data["role"] == "user"
            assert data["content"] == "Hello, this is a test message"
            assert data["session_id"] == "test-session-123"
            assert "id" in data
            assert "timestamp" in data

            # Verify message was stored
            assert len(store._messages) > initial_count


class TestHistoryLoadedFromDb:
    """Tests for GET /api/history loading from DB."""

    @pytest.mark.asyncio
    async def test_history_loaded_from_db(self):
        """
        Test that GET /api/history loads messages from storage.

        Requirements:
        - Add messages to storage
        - Call GET /api/history
        - Verify response contains stored messages
        """
        from services.backend.app.main import app
        from services.backend.app.routes.history import get_history_store

        store = get_history_store()
        session_id = f"test-session-{uuid.uuid4().hex[:8]}"

        # Add test messages
        store.add_message(session_id, "user", "First message")
        store.add_message(session_id, "assistant", "Response message")

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/api/history",
                params={"session_id": session_id}
            )

            assert response.status_code == 200
            data = response.json()
            assert "messages" in data
            assert len(data["messages"]) >= 2

            # Verify message content
            contents = [m["content"] for m in data["messages"]]
            assert "First message" in contents
            assert "Response message" in contents


class TestHistorySessionListFromDb:
    """Tests for GET /api/history/sessions loading from DB."""

    @pytest.mark.asyncio
    async def test_history_session_list_from_db(self):
        """
        Test that GET /api/history/sessions loads session list from storage.

        Requirements:
        - Add messages to create sessions
        - Call GET /api/history/sessions
        - Verify response contains session info
        """
        from services.backend.app.main import app
        from services.backend.app.routes.history import get_history_store

        store = get_history_store()
        session_id = f"list-test-session-{uuid.uuid4().hex[:8]}"

        # Add message to create a session
        store.add_message(session_id, "user", "Test message for session list")

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/history/sessions")

            assert response.status_code == 200
            data = response.json()
            assert "sessions" in data

            # Find our test session
            session_ids = [s["session_id"] for s in data["sessions"]]
            assert session_id in session_ids

            # Verify session info
            our_session = next(s for s in data["sessions"] if s["session_id"] == session_id)
            assert our_session["message_count"] >= 1
            assert "created_at" in our_session


class TestHistoryExportFromDb:
    """Tests for GET /api/history/export using DB data."""

    @pytest.mark.asyncio
    async def test_history_export_from_db(self):
        """
        Test that GET /api/history/export uses stored data.

        Requirements:
        - Add messages to storage
        - Call GET /api/history/export
        - Verify exported data matches stored messages
        """
        from services.backend.app.main import app
        from services.backend.app.routes.history import get_history_store

        store = get_history_store()
        session_id = f"export-test-session-{uuid.uuid4().hex[:8]}"

        # Add test messages
        store.add_message(session_id, "user", "Export test message 1")
        store.add_message(session_id, "assistant", "Export test response")

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Test JSON export
            response = await client.get(
                "/api/history/export",
                params={"format": "json", "session_id": session_id}
            )

            assert response.status_code == 200
            data = response.json()
            assert "messages" in data
            assert "exported_at" in data

            # Verify exported messages
            contents = [m["content"] for m in data["messages"]]
            assert "Export test message 1" in contents
            assert "Export test response" in contents

    @pytest.mark.asyncio
    async def test_history_export_csv_format(self):
        """
        Test that GET /api/history/export supports CSV format.
        """
        from services.backend.app.main import app
        from services.backend.app.routes.history import get_history_store

        store = get_history_store()
        session_id = f"csv-export-session-{uuid.uuid4().hex[:8]}"

        # Add test message
        store.add_message(session_id, "user", "CSV export test")

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/api/history/export",
                params={"format": "csv", "session_id": session_id}
            )

            assert response.status_code == 200
            assert "text/csv" in response.headers.get("content-type", "")

            # Verify CSV content
            csv_content = response.text
            assert "id,session_id,role,content,timestamp" in csv_content
            assert "CSV export test" in csv_content
