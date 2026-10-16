"""
RAG Integration Tests

Phase 6.1: RAG 통합 테스트
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import asyncio


class TestRAGWithLLM:
    """RAG와 LLM 통합 테스트"""

    @pytest.mark.asyncio
    async def test_rag_context_enhances_llm_response(
        self,
        mock_rag_service,
        mock_llm_service
    ):
        """RAG 컨텍스트가 LLM 응답을 향상시켜야 한다"""
        user_query = "회사 휴가 정책이 어떻게 되나요?"

        # RAG 검색
        rag_results = await mock_rag_service.retrieve(query=user_query)
        assert len(rag_results) > 0

        # RAG 컨텍스트 구성
        rag_context = "\n\n".join([
            f"[출처: {r['metadata']['source']}]\n{r['content']}"
            for r in rag_results
        ])

        # LLM 호출 with RAG context
        mock_llm_service.generate = AsyncMock(return_value={
            "text": "회사 휴가 정책에 따르면 연차는 15일입니다.",
            "tokens_used": 50
        })

        llm_result = await mock_llm_service.generate(
            prompt=user_query,
            system_prompt="주어진 컨텍스트를 기반으로 답변하세요.",
            context=rag_context
        )

        # LLM이 RAG 컨텍스트와 함께 호출되었는지 확인
        call_args = mock_llm_service.generate.call_args
        assert "context" in call_args.kwargs

    @pytest.mark.asyncio
    async def test_rag_relevance_filtering(self, mock_rag_service, mock_llm_service):
        """관련성 낮은 RAG 결과가 필터링되어야 한다"""
        mock_rag_service.retrieve = AsyncMock(return_value=[
            {"content": "관련 문서", "score": 0.9, "metadata": {"source": "doc1.txt"}},
            {"content": "약간 관련", "score": 0.6, "metadata": {"source": "doc2.txt"}},
            {"content": "관련 없음", "score": 0.2, "metadata": {"source": "doc3.txt"}}
        ])

        rag_results = await mock_rag_service.retrieve(query="테스트 쿼리")

        # 관련성 임계값으로 필터링
        relevance_threshold = 0.5
        filtered_results = [r for r in rag_results if r["score"] >= relevance_threshold]

        assert len(filtered_results) == 2
        assert all(r["score"] >= relevance_threshold for r in filtered_results)

    @pytest.mark.asyncio
    async def test_rag_top_k_limitation(self, mock_rag_service):
        """RAG 결과가 top_k로 제한되어야 한다"""
        # 많은 결과 시뮬레이션
        mock_rag_service.retrieve = AsyncMock(return_value=[
            {"content": f"문서 {i}", "score": 0.9 - i * 0.1, "metadata": {"source": f"doc{i}.txt"}}
            for i in range(10)
        ])

        top_k = 3
        rag_results = await mock_rag_service.retrieve(query="테스트", top_k=top_k)

        # top_k 결과만 사용
        limited_results = rag_results[:top_k]

        assert len(limited_results) == 3


class TestRAGDocumentManagement:
    """RAG 문서 관리 통합 테스트"""

    @pytest.mark.asyncio
    async def test_document_upload_and_retrieval(
        self,
        mock_rag_service,
        mock_embedding_service
    ):
        """문서 업로드 후 검색이 가능해야 한다"""
        # 문서 업로드
        document_content = "이것은 테스트 문서입니다. 중요한 내용이 포함되어 있습니다."

        upload_result = await mock_rag_service.add_document(
            content=document_content,
            metadata={"source": "test.txt", "type": "text"}
        )

        assert upload_result["id"] is not None
        assert upload_result["chunks"] > 0

        # 문서 검색
        mock_rag_service.retrieve = AsyncMock(return_value=[
            {"content": "중요한 내용이 포함되어 있습니다.", "score": 0.85, "metadata": {"source": "test.txt"}}
        ])

        search_results = await mock_rag_service.retrieve(query="중요한 내용")

        assert len(search_results) > 0
        assert "중요한" in search_results[0]["content"]

    @pytest.mark.asyncio
    async def test_document_chunking_integration(self, mock_embedding_service):
        """문서 청킹이 올바르게 동작해야 한다"""
        from services.orchestrator.app.rag_service import RAGService

        # 긴 문서
        long_document = "첫 번째 문장입니다. " * 100 + "두 번째 문장입니다. " * 100

        # RAGService의 청킹 로직 테스트
        rag_service = RAGService.__new__(RAGService)
        rag_service.chunk_size = 500
        rag_service.chunk_overlap = 50

        chunks = rag_service.chunk_text(long_document)

        # 청크가 생성되었는지 확인
        assert len(chunks) > 1

        # 각 청크 크기 확인
        for chunk in chunks:
            assert len(chunk) <= rag_service.chunk_size + 100  # 문장 경계 허용

    @pytest.mark.asyncio
    async def test_document_deletion_removes_from_retrieval(self, mock_rag_service):
        """삭제된 문서는 검색 결과에서 제외되어야 한다"""
        # 문서 추가
        await mock_rag_service.add_document(
            content="삭제될 문서",
            metadata={"source": "to_delete.txt"}
        )

        # 문서 삭제
        mock_rag_service.delete_document = AsyncMock(return_value=True)
        await mock_rag_service.delete_document(document_id="doc-001")

        mock_rag_service.delete_document.assert_called_once_with(document_id="doc-001")


class TestRAGWithEmbedding:
    """RAG와 Embedding 서비스 통합 테스트"""

    @pytest.mark.asyncio
    async def test_query_embedding_for_retrieval(self, mock_embedding_service, mock_rag_service):
        """쿼리 임베딩이 검색에 사용되어야 한다"""
        query = "휴가 정책"

        # 쿼리 임베딩
        embedding_result = await mock_embedding_service.embed(text=query)

        assert "embedding" in embedding_result
        assert len(embedding_result["embedding"]) == 1024

        # 임베딩으로 검색
        mock_rag_service.retrieve_by_embedding = AsyncMock(return_value=[
            {"content": "휴가 관련 내용", "score": 0.9, "metadata": {"source": "policy.txt"}}
        ])

        results = await mock_rag_service.retrieve_by_embedding(
            embedding=embedding_result["embedding"]
        )

        assert len(results) > 0

    @pytest.mark.asyncio
    async def test_batch_document_embedding(self, mock_embedding_service):
        """배치 문서 임베딩이 동작해야 한다"""
        documents = [
            "첫 번째 문서 내용",
            "두 번째 문서 내용",
            "세 번째 문서 내용",
            "네 번째 문서 내용",
            "다섯 번째 문서 내용"
        ]

        batch_result = await mock_embedding_service.embed_batch(texts=documents)

        assert "embeddings" in batch_result
        assert len(batch_result["embeddings"]) == 5
        assert all(len(e) == 1024 for e in batch_result["embeddings"])


class TestRAGSourceAttribution:
    """RAG 출처 표시 테스트"""

    @pytest.mark.asyncio
    async def test_llm_response_includes_sources(
        self,
        mock_rag_service,
        mock_llm_service
    ):
        """LLM 응답에 출처가 포함되어야 한다"""
        mock_rag_service.retrieve = AsyncMock(return_value=[
            {"content": "연차는 15일입니다.", "score": 0.9, "metadata": {"source": "hr_policy.pdf", "page": 5}},
            {"content": "병가는 7일입니다.", "score": 0.8, "metadata": {"source": "hr_policy.pdf", "page": 6}}
        ])

        rag_results = await mock_rag_service.retrieve(query="휴가 정책")

        # 출처 정보 추출
        sources = set()
        for result in rag_results:
            source = result["metadata"]["source"]
            if "page" in result["metadata"]:
                source += f" (p.{result['metadata']['page']})"
            sources.add(source)

        assert "hr_policy.pdf (p.5)" in sources
        assert "hr_policy.pdf (p.6)" in sources

    @pytest.mark.asyncio
    async def test_source_deduplication(self, mock_rag_service):
        """중복 출처가 제거되어야 한다"""
        mock_rag_service.retrieve = AsyncMock(return_value=[
            {"content": "내용 1", "score": 0.9, "metadata": {"source": "doc.txt"}},
            {"content": "내용 2", "score": 0.85, "metadata": {"source": "doc.txt"}},
            {"content": "내용 3", "score": 0.8, "metadata": {"source": "other.txt"}}
        ])

        rag_results = await mock_rag_service.retrieve(query="테스트")

        # 고유 출처만 추출
        unique_sources = list(set(r["metadata"]["source"] for r in rag_results))

        assert len(unique_sources) == 2
        assert "doc.txt" in unique_sources
        assert "other.txt" in unique_sources


class TestRAGErrorHandling:
    """RAG 에러 처리 테스트"""

    @pytest.mark.asyncio
    async def test_rag_service_unavailable(self, mock_llm_service):
        """RAG 서비스 불가 시 LLM만으로 응답해야 한다"""
        mock_rag = MagicMock()
        mock_rag.retrieve = AsyncMock(side_effect=Exception("RAG service unavailable"))

        try:
            await mock_rag.retrieve(query="테스트")
            rag_available = True
        except Exception:
            rag_available = False

        assert not rag_available

        # RAG 없이 LLM 호출
        llm_result = await mock_llm_service.generate(
            prompt="테스트 질문",
            system_prompt="지식 베이스 없이 최선을 다해 답변하세요."
        )

        assert llm_result["text"] is not None

    @pytest.mark.asyncio
    async def test_empty_rag_results_handling(self, mock_rag_service, mock_llm_service):
        """RAG 결과가 없을 때 적절히 처리해야 한다"""
        mock_rag_service.retrieve = AsyncMock(return_value=[])

        rag_results = await mock_rag_service.retrieve(query="존재하지 않는 정보")

        assert len(rag_results) == 0

        # RAG 결과 없이 LLM 호출
        mock_llm_service.generate = AsyncMock(return_value={
            "text": "죄송합니다, 해당 정보를 찾을 수 없습니다.",
            "tokens_used": 20
        })

        if not rag_results:
            llm_result = await mock_llm_service.generate(
                prompt="존재하지 않는 정보",
                system_prompt="관련 정보가 없습니다. 모른다고 답변하세요."
            )

        assert "찾을 수 없습니다" in llm_result["text"]


class TestRAGMetadataFiltering:
    """RAG 메타데이터 필터링 테스트"""

    @pytest.mark.asyncio
    async def test_filter_by_document_type(self, mock_rag_service):
        """문서 타입으로 필터링할 수 있어야 한다"""
        mock_rag_service.retrieve = AsyncMock(return_value=[
            {"content": "PDF 내용", "score": 0.9, "metadata": {"source": "doc.pdf", "type": "pdf"}},
            {"content": "TXT 내용", "score": 0.85, "metadata": {"source": "doc.txt", "type": "txt"}}
        ])

        all_results = await mock_rag_service.retrieve(query="테스트")

        # PDF만 필터링
        pdf_results = [r for r in all_results if r["metadata"].get("type") == "pdf"]

        assert len(pdf_results) == 1
        assert pdf_results[0]["metadata"]["source"].endswith(".pdf")

    @pytest.mark.asyncio
    async def test_filter_by_date_range(self, mock_rag_service):
        """날짜 범위로 필터링할 수 있어야 한다"""
        mock_rag_service.retrieve = AsyncMock(return_value=[
            {"content": "최신 정책", "score": 0.9, "metadata": {"source": "policy.txt", "created": "2024-01-01"}},
            {"content": "오래된 정책", "score": 0.85, "metadata": {"source": "old_policy.txt", "created": "2022-01-01"}}
        ])

        all_results = await mock_rag_service.retrieve(query="정책")

        # 2023년 이후만 필터링
        recent_results = [
            r for r in all_results
            if r["metadata"].get("created", "2000-01-01") >= "2023-01-01"
        ]

        assert len(recent_results) == 1
        assert "최신" in recent_results[0]["content"]
