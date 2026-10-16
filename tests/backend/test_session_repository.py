"""
Test Session Repository

Phase 14.2.3: Session Repository Tests
- CRUD operations for sessions table
- UUID-based session management
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone
import uuid


class TestSessionRepoCreate:
    """Tests for SessionRepository.create() method."""

    @pytest.mark.asyncio
    async def test_session_repo_create(self):
        """
        Test that create() creates a new session and returns its ID.

        Requirements:
        - INSERT into sessions table
        - Return the generated UUID
        - Support optional user_id and title
        """
        from services.backend.app.repositories.session_repository import SessionRepository

        session_id = uuid.uuid4()
        mock_conn = AsyncMock()
        mock_conn.fetchval = AsyncMock(return_value=session_id)

        mock_pool = MagicMock()
        mock_acquire_ctx = AsyncMock()
        mock_acquire_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_acquire_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_pool.acquire = MagicMock(return_value=mock_acquire_ctx)

        from services.backend.app.database import get_db_manager
        with patch.object(get_db_manager(), '_pool', mock_pool):
            repo = SessionRepository()
            result = await repo.create(user_id="user123", title="Test Session")

            assert result == session_id
            mock_conn.fetchval.assert_called_once()
            call_args = mock_conn.fetchval.call_args
            sql = call_args[0][0].upper()
            assert "INSERT INTO SESSIONS" in sql
            assert "RETURNING ID" in sql


class TestSessionRepoGetById:
    """Tests for SessionRepository.get_by_id() method."""

    @pytest.mark.asyncio
    async def test_session_repo_get_by_id(self):
        """
        Test that get_by_id() returns session data by UUID.

        Requirements:
        - Query sessions table by id
        - Return session dict with all fields
        """
        from services.backend.app.repositories.session_repository import SessionRepository

        session_id = uuid.uuid4()
        now = datetime.now(timezone.utc)
        mock_row = {
            "id": session_id,
            "user_id": "user123",
            "title": "Test Session",
            "created_at": now,
            "last_active_at": now,
            "metadata": {}
        }

        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value=mock_row)

        mock_pool = MagicMock()
        mock_acquire_ctx = AsyncMock()
        mock_acquire_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_acquire_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_pool.acquire = MagicMock(return_value=mock_acquire_ctx)

        from services.backend.app.database import get_db_manager
        with patch.object(get_db_manager(), '_pool', mock_pool):
            repo = SessionRepository()
            result = await repo.get_by_id(session_id)

            assert result["id"] == session_id
            assert result["user_id"] == "user123"
            assert result["title"] == "Test Session"
            mock_conn.fetchrow.assert_called_once()


class TestSessionRepoUpdateLastActive:
    """Tests for SessionRepository.update_last_active() method."""

    @pytest.mark.asyncio
    async def test_session_repo_update_last_active(self):
        """
        Test that update_last_active() updates the last_active_at timestamp.

        Requirements:
        - UPDATE sessions SET last_active_at = NOW()
        - Identify session by id
        """
        from services.backend.app.repositories.session_repository import SessionRepository

        session_id = uuid.uuid4()
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock(return_value="UPDATE 1")

        mock_pool = MagicMock()
        mock_acquire_ctx = AsyncMock()
        mock_acquire_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_acquire_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_pool.acquire = MagicMock(return_value=mock_acquire_ctx)

        from services.backend.app.database import get_db_manager
        with patch.object(get_db_manager(), '_pool', mock_pool):
            repo = SessionRepository()
            await repo.update_last_active(session_id)

            mock_conn.execute.assert_called_once()
            call_args = mock_conn.execute.call_args
            sql = call_args[0][0].upper()
            assert "UPDATE SESSIONS" in sql
            assert "LAST_ACTIVE_AT" in sql


class TestSessionRepoListRecent:
    """Tests for SessionRepository.list_recent() method."""

    @pytest.mark.asyncio
    async def test_session_repo_list_recent(self):
        """
        Test that list_recent() returns sessions ordered by last_active_at.

        Requirements:
        - ORDER BY last_active_at DESC
        - Support limit parameter
        - Return list of session dicts
        """
        from services.backend.app.repositories.session_repository import SessionRepository

        now = datetime.now(timezone.utc)
        mock_rows = [
            {"id": uuid.uuid4(), "user_id": "user1", "title": "Session 1", "created_at": now, "last_active_at": now, "metadata": {}},
            {"id": uuid.uuid4(), "user_id": "user1", "title": "Session 2", "created_at": now, "last_active_at": now, "metadata": {}},
        ]

        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=mock_rows)

        mock_pool = MagicMock()
        mock_acquire_ctx = AsyncMock()
        mock_acquire_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_acquire_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_pool.acquire = MagicMock(return_value=mock_acquire_ctx)

        from services.backend.app.database import get_db_manager
        with patch.object(get_db_manager(), '_pool', mock_pool):
            repo = SessionRepository()
            result = await repo.list_recent(limit=10)

            assert len(result) == 2
            assert result[0]["title"] == "Session 1"
            mock_conn.fetch.assert_called_once()
            call_args = mock_conn.fetch.call_args
            sql = call_args[0][0].upper()
            assert "ORDER BY LAST_ACTIVE_AT DESC" in sql
            assert "LIMIT" in sql


class TestSessionRepoDelete:
    """Tests for SessionRepository.delete() method."""

    @pytest.mark.asyncio
    async def test_session_repo_delete(self):
        """
        Test that delete() removes a session by id.

        Requirements:
        - DELETE FROM sessions WHERE id = $1
        - Return True if deleted, False if not found
        - Cascade delete should handle related messages
        """
        from services.backend.app.repositories.session_repository import SessionRepository

        session_id = uuid.uuid4()
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock(return_value="DELETE 1")

        mock_pool = MagicMock()
        mock_acquire_ctx = AsyncMock()
        mock_acquire_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_acquire_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_pool.acquire = MagicMock(return_value=mock_acquire_ctx)

        from services.backend.app.database import get_db_manager
        with patch.object(get_db_manager(), '_pool', mock_pool):
            repo = SessionRepository()
            result = await repo.delete(session_id)

            assert result is True
            mock_conn.execute.assert_called_once()
            call_args = mock_conn.execute.call_args
            sql = call_args[0][0].upper()
            assert "DELETE FROM SESSIONS" in sql
