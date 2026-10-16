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


def _metadata(value: Any) -> Dict[str, Any]:
    """asyncpg 는 JSONB 를 문자열로 돌려준다(코덱 미등록)."""
    if isinstance(value, str):
        value = json.loads(value)
    return dict(value) if value else {}


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
        metadata: Optional[Dict[str, Any]] = None,
        session_type: str = "web",
        source: str = "web"
    ) -> UUID:
        """
        Create a new session.

        Args:
            user_id: Optional user identifier
            title: Optional session title
            metadata: Optional metadata dict
            session_type: 'web' | 'voice' | 'unified'
            source: 'web' | 'orchestrator' | 'api'

        Returns:
            The generated session UUID
        """
        async with self.connection() as conn:
            session_id = await conn.fetchval(
                """
                INSERT INTO sessions (user_id, title, metadata, session_type, source)
                VALUES ($1, $2, $3::jsonb, $4, $5)
                RETURNING id
                """,
                user_id,
                title,
                json.dumps(metadata or {}),
                session_type,
                source
            )
            return session_id

    async def get_active(self) -> Optional[UUID]:
        """활성 세션 ID (settings 의 'active_session'). 지워진 세션이면 None."""
        async with self.connection() as conn:
            return await conn.fetchval(
                """
                SELECT s.id
                FROM settings st
                JOIN sessions s ON s.id::text = st.value->>'session_id'
                WHERE st.key = 'active_session'
                """
            )

    async def set_active(self, session_id: UUID) -> None:
        """활성 세션을 바꾼다(재시작해도 유지되도록 DB 에 둔다)."""
        async with self.connection() as conn:
            await conn.execute(
                """
                INSERT INTO settings (key, value, category, description, updated_at)
                VALUES ('active_session', $1::jsonb, 'system',
                        'Active unified conversation session', NOW())
                ON CONFLICT (key) DO UPDATE
                    SET value = EXCLUDED.value, updated_at = NOW()
                """,
                json.dumps({"session_id": str(session_id)})
            )

    async def get_summary(self, session_id: UUID) -> Optional[Dict[str, Any]]:
        """세션의 최신 롤링 요약."""
        async with self.connection() as conn:
            row = await conn.fetchrow(
                """
                SELECT summary, covered_until_message_id, token_count, created_at
                FROM session_summaries
                WHERE session_id = $1
                ORDER BY created_at DESC
                LIMIT 1
                """,
                session_id
            )
            return dict(row) if row else None

    async def add_summary(
        self,
        session_id: UUID,
        summary: str,
        covered_until_message_id: UUID,
        token_count: int
    ) -> None:
        """롤링 요약 추가(원문 메시지는 지우지 않는다)."""
        async with self.connection() as conn:
            await conn.execute(
                """
                INSERT INTO session_summaries
                    (session_id, summary, covered_until_message_id, token_count)
                VALUES ($1, $2, $3, $4)
                """,
                session_id,
                summary,
                covered_until_message_id,
                token_count
            )

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
                "metadata": _metadata(row["metadata"])
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
                    "metadata": _metadata(row["metadata"])
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
