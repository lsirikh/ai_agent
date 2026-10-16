"""
Test Knowledge Integration

Phase 14.3.4: Knowledge Router Integration Tests
Phase 33: Test 수정 - get_rag_client로 패치 대상 변경
- Upload creates document in DB
- List documents loads from DB
- Delete updates status to 'deleted'
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport
import uuid
import io


class TestKnowledgeUploadCreatesDocument:
    """Tests for upload creating document records."""

    @pytest.mark.asyncio
    async def test_knowledge_upload_creates_document(self):
        """
        Test that POST /api/knowledge/upload creates a document record.

        Requirements:
        - Upload a file
        - RAG service receives the document
        - Document ID is returned
        """
        from services.backend.app.main import app
        from services.backend.app.routes import knowledge as knowledge_module

        # Create mock RAG client
        mock_client = MagicMock()
        doc_id = f"doc-{uuid.uuid4().hex[:8]}"
        mock_client.add_document = AsyncMock(return_value={"doc_id": doc_id})

        with patch.object(knowledge_module, "get_rag_client", return_value=mock_client):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                # Create a test file
                file_content = b"This is test document content for RAG indexing."

                response = await client.post(
                    "/api/knowledge/upload",
                    files={"file": ("test_document.txt", io.BytesIO(file_content), "text/plain")},
                    data={"title": "Test Document", "category": "manual"}
                )

                assert response.status_code == 200
                data = response.json()
                assert data["doc_id"] == doc_id
                assert data["filename"] == "test_document.txt"
                assert "message" in data

                # Verify RAG client was called
                mock_client.add_document.assert_called_once()
                call_kwargs = mock_client.add_document.call_args
                assert "content" in call_kwargs.kwargs or len(call_kwargs.args) > 0


class TestKnowledgeListFromDb:
    """Tests for listing documents from storage."""

    @pytest.mark.asyncio
    async def test_knowledge_list_from_db(self):
        """
        Test that GET /api/knowledge/documents loads from storage.

        Requirements:
        - Call GET /api/knowledge/documents
        - Verify response contains documents from RAG client
        """
        from services.backend.app.main import app
        from services.backend.app.routes import knowledge as knowledge_module

        # Create mock RAG client with documents
        mock_client = MagicMock()
        mock_client.list_documents = AsyncMock(return_value=[
            {
                "doc_id": "doc-001",
                "metadata": {"filename": "manual.pdf", "category": "manual"}
            },
            {
                "doc_id": "doc-002",
                "metadata": {"filename": "guide.txt", "category": "guide"}
            }
        ])

        with patch.object(knowledge_module, "get_rag_client", return_value=mock_client):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/api/knowledge/documents")

                assert response.status_code == 200
                data = response.json()
                assert "documents" in data
                assert "total" in data
                assert data["total"] == 2
                assert len(data["documents"]) == 2

                # Verify document info
                doc_ids = [d["doc_id"] for d in data["documents"]]
                assert "doc-001" in doc_ids
                assert "doc-002" in doc_ids

                # Verify RAG client was called
                mock_client.list_documents.assert_called_once()


class TestKnowledgeDeleteUpdatesStatus:
    """Tests for delete updating document status."""

    @pytest.mark.asyncio
    async def test_knowledge_delete_updates_status(self):
        """
        Test that DELETE /api/knowledge/documents/{doc_id} removes document.

        Requirements:
        - Call DELETE with doc_id
        - Verify RAG client delete is called
        - Document is marked as deleted
        """
        from services.backend.app.main import app
        from services.backend.app.routes import knowledge as knowledge_module

        # Create mock RAG client
        mock_client = MagicMock()
        mock_client.delete_document = AsyncMock(return_value={"deleted": True})

        doc_id = "doc-to-delete"

        with patch.object(knowledge_module, "get_rag_client", return_value=mock_client):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.delete(f"/api/knowledge/documents/{doc_id}")

                assert response.status_code == 200
                data = response.json()
                assert data["doc_id"] == doc_id
                assert data["deleted"] is True

                # Verify RAG client delete was called
                mock_client.delete_document.assert_called_once_with(doc_id)

    @pytest.mark.asyncio
    async def test_knowledge_delete_not_found(self):
        """
        Test that DELETE returns 404 for non-existent document.
        """
        from services.backend.app.main import app
        from services.backend.app.routes import knowledge as knowledge_module

        # Create mock RAG client that raises error
        mock_client = MagicMock()
        mock_client.delete_document = AsyncMock(side_effect=Exception("Document not found"))

        doc_id = "non-existent-doc"

        with patch.object(knowledge_module, "get_rag_client", return_value=mock_client):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.delete(f"/api/knowledge/documents/{doc_id}")

                assert response.status_code == 404


class TestKnowledgeSearch:
    """Tests for knowledge base search."""

    @pytest.mark.asyncio
    async def test_knowledge_search(self):
        """
        Test that POST /api/knowledge/search performs RAG search.
        """
        from services.backend.app.main import app
        from services.backend.app.routes import knowledge as knowledge_module

        # Create mock RAG client
        mock_client = MagicMock()
        mock_client.search = AsyncMock(return_value=[
            {
                "content": "Relevant document content",
                "score": 0.95,
                "doc_id": "doc-123",
                "metadata": {"filename": "manual.pdf"}
            }
        ])

        with patch.object(knowledge_module, "get_rag_client", return_value=mock_client):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/api/knowledge/search",
                    json={"query": "How to configure the system?", "top_k": 3}
                )

                assert response.status_code == 200
                data = response.json()
                assert "results" in data
                assert len(data["results"]) == 1
                assert data["results"][0]["doc_id"] == "doc-123"
                assert data["results"][0]["score"] == 0.95

                # Verify RAG search was called
                mock_client.search.assert_called_once()
