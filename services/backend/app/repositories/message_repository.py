"""
Message Repository

Phase 14.2.4: Message Repository Implementation
- CRUD operations for messages table
- Session-based message management
- RAG context storage
"""

from typing import Any, Dict, List, Optional
from uuid import UUID
import json
import re

from .base import BaseRepository


class MessageRepository(BaseRepository):
    """
    Repository for messages table operations.

    Handles CRUD operations for chat messages with RAG context support.

    Usage:
        repo = MessageRepository()

        # Create a message
        msg_id = await repo.create(
            session_id=session_id,
            role="user",
            content="Hello!"
        )

        # Create with RAG context
        msg_id = await repo.create(
            session_id=session_id,
            role="assistant",
            content="Based on the docs...",
            rag_context="Relevant context",
            rag_sources=[{"doc_id": "doc1"}]
        )

        # Get messages for a session
        messages = await repo.get_by_session(session_id)

        # Get recent messages
        recent = await repo.get_recent(session_id, limit=10)

        # Delete all messages for a session
        count = await repo.delete_by_session(session_id)
    """

    async def create(
        self,
        session_id: UUID,
        role: str,
        content: str,
        rag_context: Optional[str] = None,
        rag_sources: Optional[List[Dict[str, Any]]] = None,
        source: str = "web"
    ) -> UUID:
        """
        Create a new message.

        Args:
            session_id: The session UUID this message belongs to
            role: Message role ('user', 'assistant', 'system')
            content: Message content text
            rag_context: Optional RAG context text
            rag_sources: Optional list of RAG source references
            source: 'web' | 'voice' | 'api'

        Returns:
            The generated message UUID
        """
        async with self.connection() as conn:
            message_id = await conn.fetchval(
                """
                INSERT INTO messages
                    (session_id, role, content, rag_context, rag_sources, source)
                VALUES ($1, $2, $3, $4, $5::jsonb, $6)
                RETURNING id
                """,
                session_id,
                role,
                content,
                rag_context,
                json.dumps(rag_sources or []),
                source
            )
            return message_id

    async def get_by_id(self, message_id: UUID) -> Optional[Dict[str, Any]]:
        """
        Get a message by its ID.

        Args:
            message_id: The message UUID

        Returns:
            Message dict with all fields, or None if not found
        """
        async with self.connection() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, session_id, role, content, rag_context, rag_sources, created_at
                FROM messages
                WHERE id = $1
                """,
                message_id
            )

            if row is None:
                return None

            return self._row_to_dict(row)

    async def get_by_session(
        self,
        session_id: UUID,
        include_system: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Get all messages for a session.

        Args:
            session_id: The session UUID
            include_system: Whether to include system messages

        Returns:
            List of message dicts ordered by created_at ASC
        """
        async with self.connection() as conn:
            if include_system:
                rows = await conn.fetch(
                    """
                    SELECT id, session_id, role, content, rag_context, rag_sources,
                           source, created_at
                    FROM messages
                    WHERE session_id = $1
                    ORDER BY created_at ASC
                    """,
                    session_id
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT id, session_id, role, content, rag_context, rag_sources,
                           source, created_at
                    FROM messages
                    WHERE session_id = $1 AND role != 'system'
                    ORDER BY created_at ASC
                    """,
                    session_id
                )

            return [self._row_to_dict(row) for row in rows]

    async def get_recent(
        self,
        session_id: UUID,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get the most recent N messages for a session.

        Args:
            session_id: The session UUID
            limit: Maximum number of messages to return

        Returns:
            List of message dicts ordered by created_at ASC (chronological)
        """
        async with self.connection() as conn:
            # Get last N messages ordered DESC, then reverse for chronological order
            rows = await conn.fetch(
                """
                SELECT id, session_id, role, content, rag_context, rag_sources, created_at
                FROM (
                    SELECT id, session_id, role, content, rag_context, rag_sources, created_at
                    FROM messages
                    WHERE session_id = $1
                    ORDER BY created_at DESC
                    LIMIT $2
                ) sub
                ORDER BY created_at ASC
                """,
                session_id,
                limit
            )

            return [self._row_to_dict(row) for row in rows]

    async def list_recent(
        self, limit: int = 100, offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Get the most recent messages across all sessions (newest first).

        Args:
            limit: Maximum number of messages to return
            offset: Number of messages to skip
        """
        async with self.connection() as conn:
            rows = await conn.fetch(
                """
                SELECT id, session_id, role, content, rag_context, rag_sources,
                       source, created_at
                FROM messages
                ORDER BY created_at DESC
                LIMIT $1 OFFSET $2
                """,
                limit,
                offset
            )

            return [self._row_to_dict(row) for row in rows]

    async def count_by_session(self, session_id: UUID) -> int:
        """
        Count messages in a session.

        Args:
            session_id: The session UUID

        Returns:
            Number of messages in the session
        """
        async with self.connection() as conn:
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM messages WHERE session_id = $1",
                session_id
            )
            return count or 0

    async def delete_by_session(self, session_id: UUID) -> int:
        """
        Delete all messages for a session.

        Args:
            session_id: The session UUID

        Returns:
            Number of messages deleted
        """
        async with self.connection() as conn:
            result = await conn.execute(
                "DELETE FROM messages WHERE session_id = $1",
                session_id
            )

            # asyncpg returns "DELETE N" where N is the number of rows deleted
            match = re.match(r"DELETE (\d+)", result)
            return int(match.group(1)) if match else 0

    async def delete(self, message_id: UUID) -> bool:
        """
        Delete a single message.

        Args:
            message_id: The message UUID

        Returns:
            True if deleted, False if not found
        """
        async with self.connection() as conn:
            result = await conn.execute(
                "DELETE FROM messages WHERE id = $1",
                message_id
            )
            return result == "DELETE 1"

    def _row_to_dict(self, row) -> Dict[str, Any]:
        """Convert a database row to a dict."""
        # asyncpg 는 JSONB 를 문자열로 돌려준다(코덱 미등록)
        sources = row["rag_sources"]
        if isinstance(sources, str):
            sources = json.loads(sources)
        return {
            "id": row["id"],
            "session_id": row["session_id"],
            "role": row["role"],
            "content": row["content"],
            "rag_context": row["rag_context"],
            "rag_sources": list(sources) if sources else [],
            "source": row.get("source"),
            "created_at": row["created_at"]
        }
