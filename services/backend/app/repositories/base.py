"""
Base Repository

Phase 14.2.1: Base Repository Implementation
- Provides connection and transaction context managers
- Abstract base class for all repositories
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

try:
    import asyncpg
except ImportError:
    asyncpg = None

from ..database import get_db_manager


class BaseRepository:
    """
    Abstract base class for all repositories.

    Provides:
    - connection(): Context manager for acquiring a database connection
    - transaction(): Context manager for transaction handling with auto-rollback

    Usage:
        class UserRepository(BaseRepository):
            async def get_user(self, user_id: int):
                async with self.connection() as conn:
                    return await conn.fetchrow(
                        "SELECT * FROM users WHERE id = $1", user_id
                    )

            async def create_user(self, name: str):
                async with self.transaction() as conn:
                    return await conn.execute(
                        "INSERT INTO users (name) VALUES ($1)", name
                    )
    """

    def __init__(self):
        """Initialize the repository with the database manager."""
        self._db_manager = get_db_manager()

    @asynccontextmanager
    async def connection(self) -> AsyncGenerator["asyncpg.Connection", None]:
        """
        Acquire a connection from the pool.

        Yields:
            asyncpg.Connection: Database connection

        Usage:
            async with self.connection() as conn:
                result = await conn.fetch("SELECT * FROM users")
        """
        if self._db_manager.pool is None:
            raise RuntimeError("Database not connected. Call connect() first.")

        async with self._db_manager.pool.acquire() as conn:
            yield conn

    @asynccontextmanager
    async def transaction(self) -> AsyncGenerator["asyncpg.Connection", None]:
        """
        Acquire a connection and start a transaction.

        The transaction is automatically committed on success,
        or rolled back if an exception is raised.

        Yields:
            asyncpg.Connection: Database connection within a transaction

        Usage:
            async with self.transaction() as conn:
                await conn.execute("INSERT INTO users (name) VALUES ($1)", "John")
                await conn.execute("INSERT INTO audit_log (action) VALUES ($1)", "user_created")
                # Both statements committed together

            # If exception raised, both statements rolled back
        """
        if self._db_manager.pool is None:
            raise RuntimeError("Database not connected. Call connect() first.")

        async with self._db_manager.pool.acquire() as conn:
            async with conn.transaction():
                yield conn
