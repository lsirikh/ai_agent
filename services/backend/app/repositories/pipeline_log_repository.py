"""
Pipeline Log Repository

Phase 17: Pipeline Logging System
- CRUD operations for pipeline_logs table
- Real-time log streaming support
"""

from typing import Any, Dict, List, Optional
from uuid import UUID
from datetime import datetime, timedelta
import json

from .base import BaseRepository


class PipelineLogRepository(BaseRepository):
    """
    Repository for pipeline_logs table operations.

    Handles CRUD operations for pipeline execution logs.

    Usage:
        repo = PipelineLogRepository()

        # Create a new log entry
        log_id = await repo.create(
            service="orchestrator",
            stage="wake_word_detected",
            message="Wake word detected",
            level="INFO"
        )

        # Get recent logs
        logs = await repo.list_recent(limit=100)

        # Get logs by service
        logs = await repo.list_by_service("stt", limit=50)

        # Delete old logs
        await repo.delete_older_than(days=7)
    """

    async def create(
        self,
        service: str,
        stage: str,
        message: str,
        level: str = "INFO",
        session_id: Optional[UUID] = None,
        duration_ms: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> UUID:
        """
        Create a new pipeline log entry.

        Args:
            service: Service name (orchestrator, stt, tts, llm, etc.)
            stage: Pipeline stage (wake_word_detected, stt_started, etc.)
            message: Log message
            level: Log level (DEBUG, INFO, WARNING, ERROR)
            session_id: Optional session UUID for correlation
            duration_ms: Optional duration in milliseconds
            metadata: Optional metadata dict

        Returns:
            The generated log UUID
        """
        async with self.connection() as conn:
            log_id = await conn.fetchval(
                """
                INSERT INTO pipeline_logs (
                    service, stage, message, level, session_id, duration_ms, metadata
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb)
                RETURNING id
                """,
                service,
                stage,
                message,
                level,
                session_id,
                duration_ms,
                json.dumps(metadata or {})
            )
            return log_id

    async def get_by_id(self, log_id: UUID) -> Optional[Dict[str, Any]]:
        """
        Get a log entry by its ID.

        Args:
            log_id: The log UUID

        Returns:
            Log dict with all fields, or None if not found
        """
        async with self.connection() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, session_id, service, stage, level, message,
                       duration_ms, metadata, created_at
                FROM pipeline_logs
                WHERE id = $1
                """,
                log_id
            )

            if row is None:
                return None

            return self._row_to_dict(row)

    async def list_recent(
        self,
        limit: int = 100,
        offset: int = 0,
        level: Optional[str] = None,
        service: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        List recent logs ordered by created_at descending.

        Args:
            limit: Maximum number of logs to return
            offset: Number of logs to skip (for pagination)
            level: Optional filter by log level
            service: Optional filter by service

        Returns:
            List of log dicts
        """
        async with self.connection() as conn:
            query = """
                SELECT id, session_id, service, stage, level, message,
                       duration_ms, metadata, created_at
                FROM pipeline_logs
                WHERE 1=1
            """
            params = []
            param_idx = 1

            if level:
                query += f" AND level = ${param_idx}"
                params.append(level)
                param_idx += 1

            if service:
                query += f" AND service = ${param_idx}"
                params.append(service)
                param_idx += 1

            query += f" ORDER BY created_at DESC LIMIT ${param_idx} OFFSET ${param_idx + 1}"
            params.extend([limit, offset])

            rows = await conn.fetch(query, *params)

            return [self._row_to_dict(row) for row in rows]

    async def list_by_session(
        self,
        session_id: UUID,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        List logs for a specific session.

        Args:
            session_id: The session UUID
            limit: Maximum number of logs to return

        Returns:
            List of log dicts ordered by created_at
        """
        async with self.connection() as conn:
            rows = await conn.fetch(
                """
                SELECT id, session_id, service, stage, level, message,
                       duration_ms, metadata, created_at
                FROM pipeline_logs
                WHERE session_id = $1
                ORDER BY created_at ASC
                LIMIT $2
                """,
                session_id,
                limit
            )

            return [self._row_to_dict(row) for row in rows]

    async def list_by_service(
        self,
        service: str,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        List logs for a specific service.

        Args:
            service: Service name
            limit: Maximum number of logs to return

        Returns:
            List of log dicts ordered by created_at descending
        """
        async with self.connection() as conn:
            rows = await conn.fetch(
                """
                SELECT id, session_id, service, stage, level, message,
                       duration_ms, metadata, created_at
                FROM pipeline_logs
                WHERE service = $1
                ORDER BY created_at DESC
                LIMIT $2
                """,
                service,
                limit
            )

            return [self._row_to_dict(row) for row in rows]

    async def list_since(
        self,
        since: datetime,
        limit: int = 1000
    ) -> List[Dict[str, Any]]:
        """
        List logs created after a specific timestamp.
        Used for real-time log streaming.

        Args:
            since: Timestamp to fetch logs after
            limit: Maximum number of logs to return

        Returns:
            List of log dicts ordered by created_at ascending
        """
        async with self.connection() as conn:
            rows = await conn.fetch(
                """
                SELECT id, session_id, service, stage, level, message,
                       duration_ms, metadata, created_at
                FROM pipeline_logs
                WHERE created_at > $1
                ORDER BY created_at ASC
                LIMIT $2
                """,
                since,
                limit
            )

            return [self._row_to_dict(row) for row in rows]

    async def get_stats(
        self,
        hours: int = 24
    ) -> Dict[str, Any]:
        """
        Get log statistics for the specified time period.

        Args:
            hours: Number of hours to look back

        Returns:
            Statistics dict with counts by service and level
        """
        async with self.connection() as conn:
            since = datetime.utcnow() - timedelta(hours=hours)

            # Count by service
            service_counts = await conn.fetch(
                """
                SELECT service, COUNT(*) as count
                FROM pipeline_logs
                WHERE created_at > $1
                GROUP BY service
                ORDER BY count DESC
                """,
                since
            )

            # Count by level
            level_counts = await conn.fetch(
                """
                SELECT level, COUNT(*) as count
                FROM pipeline_logs
                WHERE created_at > $1
                GROUP BY level
                ORDER BY count DESC
                """,
                since
            )

            # Total count
            total = await conn.fetchval(
                """
                SELECT COUNT(*)
                FROM pipeline_logs
                WHERE created_at > $1
                """,
                since
            )

            return {
                "total": total,
                "by_service": {row["service"]: row["count"] for row in service_counts},
                "by_level": {row["level"]: row["count"] for row in level_counts},
                "period_hours": hours
            }

    async def delete_older_than(self, days: int = 7) -> int:
        """
        Delete logs older than the specified number of days.

        Args:
            days: Number of days to keep logs

        Returns:
            Number of deleted rows
        """
        async with self.connection() as conn:
            cutoff = datetime.utcnow() - timedelta(days=days)
            result = await conn.execute(
                "DELETE FROM pipeline_logs WHERE created_at < $1",
                cutoff
            )

            # Extract count from "DELETE N"
            count = int(result.split()[-1]) if result else 0
            return count

    async def delete(self, log_id: UUID) -> bool:
        """
        Delete a specific log entry.

        Args:
            log_id: The log UUID

        Returns:
            True if deleted, False if not found
        """
        async with self.connection() as conn:
            result = await conn.execute(
                "DELETE FROM pipeline_logs WHERE id = $1",
                log_id
            )

            return result == "DELETE 1"

    def _row_to_dict(self, row) -> Dict[str, Any]:
        """Convert a database row to a dict."""
        # Handle metadata - asyncpg returns dict directly from jsonb
        metadata = row["metadata"]
        if metadata is None:
            metadata = {}
        elif isinstance(metadata, str):
            metadata = json.loads(metadata)
        # If already dict, use as-is

        return {
            "id": str(row["id"]),
            "session_id": str(row["session_id"]) if row["session_id"] else None,
            "service": row["service"],
            "stage": row["stage"],
            "level": row["level"],
            "message": row["message"],
            "duration_ms": row["duration_ms"],
            "metadata": metadata,
            "created_at": row["created_at"].isoformat() if row["created_at"] else None
        }
