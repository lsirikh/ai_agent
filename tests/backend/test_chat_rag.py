"""
Backend API - Chat RAG Integration Tests

Phase 9.3: 채팅과 RAG 통합 테스트
"""
from unittest.mock import AsyncMock, MagicMock

import pytest


class TestChatWithRAGContext:
    """RAG 컨텍스트 검색 테스트"""

    @pytest.mark.asyncio
    async def test_chat_with_rag_retrieves_context(self):
        """use_rag=True일 때 RAG 컨텍스트를 검색해야 한다"""
        from services.backend.app.services.chat_service import ChatService

        # Mock RAG service
        mock_rag = MagicMock()
        mock_rag.retrieve = MagicMock(return_value=[
            {
                "content": "관련 문서 내용입니다.",
                "doc_id": "doc-1",
                "metadata": {"filename": "test.pdf"},
                "score": 0.9
            }
        ])

        # Mock LLM
        mock_llm = MagicMock()

        async def mock_stream(text, system_prompt=None, **kwargs):
            yield "응답"

        mock_llm.generate_stream = mock_stream

        service = ChatService(llm_client=mock_llm, rag_service=mock_rag)

        events = []
        async for event in service.process_message(
            session_id="test-session",
            message="문서에서 정보 찾아줘",
            use_rag=True
        ):
            events.append(event)

        # RAG retrieve가 호출되었는지 확인
        mock_rag.retrieve.assert_called_once()

    @pytest.mark.asyncio
    async def test_chat_with_rag_formats_context(self):
        """RAG 컨텍스트가 올바르게 포맷되어야 한다"""
        from services.backend.app.services.chat_service import ChatService

        mock_rag = MagicMock()
        mock_rag.retrieve = MagicMock(return_value=[
            {
                "content": "첫 번째 문서 내용",
                "doc_id": "doc-1",
                "metadata": {"filename": "doc1.pdf"},
                "score": 0.95
            },
            {
                "content": "두 번째 문서 내용",
                "doc_id": "doc-2",
                "metadata": {"filename": "doc2.pdf"},
                "score": 0.85
            }
        ])

        mock_llm = MagicMock()

        async def mock_stream(text, system_prompt=None, reference=None, **kwargs):
            # RAG 컨텍스트는 이번 질문에 붙는 참고 자료로 전달되고
            # 시스템 프롬프트는 고정(접두사 캐시)
            assert "첫 번째 문서 내용" in reference
            assert "두 번째 문서 내용" in reference
            assert "첫 번째 문서 내용" not in system_prompt
            yield "응답"

        mock_llm.generate_stream = mock_stream

        service = ChatService(llm_client=mock_llm, rag_service=mock_rag)

        events = []
        async for event in service.process_message(
            session_id="test-session",
            message="테스트",
            use_rag=True
        ):
            events.append(event)

    @pytest.mark.asyncio
    async def test_chat_with_rag_includes_sources(self):
        """RAG 사용 시 출처 정보가 포함되어야 한다"""
        from services.backend.app.services.chat_service import ChatService

        mock_rag = MagicMock()
        mock_rag.retrieve = MagicMock(return_value=[
            {
                "content": "관련 내용",
                "doc_id": "doc-123",
                "metadata": {"filename": "policy.pdf"},
                "score": 0.9
            }
        ])

        mock_llm = MagicMock()

        async def mock_stream(text, system_prompt=None, **kwargs):
            yield "응답"

        mock_llm.generate_stream = mock_stream

        service = ChatService(llm_client=mock_llm, rag_service=mock_rag)

        events = []
        async for event in service.process_message(
            session_id="test-session",
            message="정책 알려줘",
            use_rag=True
        ):
            events.append(event)

        # 완료 이벤트에 sources가 포함되어야 함
        complete_events = [e for e in events if e["type"] == "complete"]
        assert len(complete_events) == 1
        assert "sources" in complete_events[0]
        assert len(complete_events[0]["sources"]) > 0
        assert complete_events[0]["sources"][0]["doc_id"] == "doc-123"

    @pytest.mark.asyncio
    async def test_chat_without_rag_skips_retrieval(self):
        """use_rag=False일 때 RAG 검색을 스킵해야 한다"""
        from services.backend.app.services.chat_service import ChatService

        mock_rag = MagicMock()
        mock_rag.retrieve = MagicMock(return_value=[])

        mock_llm = MagicMock()

        async def mock_stream(text, system_prompt=None, **kwargs):
            yield "응답"

        mock_llm.generate_stream = mock_stream

        service = ChatService(llm_client=mock_llm, rag_service=mock_rag)

        events = []
        async for event in service.process_message(
            session_id="test-session",
            message="테스트",
            use_rag=False  # RAG 비활성화
        ):
            events.append(event)

        # RAG retrieve가 호출되지 않아야 함
        mock_rag.retrieve.assert_not_called()


