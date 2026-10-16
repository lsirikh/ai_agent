"""
Database Connection Manager

Phase 14.1: Database Infrastructure
- Singleton pattern for connection pool management
- asyncpg-based PostgreSQL connection pooling
"""

import asyncio
import os
from typing import Any, Awaitable, Callable, Optional

try:
    import asyncpg
except ImportError:
    asyncpg = None


class DatabaseManager:
    """
    Centralized database connection pool manager.

    Singleton pattern ensures single pool across application.

    Usage:
        manager = DatabaseManager()
        await manager.connect()

        async with manager.acquire() as conn:
            result = await conn.fetch("SELECT * FROM settings")

        await manager.disconnect()
    """

    _instance: Optional["DatabaseManager"] = None
    _pool: Optional["asyncpg.Pool"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @property
    def database_url(self) -> str:
        """Get database URL from environment."""
        return os.getenv(
            "DATABASE_URL",
            "postgresql://edgevoice:edgevoice@localhost:5432/edgevoice"
        )

    @property
    def pool(self) -> Optional["asyncpg.Pool"]:
        """Get the connection pool."""
        return self._pool

    @property
    def is_connected(self) -> bool:
        """Check if database is connected."""
        return self._pool is not None

    async def connect(
        self,
        min_size: int = 5,
        max_size: int = 20,
        command_timeout: float = 60.0
    ) -> None:
        """
        Initialize the connection pool.

        Args:
            min_size: Minimum number of connections in the pool
            max_size: Maximum number of connections in the pool
            command_timeout: Timeout for database commands
        """
        if asyncpg is None:
            raise ImportError("asyncpg is not installed. Run: pip install asyncpg>=0.29.0")

        if self._pool is not None:
            return  # Already connected

        # Parse DATABASE_URL for asyncpg
        url = self.database_url

        self._pool = await asyncpg.create_pool(
            url,
            min_size=min_size,
            max_size=max_size,
            command_timeout=command_timeout
        )

    async def disconnect(self) -> None:
        """Close the connection pool."""
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    async def acquire(self):
        """
        Acquire a connection from the pool.

        Returns:
            asyncpg.Connection context manager

        Usage:
            async with manager.acquire() as conn:
                await conn.fetch("SELECT 1")
        """
        if self._pool is None:
            raise RuntimeError("Database not connected. Call connect() first.")
        return self._pool.acquire()

    async def health_check(self) -> bool:
        """
        Check if database connection is healthy.

        Returns:
            True if connected and can execute queries, False otherwise
        """
        if self._pool is None:
            return False

        try:
            async with self._pool.acquire() as conn:
                result = await conn.fetchval("SELECT 1")
                return result == 1
        except Exception:
            return False


async def connect_with_retry(
    db_manager: Any,
    attempts: int = 30,
    delay: float = 2.0,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> None:
    """
    DB 가 준비될 때까지 연결을 재시도한다.

    Docker 재시작 정책으로 되살아날 때는 depends_on(healthy) 이 지켜지지 않아
    Postgres 가 아직 "starting up" 일 수 있다.
    마지막 시도도 실패하면 예외를 그대로 올린다.
    """
    for attempt in range(1, attempts + 1):
        try:
            await db_manager.connect()
            return
        except Exception:
            if attempt == attempts:
                raise
            await sleep(delay)


# Global instance accessor
_db_manager: Optional[DatabaseManager] = None


def get_db_manager() -> DatabaseManager:
    """
    Get the global DatabaseManager instance.

    Returns:
        DatabaseManager singleton instance
    """
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager()
    return _db_manager


def reset_db_manager() -> None:
    """
    Reset the global DatabaseManager instance.
    (For testing purposes)
    """
    global _db_manager
    _db_manager = None
    DatabaseManager._instance = None
    DatabaseManager._pool = None
