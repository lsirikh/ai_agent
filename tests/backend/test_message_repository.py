"""
Test Message Repository

Phase 14.2.4: Message Repository Tests
- CRUD operations for messages table
- Session-based message management
- RAG context storage
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone
import uuid


class TestMessageRepoCreate:
    """Tests for MessageRepository.create() method."""

    @pytest.mark.asyncio
    async def test_message_repo_create(self):
        """
        Test that create() creates a new message and returns its ID.

        Requirements:
        - INSERT into messages table
        - Return the generated UUID
        - Support session_id, role, content
        """
        from services.backend.app.repositories.message_repository import MessageRepository

        message_id = uuid.uuid4()
        session_id = uuid.uuid4()

        mock_conn = AsyncMock()
        mock_conn.fetchval = AsyncMock(return_value=message_id)

        mock_pool = MagicMock()
        mock_acquire_ctx = AsyncMock()
        mock_acquire_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_acquire_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_pool.acquire = MagicMock(return_value=mock_acquire_ctx)

        from services.backend.app.database import get_db_manager
        with patch.object(get_db_manager(), '_pool', mock_pool):
            repo = MessageRepository()
            result = await repo.create(
                session_id=session_id,
                role="user",
                content="Hello, how are you?"
            )

            assert result == message_id
            mock_conn.fetchval.assert_called_once()
            call_args = mock_conn.fetchval.call_args
            sql = call_args[0][0].upper()
            assert "INSERT INTO MESSAGES" in sql
            assert "RETURNING ID" in sql


class TestMessageRepoGetBySession:
    """Tests for MessageRepository.get_by_session() method."""

    @pytest.mark.asyncio
    async def test_message_repo_get_by_session(self):
        """
        Test that get_by_session() returns messages for a session.

        Requirements:
        - Query messages by session_id
        - Order by created_at ASC (oldest first)
        - Return list of message dicts
        """
        from services.backend.app.repositories.message_repository import MessageRepository

        session_id = uuid.uuid4()
        now = datetime.now(timezone.utc)

        mock_rows = [
            {"id": uuid.uuid4(), "session_id": session_id, "role": "user", "content": "Hello", "rag_context": None, "rag_sources": [], "created_at": now},
            {"id": uuid.uuid4(), "session_id": session_id, "role": "assistant", "content": "Hi there!", "rag_context": None, "rag_sources": [], "created_at": now},
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
            repo = MessageRepository()
            result = await repo.get_by_session(session_id)

            assert len(result) == 2
            assert result[0]["role"] == "user"
            assert result[1]["role"] == "assistant"
            mock_conn.fetch.assert_called_once()
            call_args = mock_conn.fetch.call_args
            sql = call_args[0][0].upper()
            assert "SESSION_ID" in sql
            assert "ORDER BY CREATED_AT" in sql


class TestMessageRepoGetRecent:
    """Tests for MessageRepository.get_recent() method."""

    @pytest.mark.asyncio
    async def test_message_repo_get_recent(self):
        """
        Test that get_recent() returns the last N messages for a session.

        Requirements:
        - LIMIT to N messages
        - Order by created_at DESC then reverse for chronological order
        """
        from services.backend.app.repositories.message_repository import MessageRepository

        session_id = uuid.uuid4()
        now = datetime.now(timezone.utc)

        mock_rows = [
            {"id": uuid.uuid4(), "session_id": session_id, "role": "user", "content": "Recent message", "rag_context": None, "rag_sources": [], "created_at": now},
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
            repo = MessageRepository()
            result = await repo.get_recent(session_id, limit=10)

            assert len(result) == 1
            mock_conn.fetch.assert_called_once()
            call_args = mock_conn.fetch.call_args
            sql = call_args[0][0].upper()
            assert "LIMIT" in sql


class TestMessageRepoWithRagContext:
    """Tests for MessageRepository with RAG context."""

    @pytest.mark.asyncio
    async def test_message_repo_with_rag_context(self):
        """
        Test that create() stores RAG context and sources.

        Requirements:
        - Store rag_context as TEXT
        - Store rag_sources as JSONB array
        """
        from services.backend.app.repositories.message_repository import MessageRepository

        message_id = uuid.uuid4()
        session_id = uuid.uuid4()

        mock_conn = AsyncMock()
        mock_conn.fetchval = AsyncMock(return_value=message_id)

        mock_pool = MagicMock()
        mock_acquire_ctx = AsyncMock()
        mock_acquire_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_acquire_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_pool.acquire = MagicMock(return_value=mock_acquire_ctx)

        from services.backend.app.database import get_db_manager
        with patch.object(get_db_manager(), '_pool', mock_pool):
            repo = MessageRepository()
            result = await repo.create(
                session_id=session_id,
                role="assistant",
                content="Based on the documentation...",
                rag_context="Relevant context from documents",
                rag_sources=[{"doc_id": "doc1", "chunk": 0}]
            )

            assert result == message_id
            mock_conn.fetchval.assert_called_once()
            call_args = mock_conn.fetchval.call_args
            sql = call_args[0][0].upper()
            assert "RAG_CONTEXT" in sql
            assert "RAG_SOURCES" in sql


class TestMessageRepoDeleteBySession:
    """Tests for MessageRepository.delete_by_session() method."""

    @pytest.mark.asyncio
    async def test_message_repo_delete_by_session(self):
        """
        Test that delete_by_session() removes all messages for a session.

        Requirements:
        - DELETE FROM messages WHERE session_id = $1
        - Return count of deleted messages
        """
        from services.backend.app.repositories.message_repository import MessageRepository

        session_id = uuid.uuid4()

        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock(return_value="DELETE 5")

        mock_pool = MagicMock()
        mock_acquire_ctx = AsyncMock()
        mock_acquire_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_acquire_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_pool.acquire = MagicMock(return_value=mock_acquire_ctx)

        from services.backend.app.database import get_db_manager
        with patch.object(get_db_manager(), '_pool', mock_pool):
            repo = MessageRepository()
            result = await repo.delete_by_session(session_id)

            assert result == 5
            mock_conn.execute.assert_called_once()
            call_args = mock_conn.execute.call_args
            sql = call_args[0][0].upper()
            assert "DELETE FROM MESSAGES" in sql
            assert "SESSION_ID" in sql
