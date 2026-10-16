"""
Document Repository

Phase 14.2.5: Document Repository Implementation
- CRUD operations for documents table
- File hash duplicate checking
- Category-based document listing
"""

from typing import Any, Dict, List, Optional
from uuid import UUID
import json

from .base import BaseRepository


class DocumentRepository(BaseRepository):
    """
    Repository for documents table operations.

    Handles CRUD operations for document metadata storage and RAG support.

    Usage:
        repo = DocumentRepository()

        # Create a new document
        doc_id = await repo.create(
            filename="doc.pdf",
            file_type="pdf",
            file_size=1024,
            file_hash="abc123"
        )

        # Check for duplicates before uploading
        existing = await repo.check_duplicate("abc123")
        if existing:
            print(f"Document already exists: {existing}")

        # Update status after indexing
        await repo.update_status(doc_id, status="indexed", chunk_count=10)

        # List documents by category
        manuals = await repo.list_by_category("manual")
    """

    async def create(
        self,
        filename: str,
        original_filename: Optional[str] = None,
        file_type: Optional[str] = None,
        file_size: Optional[int] = None,
        file_hash: Optional[str] = None,
        title: Optional[str] = None,
        category: Optional[str] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> UUID:
        """
        Create a new document record.

        Args:
            filename: The stored filename (unique identifier)
            original_filename: The original uploaded filename
            file_type: File type/extension (pdf, docx, txt, etc.)
            file_size: File size in bytes
            file_hash: SHA256 hash for duplicate detection
            title: Document title for display
            category: Document category for organization
            tags: List of tags for searching
            metadata: Additional metadata as dict

        Returns:
            The generated UUID of the new document
        """
        async with self.connection() as conn:
            document_id = await conn.fetchval(
                """
                INSERT INTO documents (
                    filename, original_filename, file_type, file_size,
                    file_hash, title, category, tags, metadata
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9::jsonb)
                RETURNING id
                """,
                filename,
                original_filename,
                file_type,
                file_size,
                file_hash,
                title,
                category,
                json.dumps(tags or []),
                json.dumps(metadata or {})
            )
            return document_id

    async def get_by_id(self, document_id: UUID) -> Optional[Dict[str, Any]]:
        """
        Get a document by its ID.

        Args:
            document_id: The document UUID

        Returns:
            Document dict with all fields, or None if not found
        """
        async with self.connection() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, filename, original_filename, file_type, file_size,
                       file_hash, status, chunk_count, title, category, tags,
                       uploaded_at, indexed_at, metadata
                FROM documents
                WHERE id = $1
                """,
                document_id
            )

            if row is None:
                return None

            return dict(row)

    async def update_status(
        self,
        document_id: UUID,
        status: str,
        chunk_count: Optional[int] = None,
        set_indexed_at: bool = False
    ) -> None:
        """
        Update the document processing status.

        Args:
            document_id: The document UUID
            status: New status (pending, processing, indexed, failed, deleted)
            chunk_count: Number of chunks created (for indexed status)
            set_indexed_at: If True, set indexed_at to NOW()
        """
        async with self.connection() as conn:
            if chunk_count is not None and set_indexed_at:
                await conn.execute(
                    """
                    UPDATE documents
                    SET status = $1, chunk_count = $2, indexed_at = NOW()
                    WHERE id = $3
                    """,
                    status,
                    chunk_count,
                    document_id
                )
            elif chunk_count is not None:
                await conn.execute(
                    """
                    UPDATE documents
                    SET status = $1, chunk_count = $2
                    WHERE id = $3
                    """,
                    status,
                    chunk_count,
                    document_id
                )
            elif set_indexed_at:
                await conn.execute(
                    """
                    UPDATE documents
                    SET status = $1, indexed_at = NOW()
                    WHERE id = $2
                    """,
                    status,
                    document_id
                )
            else:
                await conn.execute(
                    """
                    UPDATE documents
                    SET status = $1
                    WHERE id = $2
                    """,
                    status,
                    document_id
                )

    async def list_by_category(
        self,
        category: str,
        status: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        List documents by category.

        Args:
            category: The category to filter by
            status: Optional status filter
            limit: Maximum number of documents to return

        Returns:
            List of document dicts
        """
        async with self.connection() as conn:
            if status:
                rows = await conn.fetch(
                    """
                    SELECT id, filename, original_filename, file_type, file_size,
                           file_hash, status, chunk_count, title, category, tags,
                           uploaded_at, indexed_at, metadata
                    FROM documents
                    WHERE category = $1 AND status = $2
                    ORDER BY uploaded_at DESC
                    LIMIT $3
                    """,
                    category,
                    status,
                    limit
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT id, filename, original_filename, file_type, file_size,
                           file_hash, status, chunk_count, title, category, tags,
                           uploaded_at, indexed_at, metadata
                    FROM documents
                    WHERE category = $1
                    ORDER BY uploaded_at DESC
                    LIMIT $2
                    """,
                    category,
                    limit
                )

            return [dict(row) for row in rows]

    async def check_duplicate(self, file_hash: str) -> Optional[UUID]:
        """
        Check if a document with the same file hash already exists.

        Args:
            file_hash: The SHA256 hash of the file content

        Returns:
            The document ID if a duplicate exists, None otherwise
        """
        async with self.connection() as conn:
            existing_id = await conn.fetchval(
                """
                SELECT id FROM documents
                WHERE file_hash = $1 AND status != 'deleted'
                """,
                file_hash
            )
            return existing_id

    async def list_all(
        self,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        List all documents with optional status filter.

        Args:
            status: Optional status filter
            limit: Maximum number of documents to return
            offset: Number of documents to skip

        Returns:
            List of document dicts
        """
        async with self.connection() as conn:
            if status:
                rows = await conn.fetch(
                    """
                    SELECT id, filename, original_filename, file_type, file_size,
                           file_hash, status, chunk_count, title, category, tags,
                           uploaded_at, indexed_at, metadata
                    FROM documents
                    WHERE status = $1
                    ORDER BY uploaded_at DESC
                    LIMIT $2 OFFSET $3
                    """,
                    status,
                    limit,
                    offset
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT id, filename, original_filename, file_type, file_size,
                           file_hash, status, chunk_count, title, category, tags,
                           uploaded_at, indexed_at, metadata
                    FROM documents
                    ORDER BY uploaded_at DESC
                    LIMIT $1 OFFSET $2
                    """,
                    limit,
                    offset
                )

            return [dict(row) for row in rows]

    async def delete(self, document_id: UUID, soft_delete: bool = True) -> bool:
        """
        Delete a document.

        Args:
            document_id: The document UUID
            soft_delete: If True, set status to 'deleted' instead of removing

        Returns:
            True if a document was deleted, False if not found
        """
        async with self.connection() as conn:
            if soft_delete:
                result = await conn.execute(
                    """
                    UPDATE documents
                    SET status = 'deleted'
                    WHERE id = $1
                    """,
                    document_id
                )
                return result == "UPDATE 1"
            else:
                result = await conn.execute(
                    """
                    DELETE FROM documents
                    WHERE id = $1
                    """,
                    document_id
                )
                return result == "DELETE 1"
