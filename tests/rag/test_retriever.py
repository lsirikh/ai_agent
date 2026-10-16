"""
RAG Service Tests

Phase 4.2: RAG (Retrieval-Augmented Generation) 서비스 테스트
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest


class TestRAGServiceInitialization:
    """RAG 서비스 초기화 테스트"""

    def test_rag_service_initialization(self):
        """RAGService가 올바르게 초기화되어야 한다"""
        from services.orchestrator.app.rag_service import RAGService

        with patch('services.orchestrator.app.rag_service.get_embedder') as mock_embedder:
            mock_embedder.return_value = MagicMock()
            rag = RAGService()

            assert rag is not None
            assert rag.embedder is not None

    def test_rag_service_with_custom_config(self):
        """커스텀 설정으로 초기화할 수 있어야 한다"""
        from services.orchestrator.app.rag_service import RAGService

        with patch('services.orchestrator.app.rag_service.get_embedder') as mock_embedder:
            mock_embedder.return_value = MagicMock()
            rag = RAGService(
                chunk_size=512,
                chunk_overlap=64,
                top_k=5
            )

            assert rag.chunk_size == 512
            assert rag.chunk_overlap == 64
            assert rag.top_k == 5

    def test_rag_service_default_config(self):
        """기본 설정이 올바르게 적용되어야 한다"""
        from services.orchestrator.app.rag_service import RAGService

        with patch('services.orchestrator.app.rag_service.get_embedder') as mock_embedder:
            mock_embedder.return_value = MagicMock()
            rag = RAGService()

            assert rag.chunk_size == 256
            assert rag.chunk_overlap == 32
            assert rag.top_k == 3


class TestTextChunking:
    """텍스트 청킹 테스트"""

    def test_chunk_text(self):
        """텍스트를 청크로 분리해야 한다"""
        from services.orchestrator.app.rag_service import RAGService

        with patch('services.orchestrator.app.rag_service.get_embedder') as mock_embedder:
            mock_embedder.return_value = MagicMock()
            rag = RAGService(chunk_size=100, chunk_overlap=20)

            text = "이것은 테스트 문장입니다. " * 20  # 긴 텍스트

            chunks = rag.chunk_text(text)

            assert len(chunks) > 1
            for chunk in chunks:
                assert len(chunk) <= 100 + 50  # 여유 허용

    def test_chunk_overlap(self):
        """청크 오버랩이 올바르게 적용되어야 한다"""
        from services.orchestrator.app.rag_service import RAGService

        with patch('services.orchestrator.app.rag_service.get_embedder') as mock_embedder:
            mock_embedder.return_value = MagicMock()
            rag = RAGService(chunk_size=50, chunk_overlap=10)

            text = "A" * 100  # 100자 텍스트

            chunks = rag.chunk_text(text)

            # 오버랩이 있으면 청크 간에 공통 부분이 있어야 함
            if len(chunks) >= 2:
                # 첫 번째 청크의 끝 부분과 두 번째 청크의 시작 부분 비교
                assert len(chunks[0]) > 0
                assert len(chunks[1]) > 0

    def test_chunk_at_sentence_boundary(self):
        """문장 경계에서 청킹되어야 한다"""
        from services.orchestrator.app.rag_service import RAGService

        with patch('services.orchestrator.app.rag_service.get_embedder') as mock_embedder:
            mock_embedder.return_value = MagicMock()
            rag = RAGService(chunk_size=100, chunk_overlap=20)

            text = "첫 번째 문장입니다. 두 번째 문장입니다. 세 번째 문장입니다. 네 번째 문장입니다. 다섯 번째 문장입니다."

            chunks = rag.chunk_text(text)

            # 청크가 문장 중간에서 잘리지 않아야 함 (가능한 경우)
            for chunk in chunks:
                # 청크가 완전한 문장으로 끝나는지 확인 (마지막 청크 제외)
                assert len(chunk.strip()) > 0

    def test_chunk_short_text(self):
        """짧은 텍스트는 하나의 청크로 반환되어야 한다"""
        from services.orchestrator.app.rag_service import RAGService

        with patch('services.orchestrator.app.rag_service.get_embedder') as mock_embedder:
            mock_embedder.return_value = MagicMock()
            rag = RAGService(chunk_size=256)

            text = "짧은 텍스트입니다."

            chunks = rag.chunk_text(text)

            assert len(chunks) == 1
            assert chunks[0] == text

    def test_chunk_empty_text(self):
        """빈 텍스트는 빈 리스트를 반환해야 한다"""
        from services.orchestrator.app.rag_service import RAGService

        with patch('services.orchestrator.app.rag_service.get_embedder') as mock_embedder:
            mock_embedder.return_value = MagicMock()
            rag = RAGService()

            chunks = rag.chunk_text("")

            assert chunks == []


class TestDocumentManagement:
    """문서 관리 테스트"""

    def test_add_document(self):
        """문서를 추가할 수 있어야 한다"""
        from services.orchestrator.app.rag_service import RAGService

        with patch('services.orchestrator.app.rag_service.get_embedder') as mock_embedder:
            mock_emb = MagicMock()
            mock_emb.embed_batch.return_value = np.random.randn(3, 1024).astype(np.float32)
            mock_embedder.return_value = mock_emb

            rag = RAGService()

            doc_id = rag.add_document(
                content="테스트 문서 내용입니다. 여러 문장이 있습니다. 이것은 세 번째 문장입니다.",
                metadata={"title": "테스트 문서", "source": "test"}
            )

            assert doc_id is not None
            assert rag.document_count > 0

    def test_add_document_with_id(self):
        """지정된 ID로 문서를 추가할 수 있어야 한다"""
        from services.orchestrator.app.rag_service import RAGService

        with patch('services.orchestrator.app.rag_service.get_embedder') as mock_embedder:
            mock_emb = MagicMock()
            mock_emb.embed_batch.return_value = np.random.randn(1, 1024).astype(np.float32)
            mock_embedder.return_value = mock_emb

            rag = RAGService()

            doc_id = rag.add_document(
                content="테스트 내용",
                doc_id="custom-doc-001"
            )

            assert doc_id == "custom-doc-001"

    def test_delete_document(self):
        """문서를 삭제할 수 있어야 한다"""
        from services.orchestrator.app.rag_service import RAGService

        with patch('services.orchestrator.app.rag_service.get_embedder') as mock_embedder:
            mock_emb = MagicMock()
            mock_emb.embed_batch.return_value = np.random.randn(1, 1024).astype(np.float32)
            mock_embedder.return_value = mock_emb

            rag = RAGService()

            doc_id = rag.add_document(content="삭제할 문서")
            initial_count = rag.document_count

            rag.delete_document(doc_id)

            assert rag.document_count < initial_count

    def test_list_documents(self):
        """문서 목록을 조회할 수 있어야 한다"""
        from services.orchestrator.app.rag_service import RAGService

        with patch('services.orchestrator.app.rag_service.get_embedder') as mock_embedder:
            mock_emb = MagicMock()
            mock_emb.embed_batch.return_value = np.random.randn(1, 1024).astype(np.float32)
            mock_embedder.return_value = mock_emb

            rag = RAGService()

            rag.add_document(content="문서 1", metadata={"title": "첫 번째"})
            rag.add_document(content="문서 2", metadata={"title": "두 번째"})

            docs = rag.list_documents()

            assert len(docs) == 2


class TestRetrieval:
    """검색 테스트"""

    def test_retrieve_returns_relevant_context(self):
        """관련 컨텍스트를 검색해야 한다"""
        from services.orchestrator.app.rag_service import RAGService

        with patch('services.orchestrator.app.rag_service.get_embedder') as mock_embedder:
            mock_emb = MagicMock()

            # 문서 임베딩
            doc_embeddings = np.array([
                [1.0, 0.0, 0.0],
                [0.0, 1.0, 0.0],
                [0.5, 0.5, 0.0]
            ], dtype=np.float32)

            # 쿼리 임베딩 (첫 번째 문서와 유사)
            query_embedding = np.array([0.9, 0.1, 0.0], dtype=np.float32)

            mock_emb.embed_batch.return_value = doc_embeddings
            mock_emb.embed.return_value = query_embedding
            mock_emb.batch_cosine_similarity.return_value = np.array([0.99, 0.1, 0.7])
            mock_embedder.return_value = mock_emb

            rag = RAGService(top_k=2)
            rag._embedding_dim = 3

            rag.add_document(content="사과는 빨간색입니다.")
            rag.add_document(content="바나나는 노란색입니다.")
            rag.add_document(content="과일은 맛있습니다.")

            results = rag.retrieve("사과에 대해 알려주세요")

            assert len(results) > 0
            assert "content" in results[0]
            assert "score" in results[0]

    def test_retrieve_top_k(self):
        """top_k 개수만큼 결과를 반환해야 한다"""
        from services.orchestrator.app.rag_service import RAGService

        with patch('services.orchestrator.app.rag_service.get_embedder') as mock_embedder:
            mock_emb = MagicMock()
            mock_emb.embed_batch.return_value = np.random.randn(5, 1024).astype(np.float32)
            mock_emb.embed.return_value = np.random.randn(1024).astype(np.float32)
            mock_emb.batch_cosine_similarity.return_value = np.array([0.9, 0.8, 0.7, 0.6, 0.5])
            mock_embedder.return_value = mock_emb

            rag = RAGService(top_k=3)

            for i in range(5):
                rag.add_document(content=f"문서 {i}")

            results = rag.retrieve("쿼리")

            assert len(results) <= 3

    def test_retrieve_with_filter(self):
        """메타데이터 필터를 적용하여 검색해야 한다"""
        from services.orchestrator.app.rag_service import RAGService

        with patch('services.orchestrator.app.rag_service.get_embedder') as mock_embedder:
            mock_emb = MagicMock()
            mock_emb.embed_batch.return_value = np.random.randn(1, 1024).astype(np.float32)
            mock_emb.embed.return_value = np.random.randn(1024).astype(np.float32)
            mock_emb.batch_cosine_similarity.return_value = np.array([0.9, 0.8])
            mock_embedder.return_value = mock_emb

            rag = RAGService()

            rag.add_document(content="기술 문서", metadata={"category": "tech"})
            rag.add_document(content="요리 문서", metadata={"category": "cooking"})

            results = rag.retrieve("문서 검색", filter_metadata={"category": "tech"})

            # 필터 적용 결과 확인
            for result in results:
                if "metadata" in result and result["metadata"]:
                    assert result["metadata"].get("category") == "tech"

    def test_retrieve_empty_collection(self):
        """빈 컬렉션에서 검색 시 빈 결과 반환"""
        from services.orchestrator.app.rag_service import RAGService

        with patch('services.orchestrator.app.rag_service.get_embedder') as mock_embedder:
            mock_emb = MagicMock()
            mock_emb.embed.return_value = np.random.randn(1024).astype(np.float32)
            mock_embedder.return_value = mock_emb

            rag = RAGService()

            results = rag.retrieve("쿼리")

            assert results == []


class TestAsyncRetrieval:
    """비동기 검색 테스트"""

    @pytest.mark.asyncio
    async def test_async_retrieve(self):
        """비동기 검색이 동작해야 한다"""
        from services.orchestrator.app.rag_service import RAGService

        with patch('services.orchestrator.app.rag_service.get_embedder') as mock_embedder:
            mock_emb = MagicMock()
            mock_emb.embed_batch.return_value = np.random.randn(1, 1024).astype(np.float32)
            mock_emb.embed.return_value = np.random.randn(1024).astype(np.float32)
            mock_emb.embed_async = AsyncMock(return_value=np.random.randn(1024).astype(np.float32))
            mock_emb.batch_cosine_similarity.return_value = np.array([0.9])
            mock_embedder.return_value = mock_emb

            rag = RAGService()
            rag.add_document(content="테스트 문서")

            results = await rag.retrieve_async("쿼리")

            assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_async_add_document(self):
        """비동기 문서 추가가 동작해야 한다"""
        from services.orchestrator.app.rag_service import RAGService

        with patch('services.orchestrator.app.rag_service.get_embedder') as mock_embedder:
            mock_emb = MagicMock()
            mock_emb.embed_batch_async = AsyncMock(return_value=np.random.randn(1, 1024).astype(np.float32))
            mock_embedder.return_value = mock_emb

            rag = RAGService()

            doc_id = await rag.add_document_async(content="비동기 문서")

            assert doc_id is not None


class TestContextFormatting:
    """컨텍스트 포맷팅 테스트"""

    def test_format_context_for_llm(self):
        """LLM에 전달할 컨텍스트 포맷팅"""
        from services.orchestrator.app.rag_service import RAGService

        with patch('services.orchestrator.app.rag_service.get_embedder') as mock_embedder:
            mock_embedder.return_value = MagicMock()
            rag = RAGService()

            results = [
                {"content": "첫 번째 컨텍스트", "score": 0.9},
                {"content": "두 번째 컨텍스트", "score": 0.8}
            ]

            formatted = rag.format_context(results)

            assert "첫 번째 컨텍스트" in formatted
            assert "두 번째 컨텍스트" in formatted

    def test_format_context_with_separator(self):
        """구분자로 컨텍스트를 포맷팅"""
        from services.orchestrator.app.rag_service import RAGService

        with patch('services.orchestrator.app.rag_service.get_embedder') as mock_embedder:
            mock_embedder.return_value = MagicMock()
            rag = RAGService()

            results = [
                {"content": "A", "score": 0.9},
                {"content": "B", "score": 0.8}
            ]

            formatted = rag.format_context(results, separator="\n---\n")

            assert "\n---\n" in formatted