class TestChatRAGContextEvent:
    """RAG 컨텍스트 이벤트 테스트"""

    @pytest.mark.asyncio
    async def test_rag_context_event_emitted(self):
        """RAG 컨텍스트 검색 시 rag_context 이벤트가 발행되어야 한다"""
        from services.backend.app.services.chat_service import ChatService

        mock_rag = MagicMock()
        mock_rag.retrieve = MagicMock(return_value=[
            {
                "content": "컨텍스트 내용",
                "doc_id": "doc-1",
                "metadata": {"filename": "test.pdf"},
                "score": 0.9
            }
        ])

        mock_llm = MagicMock()

        async def mock_stream(text, system_prompt=None, **kwargs):
            yield "응답"

        mock_llm.generate_stream = mock_stream

        service = ChatService(llm_client=mock_llm, rag_service=mock_rag)

        events = []
        async for event in service.process_message(
            session_id="test-session",
            message="테스트",
            use_rag=True
        ):
            events.append(event)

        # rag_context 이벤트 확인
        rag_events = [e for e in events if e["type"] == "rag_context"]
        assert len(rag_events) == 1
        assert "content" in rag_events[0]
        assert "컨텍스트 내용" in rag_events[0]["content"]


class TestChatRAGIntegrationClass:
    """ChatRAGIntegration 클래스 테스트"""

    def test_chat_rag_integration_init(self):
        """ChatRAGIntegration이 초기화되어야 한다"""
        from services.backend.app.services.chat_rag_integration import ChatRAGIntegration

        mock_rag = MagicMock()
        mock_embedding = MagicMock()

        integration = ChatRAGIntegration(
            rag_service=mock_rag,
            embedding_service=mock_embedding
        )

        assert integration is not None
        assert integration.rag_service == mock_rag
        assert integration.embedding_service == mock_embedding

    @pytest.mark.asyncio
    async def test_get_context_for_query(self):
        """get_context_for_query가 컨텍스트를 반환해야 한다"""
        from services.backend.app.services.chat_rag_integration import ChatRAGIntegration

        mock_rag = MagicMock()
        mock_rag.retrieve = MagicMock(return_value=[
            {
                "content": "관련 내용",
                "doc_id": "doc-1",
                "metadata": {"filename": "test.pdf"},
                "score": 0.9
            }
        ])

        integration = ChatRAGIntegration(rag_service=mock_rag)

        context, sources = await integration.get_context_for_query(
            query="테스트 질문",
            top_k=3
        )

        assert context is not None
        assert "관련 내용" in context
        assert len(sources) == 1
        assert sources[0]["doc_id"] == "doc-1"

    @pytest.mark.asyncio
    async def test_get_context_filters_by_score(self):
        """낮은 점수의 결과는 필터링해야 한다"""
        from services.backend.app.services.chat_rag_integration import ChatRAGIntegration

        mock_rag = MagicMock()
        mock_rag.retrieve = MagicMock(return_value=[
            {
                "content": "높은 점수 문서",
                "doc_id": "doc-1",
                "metadata": {"filename": "high.pdf"},
                "score": 0.9
            },
            {
                "content": "낮은 점수 문서",
                "doc_id": "doc-2",
                "metadata": {"filename": "low.pdf"},
                "score": 0.3  # 임계값 미만
            }
        ])

        integration = ChatRAGIntegration(rag_service=mock_rag)

        context, sources = await integration.get_context_for_query(
            query="테스트",
            top_k=3,
            score_threshold=0.5  # 0.5 이상만
        )

        # 낮은 점수는 필터링
        assert len(sources) == 1
        assert sources[0]["doc_id"] == "doc-1"
