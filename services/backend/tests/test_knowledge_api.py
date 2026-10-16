"""
Test cases for Knowledge API - Phase 27 Bug Fixes

Issue #1: Module import error - RAG service should be called via HTTP, not direct import
Issue #2: datetime comparison error - timezone-aware vs naive
"""
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch


class TestRAGServiceClient:
    """RAG 서비스 HTTP 클라이언트 테스트"""

    @pytest.mark.asyncio
    async def test_get_documents_calls_rag_api(self):
        """RAG 서비스의 /documents API를 HTTP로 호출해야 함"""
        from app.services.rag_client import RAGServiceClient

        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"doc_id": "doc1", "metadata": {"filename": "test.txt"}}
        ]

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.get.return_value = mock_response
            mock_client_class.return_value = mock_client

            client = RAGServiceClient()
            result = await client.list_documents()

            mock_client.get.assert_called_once()
            call_args = mock_client.get.call_args
            assert "rag" in call_args[0][0] or "11006" in call_args[0][0]
            assert result == [{"doc_id": "doc1", "metadata": {"filename": "test.txt"}}]

    @pytest.mark.asyncio
    async def test_add_document_calls_rag_api(self):
        """문서 추가 시 RAG API를 HTTP로 호출해야 함"""
        from app.services.rag_client import RAGServiceClient

        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"doc_id": "new-doc-123"}

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post.return_value = mock_response
            mock_client_class.return_value = mock_client

            client = RAGServiceClient()
            result = await client.add_document(
                content="Test content",
                metadata={"filename": "test.txt"}
            )

            mock_client.post.assert_called_once()
            assert result == {"doc_id": "new-doc-123"}

    @pytest.mark.asyncio
    async def test_search_calls_rag_api(self):
        """검색 시 RAG API를 HTTP로 호출해야 함"""
        from app.services.rag_client import RAGServiceClient

        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"content": "result", "score": 0.9, "doc_id": "doc1"}
        ]

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post.return_value = mock_response
            mock_client_class.return_value = mock_client

            client = RAGServiceClient()
            result = await client.search(query="test query", top_k=3)

            mock_client.post.assert_called_once()
            assert len(result) == 1
            assert result[0]["content"] == "result"

    @pytest.mark.asyncio
    async def test_delete_document_calls_rag_api(self):
        """문서 삭제 시 RAG API를 HTTP로 호출해야 함"""
        from app.services.rag_client import RAGServiceClient

        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"deleted": True}

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.delete.return_value = mock_response
            mock_client_class.return_value = mock_client

            client = RAGServiceClient()
            result = await client.delete_document(doc_id="doc-123")

            mock_client.delete.assert_called_once()
            assert "doc-123" in mock_client.delete.call_args[0][0]


class TestDatetimeComparison:
    """datetime 비교 관련 테스트 - Issue #2"""

    def test_sort_documents_with_timezone_aware_datetime(self):
        """timezone-aware datetime으로 정렬해야 함"""
        from app.utils.datetime_utils import get_safe_datetime_for_sort

        # timezone-aware datetime
        aware_dt = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)

        # None인 경우 기본값 반환
        default_dt = get_safe_datetime_for_sort(None)

        # 둘 다 timezone-aware여야 비교 가능
        assert aware_dt.tzinfo is not None
        assert default_dt.tzinfo is not None

        # 비교 가능해야 함 (TypeError 없이)
        assert aware_dt > default_dt

    def test_sort_documents_with_none_updated_at(self):
        """updated_at이 None인 경우 안전하게 처리해야 함"""
        from app.utils.datetime_utils import get_safe_datetime_for_sort

        result = get_safe_datetime_for_sort(None)

        # timezone-aware datetime이어야 함
        assert result.tzinfo is not None
        # datetime.min과 동일한 값이어야 함 (UTC로)
        assert result == datetime.min.replace(tzinfo=timezone.utc)

    def test_sort_mixed_documents(self):
        """timezone-aware와 None이 섞인 문서 목록 정렬"""
        from app.utils.datetime_utils import get_safe_datetime_for_sort

        docs = [
            {"name": "doc1", "updated_at": datetime(2024, 1, 15, tzinfo=timezone.utc)},
            {"name": "doc2", "updated_at": None},
            {"name": "doc3", "updated_at": datetime(2024, 6, 1, tzinfo=timezone.utc)},
        ]

        # 정렬이 에러 없이 동작해야 함
        sorted_docs = sorted(
            docs,
            key=lambda doc: get_safe_datetime_for_sort(doc["updated_at"]),
            reverse=True
        )

        # 최신 날짜가 먼저
        assert sorted_docs[0]["name"] == "doc3"
        assert sorted_docs[1]["name"] == "doc1"
        assert sorted_docs[2]["name"] == "doc2"  # None은 가장 오래된 것으로 처리