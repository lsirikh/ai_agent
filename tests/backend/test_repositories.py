"""
Test Base Repository

Phase 14.2.1: Base Repository Tests
- Connection context manager
- Transaction context manager
- Transaction rollback on exception
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestBaseRepositoryConnectionContext:
    """Tests for BaseRepository connection context manager."""

    @pytest.mark.asyncio
    async def test_base_repository_connection_context(self):
        """
        Test that BaseRepository provides a connection context manager.

        The context manager should:
        1. Acquire a connection from the pool
        2. Yield the connection for use
        3. Release the connection back to the pool
        """
        from services.backend.app.repositories.base import BaseRepository
        from services.backend.app.database import get_db_manager

        # Mock the database manager
        mock_conn = AsyncMock()
        mock_pool = MagicMock()
        mock_pool.acquire = MagicMock(return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=mock_conn),
            __aexit__=AsyncMock(return_value=None)
        ))

        with patch.object(get_db_manager(), '_pool', mock_pool):
            repo = BaseRepository()

            async with repo.connection() as conn:
                # Connection should be yielded
                assert conn is mock_conn
                # Use the connection
                await conn.fetch("SELECT 1")

            # Verify connection was acquired
            mock_pool.acquire.assert_called_once()


class TestBaseRepositoryTransactionContext:
    """Tests for BaseRepository transaction context manager."""

    @pytest.mark.asyncio
    async def test_base_repository_transaction_context(self):
        """
        Test that BaseRepository provides a transaction context manager.

        The transaction context manager should:
        1. Acquire a connection
        2. Start a transaction
        3. Yield the connection
        4. Commit the transaction on success
        """
        from services.backend.app.repositories.base import BaseRepository
        from services.backend.app.database import get_db_manager

        # Mock connection with transaction support
        mock_conn = AsyncMock()
        mock_transaction = AsyncMock()
        mock_conn.transaction = MagicMock(return_value=mock_transaction)
        mock_transaction.__aenter__ = AsyncMock(return_value=mock_transaction)
        mock_transaction.__aexit__ = AsyncMock(return_value=None)

        mock_pool = MagicMock()
        mock_acquire_ctx = AsyncMock()
        mock_acquire_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_acquire_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_pool.acquire = MagicMock(return_value=mock_acquire_ctx)

        with patch.object(get_db_manager(), '_pool', mock_pool):
            repo = BaseRepository()

            async with repo.transaction() as conn:
                # Connection should be yielded
                assert conn is mock_conn
                # Perform operations
                await conn.execute("INSERT INTO test VALUES (1)")

            # Verify transaction was used
            mock_conn.transaction.assert_called_once()


class TestBaseRepositoryTransactionRollback:
    """Tests for BaseRepository transaction rollback on exception."""

    @pytest.mark.asyncio
    async def test_base_repository_transaction_rollback(self):
        """
        Test that transaction is rolled back when an exception occurs.

        When an exception is raised inside the transaction context:
        1. The transaction should NOT be committed
        2. asyncpg automatically rolls back on exception exit
        3. The exception should propagate
        """
        from services.backend.app.repositories.base import BaseRepository
        from services.backend.app.database import get_db_manager

        # Mock connection with transaction support
        mock_conn = AsyncMock()
        mock_transaction = AsyncMock()
        mock_conn.transaction = MagicMock(return_value=mock_transaction)
        mock_transaction.__aenter__ = AsyncMock(return_value=mock_transaction)
        # __aexit__ receives exception info when exception occurs
        mock_transaction.__aexit__ = AsyncMock(return_value=False)  # False = re-raise exception

        mock_pool = MagicMock()
        mock_acquire_ctx = AsyncMock()
        mock_acquire_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_acquire_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_pool.acquire = MagicMock(return_value=mock_acquire_ctx)

        with patch.object(get_db_manager(), '_pool', mock_pool):
            repo = BaseRepository()

            # Exception should propagate
            with pytest.raises(ValueError, match="Test error"):
                async with repo.transaction() as conn:
                    await conn.execute("INSERT INTO test VALUES (1)")
                    raise ValueError("Test error")

            # Transaction __aexit__ should have been called with exception info
            assert mock_transaction.__aexit__.called
            call_args = mock_transaction.__aexit__.call_args
            # First positional arg is exception type
            assert call_args[0][0] is ValueError
