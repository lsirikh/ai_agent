"""
Session Repository

Phase 14.2.3: Session Repository Implementation
- CRUD operations for sessions table
- UUID-based session management
"""

from typing import Any, Dict, List, Optional
from uuid import UUID
import json

from .base import BaseRepository


class SessionRepository(BaseRepository):
    """
    Repository for sessions table operations.

    Handles CRUD operations for chat sessions.

    Usage:
        repo = SessionRepository()

        # Create a new session
        session_id = await repo.create(user_id="user123", title="Chat Session")

        # Get session by ID
        session = await repo.get_by_id(session_id)

        # Update last active timestamp
        await repo.update_last_active(session_id)

        # List recent sessions
        sessions = await repo.list_recent(limit=10)

        # Delete a session
        await repo.delete(session_id)
    """

    async def create(
        self,
        user_id: Optional[str] = None,
        title: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> UUID:
        """
        Create a new session.

        Args:
            user_id: Optional user identifier
            title: Optional session title
            metadata: Optional metadata dict

        Returns:
            The generated session UUID
        """
        async with self.connection() as conn:
            session_id = await conn.fetchval(
                """
                INSERT INTO sessions (user_id, title, metadata)
                VALUES ($1, $2, $3::jsonb)
                RETURNING id
                """,
                user_id,
                title,
                json.dumps(metadata or {})
            )
            return session_id

    async def get_by_id(self, session_id: UUID) -> Optional[Dict[str, Any]]:
        """
        Get a session by its ID.

        Args:
            session_id: The session UUID

        Returns:
            Session dict with all fields, or None if not found
        """
        async with self.connection() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, user_id, title, created_at, last_active_at, metadata
                FROM sessions
                WHERE id = $1
                """,
                session_id
            )

            if row is None:
                return None

            return {
                "id": row["id"],
                "user_id": row["user_id"],
                "title": row["title"],
                "created_at": row["created_at"],
                "last_active_at": row["last_active_at"],
                "metadata": dict(row["metadata"]) if row["metadata"] else {}
            }

    async def update_last_active(self, session_id: UUID) -> None:
        """
        Update the last_active_at timestamp for a session.

        Args:
            session_id: The session UUID
        """
        async with self.connection() as conn:
            await conn.execute(
                """
                UPDATE sessions
                SET last_active_at = NOW()
                WHERE id = $1
                """,
                session_id
            )

    async def update_title(self, session_id: UUID, title: str) -> None:
        """
        Update the title for a session.

        Args:
            session_id: The session UUID
            title: New session title
        """
        async with self.connection() as conn:
            await conn.execute(
                """
                UPDATE sessions
                SET title = $2, last_active_at = NOW()
                WHERE id = $1
                """,
                session_id,
                title
            )

    async def list_recent(
        self,
        limit: int = 20,
        user_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        List recent sessions ordered by last_active_at.

        Args:
            limit: Maximum number of sessions to return
            user_id: Optional filter by user

        Returns:
            List of session dicts
        """
        async with self.connection() as conn:
            if user_id:
                rows = await conn.fetch(
                    """
                    SELECT id, user_id, title, created_at, last_active_at, metadata
                    FROM sessions
                    WHERE user_id = $1
                    ORDER BY last_active_at DESC
                    LIMIT $2
                    """,
                    user_id,
                    limit
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT id, user_id, title, created_at, last_active_at, metadata
                    FROM sessions
                    ORDER BY last_active_at DESC
                    LIMIT $1
                    """,
                    limit
                )

            return [
                {
                    "id": row["id"],
                    "user_id": row["user_id"],
                    "title": row["title"],
                    "created_at": row["created_at"],
                    "last_active_at": row["last_active_at"],
                    "metadata": dict(row["metadata"]) if row["metadata"] else {}
                }
                for row in rows
            ]

    async def delete(self, session_id: UUID) -> bool:
        """
        Delete a session by ID.

        Note: Related messages are cascade deleted.

        Args:
            session_id: The session UUID

        Returns:
            True if deleted, False if not found
        """
        async with self.connection() as conn:
            result = await conn.execute(
                "DELETE FROM sessions WHERE id = $1",
                session_id
            )

            # asyncpg returns "DELETE N" where N is the number of rows deleted
            return result == "DELETE 1"

    async def get_or_create(
        self,
        session_id: Optional[UUID] = None,
        user_id: Optional[str] = None,
        title: Optional[str] = None
    ) -> UUID:
        """
        Get an existing session or create a new one.

        Args:
            session_id: Optional existing session ID
            user_id: User ID for new session
            title: Title for new session

        Returns:
            Session UUID (existing or newly created)
        """
        if session_id:
            existing = await self.get_by_id(session_id)
            if existing:
                await self.update_last_active(session_id)
                return session_id

        # Create new session
        return await self.create(user_id=user_id, title=title)
