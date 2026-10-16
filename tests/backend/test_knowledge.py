"""
Backend API Knowledge Base Tests

Phase 5.3: Backend API - Knowledge Base (RAG) 테스트
Phase 33: Test 수정 - get_rag_client로 패치 대상 변경
"""
import io
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


class TestDocumentUpload:
    """문서 업로드 테스트"""

    def test_upload_document_txt(self):
        """TXT 문서를 업로드할 수 있어야 한다"""
        from services.backend.app.main import app

        client = TestClient(app)

        # TXT 파일 생성
        content = "이것은 테스트 문서입니다. 여러 문장이 포함되어 있습니다."
        files = {"file": ("test.txt", io.BytesIO(content.encode("utf-8")), "text/plain")}

        with patch("services.backend.app.routes.knowledge.get_rag_client") as mock_rag:
            mock_client = MagicMock()
            mock_client.add_document = AsyncMock(return_value={"doc_id": "doc-001"})
            mock_rag.return_value = mock_client

            response = client.post("/api/knowledge/upload", files=files)

        assert response.status_code == 200
        data = response.json()
        assert "doc_id" in data
        assert data["filename"] == "test.txt"

    def test_upload_document_pdf(self):
        """PDF 문서를 업로드할 수 있어야 한다"""
        from services.backend.app.main import app

        client = TestClient(app)

        # 간단한 PDF 바이너리 (실제로는 PyPDF2 등으로 파싱)
        pdf_content = b"%PDF-1.4 fake pdf content"
        files = {"file": ("test.pdf", io.BytesIO(pdf_content), "application/pdf")}

        with patch("services.backend.app.routes.knowledge.get_rag_client") as mock_rag:
            mock_client = MagicMock()
            mock_client.add_document = AsyncMock(return_value={"doc_id": "doc-002"})
            mock_rag.return_value = mock_client

            with patch("services.backend.app.routes.knowledge.extract_text_from_pdf") as mock_extract:
                mock_extract.return_value = "PDF에서 추출된 텍스트입니다."

                response = client.post("/api/knowledge/upload", files=files)

        assert response.status_code == 200
        data = response.json()
        assert "doc_id" in data
        assert data["filename"] == "test.pdf"

    def test_upload_document_docx(self):
        """DOCX 문서를 업로드할 수 있어야 한다"""
        from services.backend.app.main import app

        client = TestClient(app)

        # 간단한 DOCX 바이너리
        docx_content = b"PK\x03\x04 fake docx content"
        files = {"file": ("test.docx", io.BytesIO(docx_content), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}

        with patch("services.backend.app.routes.knowledge.get_rag_client") as mock_rag:
            mock_client = MagicMock()
            mock_client.add_document = AsyncMock(return_value={"doc_id": "doc-003"})
            mock_rag.return_value = mock_client

            with patch("services.backend.app.routes.knowledge.extract_text_from_docx") as mock_extract:
                mock_extract.return_value = "DOCX에서 추출된 텍스트입니다."

                response = client.post("/api/knowledge/upload", files=files)

        assert response.status_code == 200
        data = response.json()
        assert "doc_id" in data
        assert data["filename"] == "test.docx"

    def test_upload_unsupported_format(self):
        """지원하지 않는 형식은 거부해야 한다"""
        from services.backend.app.main import app

        client = TestClient(app)

        files = {"file": ("test.exe", io.BytesIO(b"binary content"), "application/octet-stream")}

        response = client.post("/api/knowledge/upload", files=files)

        assert response.status_code == 400
        assert "지원하지 않는" in response.json()["detail"] or "Unsupported" in response.json()["detail"]

    def test_upload_with_metadata(self):
        """메타데이터와 함께 문서를 업로드할 수 있어야 한다"""
        from services.backend.app.main import app

        client = TestClient(app)

        content = "테스트 문서"
        files = {"file": ("test.txt", io.BytesIO(content.encode("utf-8")), "text/plain")}
        data = {"title": "테스트 제목", "category": "manual"}

        with patch("services.backend.app.routes.knowledge.get_rag_client") as mock_rag:
            mock_client = MagicMock()
            mock_client.add_document = AsyncMock(return_value={"doc_id": "doc-004"})
            mock_rag.return_value = mock_client

            response = client.post("/api/knowledge/upload", files=files, data=data)

        assert response.status_code == 200
        # RAG 클라이언트에 메타데이터가 전달되었는지 확인
        mock_client.add_document.assert_called_once()
        call_kwargs = mock_client.add_document.call_args
        assert "metadata" in call_kwargs.kwargs or len(call_kwargs.args) > 1


class TestDocumentList:
    """문서 목록 조회 테스트"""

    def test_list_documents(self):
        """문서 목록을 조회할 수 있어야 한다"""
        from services.backend.app.main import app

        client = TestClient(app)

        with patch("services.backend.app.routes.knowledge.get_rag_client") as mock_rag:
            mock_client = MagicMock()
            mock_client.list_documents = AsyncMock(return_value=[
                {"doc_id": "doc-001", "metadata": {"filename": "test1.txt", "title": "문서1"}},
                {"doc_id": "doc-002", "metadata": {"filename": "test2.pdf", "title": "문서2"}}
            ])
            mock_rag.return_value = mock_client

            response = client.get("/api/knowledge/documents")

        assert response.status_code == 200
        data = response.json()
        assert "documents" in data
        assert len(data["documents"]) == 2

    def test_list_documents_empty(self):
        """문서가 없을 때 빈 목록을 반환해야 한다"""
        from services.backend.app.main import app

        client = TestClient(app)

        with patch("services.backend.app.routes.knowledge.get_rag_client") as mock_rag:
            mock_client = MagicMock()
            mock_client.list_documents = AsyncMock(return_value=[])
            mock_rag.return_value = mock_client

            response = client.get("/api/knowledge/documents")

        assert response.status_code == 200
        data = response.json()
        assert data["documents"] == []

    def test_list_documents_with_pagination(self):
        """페이지네이션을 지원해야 한다"""
        from services.backend.app.main import app

        client = TestClient(app)

        with patch("services.backend.app.routes.knowledge.get_rag_client") as mock_rag:
            mock_client = MagicMock()
            mock_client.list_documents = AsyncMock(return_value=[
                {"doc_id": f"doc-{i}", "metadata": {"filename": f"test{i}.txt"}}
                for i in range(5)
            ])
            mock_rag.return_value = mock_client

            response = client.get("/api/knowledge/documents?limit=5&offset=0")

        assert response.status_code == 200
        data = response.json()
        assert len(data["documents"]) <= 5


class TestDocumentDelete:
    """문서 삭제 테스트"""

    def test_delete_document(self):
        """문서를 삭제할 수 있어야 한다"""
        from services.backend.app.main import app

        client = TestClient(app)

        with patch("services.backend.app.routes.knowledge.get_rag_client") as mock_rag:
            mock_client = MagicMock()
            mock_client.delete_document = AsyncMock(return_value={"deleted": True})
            mock_rag.return_value = mock_client

            response = client.delete("/api/knowledge/documents/doc-001")

        assert response.status_code == 200
        data = response.json()
        assert data["deleted"] is True
        assert data["doc_id"] == "doc-001"

    def test_delete_nonexistent_document(self):
        """존재하지 않는 문서 삭제 시 404 반환"""
        from services.backend.app.main import app

        client = TestClient(app)

        with patch("services.backend.app.routes.knowledge.get_rag_client") as mock_rag:
            mock_client = MagicMock()
            mock_client.delete_document = AsyncMock(side_effect=Exception("Document not found"))
            mock_rag.return_value = mock_client

            response = client.delete("/api/knowledge/documents/nonexistent")

        assert response.status_code == 404


class TestKnowledgeSearch:
    """지식 검색 테스트"""

    def test_search_knowledge(self):
        """지식 베이스를 검색할 수 있어야 한다"""
        from services.backend.app.main import app

        client = TestClient(app)

        with patch("services.backend.app.routes.knowledge.get_rag_client") as mock_rag:
            mock_client = MagicMock()
            mock_client.search = AsyncMock(return_value=[
                {"content": "관련 내용 1", "score": 0.95, "doc_id": "doc-001", "metadata": {}},
                {"content": "관련 내용 2", "score": 0.85, "doc_id": "doc-002", "metadata": {}}
            ])
            mock_rag.return_value = mock_client

            response = client.post("/api/knowledge/search", json={"query": "테스트 검색"})

        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        assert len(data["results"]) == 2
        assert data["results"][0]["score"] >= data["results"][1]["score"]

    def test_search_with_top_k(self):
        """top_k 파라미터로 결과 수를 제한할 수 있어야 한다"""
        from services.backend.app.main import app

        client = TestClient(app)

        with patch("services.backend.app.routes.knowledge.get_rag_client") as mock_rag:
            mock_client = MagicMock()
            mock_client.search = AsyncMock(return_value=[
                {"content": "결과", "score": 0.9, "doc_id": "doc-001", "metadata": {}}
            ])
            mock_rag.return_value = mock_client

            response = client.post("/api/knowledge/search", json={"query": "검색", "top_k": 1})

        assert response.status_code == 200
        mock_client.search.assert_called_once()
        call_args = mock_client.search.call_args
        assert call_args.kwargs.get("top_k") == 1 or (len(call_args.args) > 1 and call_args.args[1] == 1)

    def test_search_with_filter(self):
        """메타데이터 필터로 검색 범위를 제한할 수 있어야 한다"""
        from services.backend.app.main import app

        client = TestClient(app)

        with patch("services.backend.app.routes.knowledge.get_rag_client") as mock_rag:
            mock_client = MagicMock()
            mock_client.search = AsyncMock(return_value=[])
            mock_rag.return_value = mock_client

            response = client.post("/api/knowledge/search", json={
                "query": "검색",
                "filter": {"category": "manual"}
            })

        assert response.status_code == 200
        mock_client.search.assert_called_once()

    def test_search_empty_query(self):
        """빈 쿼리는 거부해야 한다"""
        from services.backend.app.main import app

        client = TestClient(app)

        response = client.post("/api/knowledge/search", json={"query": ""})

        assert response.status_code == 400

    def test_search_returns_formatted_context(self):
        """포맷된 컨텍스트를 반환할 수 있어야 한다"""
        from services.backend.app.main import app

        client = TestClient(app)

        with patch("services.backend.app.routes.knowledge.get_rag_client") as mock_rag:
            mock_client = MagicMock()
            mock_client.search = AsyncMock(return_value=[
                {"content": "내용 1", "score": 0.9, "doc_id": "doc-001", "metadata": {}},
                {"content": "내용 2", "score": 0.8, "doc_id": "doc-002", "metadata": {}}
            ])
            mock_client.format_context = AsyncMock(return_value="내용 1\n---\n내용 2")
            mock_rag.return_value = mock_client

            response = client.post("/api/knowledge/search", json={
                "query": "검색",
                "format_context": True
            })

        assert response.status_code == 200
        data = response.json()
        assert "formatted_context" in data
