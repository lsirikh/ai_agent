"""
Test Document Repository

Phase 14.2.5: Document Repository Tests
- CRUD operations for documents table
- File hash duplicate checking
- Category-based document listing
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone
import uuid


class TestDocumentRepoCreate:
    """Tests for DocumentRepository.create() method."""

    @pytest.mark.asyncio
    async def test_document_repo_create(self):
        """
        Test that create() creates a new document and returns its ID.

        Requirements:
        - INSERT into documents table
        - Return the generated UUID
        - Support filename, file_type, file_size, file_hash, category
        """
        from services.backend.app.repositories.document_repository import DocumentRepository

        document_id = uuid.uuid4()

        mock_conn = AsyncMock()
        mock_conn.fetchval = AsyncMock(return_value=document_id)

        mock_pool = MagicMock()
        mock_acquire_ctx = AsyncMock()
        mock_acquire_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_acquire_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_pool.acquire = MagicMock(return_value=mock_acquire_ctx)

        from services.backend.app.database import get_db_manager
        with patch.object(get_db_manager(), '_pool', mock_pool):
            repo = DocumentRepository()
            result = await repo.create(
                filename="document.pdf",
                original_filename="My Document.pdf",
                file_type="pdf",
                file_size=1024000,
                file_hash="abc123def456",
                category="manual"
            )

            assert result == document_id
            mock_conn.fetchval.assert_called_once()
            call_args = mock_conn.fetchval.call_args
            sql = call_args[0][0].upper()
            assert "INSERT INTO DOCUMENTS" in sql
            assert "RETURNING ID" in sql


class TestDocumentRepoGetById:
    """Tests for DocumentRepository.get_by_id() method."""

    @pytest.mark.asyncio
    async def test_document_repo_get_by_id(self):
        """
        Test that get_by_id() returns document data by UUID.

        Requirements:
        - Query documents table by id
        - Return document dict with all fields
        """
        from services.backend.app.repositories.document_repository import DocumentRepository

        document_id = uuid.uuid4()
        now = datetime.now(timezone.utc)
        mock_row = {
            "id": document_id,
            "filename": "document.pdf",
            "original_filename": "My Document.pdf",
            "file_type": "pdf",
            "file_size": 1024000,
            "file_hash": "abc123def456",
            "status": "indexed",
            "chunk_count": 10,
            "title": "Product Manual",
            "category": "manual",
            "tags": ["product", "guide"],
            "uploaded_at": now,
            "indexed_at": now,
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
            repo = DocumentRepository()
            result = await repo.get_by_id(document_id)

            assert result["id"] == document_id
            assert result["filename"] == "document.pdf"
            assert result["status"] == "indexed"
            assert result["chunk_count"] == 10
            mock_conn.fetchrow.assert_called_once()


class TestDocumentRepoUpdateStatus:
    """Tests for DocumentRepository.update_status() method."""

    @pytest.mark.asyncio
    async def test_document_repo_update_status(self):
        """
        Test that update_status() updates the document status.

        Requirements:
        - UPDATE documents SET status = $1
        - Support optional chunk_count and indexed_at
        """
        from services.backend.app.repositories.document_repository import DocumentRepository

        document_id = uuid.uuid4()
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock(return_value="UPDATE 1")

        mock_pool = MagicMock()
        mock_acquire_ctx = AsyncMock()
        mock_acquire_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_acquire_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_pool.acquire = MagicMock(return_value=mock_acquire_ctx)

        from services.backend.app.database import get_db_manager
        with patch.object(get_db_manager(), '_pool', mock_pool):
            repo = DocumentRepository()
            await repo.update_status(document_id, status="indexed", chunk_count=15)

            mock_conn.execute.assert_called_once()
            call_args = mock_conn.execute.call_args
            sql = call_args[0][0].upper()
            assert "UPDATE DOCUMENTS" in sql
            assert "STATUS" in sql


class TestDocumentRepoListByCategory:
    """Tests for DocumentRepository.list_by_category() method."""

    @pytest.mark.asyncio
    async def test_document_repo_list_by_category(self):
        """
        Test that list_by_category() returns documents filtered by category.

        Requirements:
        - Query documents by category
        - Order by uploaded_at DESC
        - Return list of document dicts
        """
        from services.backend.app.repositories.document_repository import DocumentRepository

        now = datetime.now(timezone.utc)
        mock_rows = [
            {"id": uuid.uuid4(), "filename": "doc1.pdf", "category": "manual", "status": "indexed", "uploaded_at": now},
            {"id": uuid.uuid4(), "filename": "doc2.pdf", "category": "manual", "status": "indexed", "uploaded_at": now},
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
            repo = DocumentRepository()
            result = await repo.list_by_category("manual")

            assert len(result) == 2
            assert result[0]["category"] == "manual"
            mock_conn.fetch.assert_called_once()
            call_args = mock_conn.fetch.call_args
            sql = call_args[0][0].upper()
            assert "CATEGORY" in sql
            assert "ORDER BY UPLOADED_AT DESC" in sql


class TestDocumentRepoCheckDuplicate:
    """Tests for DocumentRepository.check_duplicate() method."""

    @pytest.mark.asyncio
    async def test_document_repo_check_duplicate(self):
        """
        Test that check_duplicate() finds documents by file_hash.

        Requirements:
        - Query documents by file_hash
        - Return document ID if duplicate exists, None otherwise
        """
        from services.backend.app.repositories.document_repository import DocumentRepository

        existing_id = uuid.uuid4()

        mock_conn = AsyncMock()
        mock_conn.fetchval = AsyncMock(return_value=existing_id)

        mock_pool = MagicMock()
        mock_acquire_ctx = AsyncMock()
        mock_acquire_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_acquire_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_pool.acquire = MagicMock(return_value=mock_acquire_ctx)

        from services.backend.app.database import get_db_manager
        with patch.object(get_db_manager(), '_pool', mock_pool):
            repo = DocumentRepository()
            result = await repo.check_duplicate("abc123def456")

            assert result == existing_id
            mock_conn.fetchval.assert_called_once()
            call_args = mock_conn.fetchval.call_args
            sql = call_args[0][0].upper()
            assert "FILE_HASH" in sql

    @pytest.mark.asyncio
    async def test_document_repo_check_duplicate_not_found(self):
        """
        Test that check_duplicate() returns None when no duplicate exists.
        """
        from services.backend.app.repositories.document_repository import DocumentRepository

        mock_conn = AsyncMock()
        mock_conn.fetchval = AsyncMock(return_value=None)

        mock_pool = MagicMock()
        mock_acquire_ctx = AsyncMock()
        mock_acquire_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_acquire_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_pool.acquire = MagicMock(return_value=mock_acquire_ctx)

        from services.backend.app.database import get_db_manager
        with patch.object(get_db_manager(), '_pool', mock_pool):
            repo = DocumentRepository()
            result = await repo.check_duplicate("nonexistent_hash")

            assert result is None
