"""
Chat Integration Tests

Phase 9.7: Dashboard 채팅 통합 테스트
"""
import pytest
from unittest.mock import AsyncMock, MagicMock


class TestFullChatFlow:
    """전체 채팅 플로우 통합 테스트"""

    @pytest.mark.asyncio
    async def test_full_chat_flow(self):
        """
        전체 채팅 플로우 테스트:
        1. 사용자가 메시지 전송
        2. ChatService가 메시지 처리
        3. LLM이 응답 생성
        4. 스트리밍 응답 반환
        5. 대화 기록 저장
        """
        from services.backend.app.services.chat_service import ChatService

        # Mock LLM client
        mock_llm = MagicMock()

        async def mock_generate_stream(message, system_prompt=None):
            tokens = ["안녕", "하세요", "!", " 반갑습니다", "."]
            for token in tokens:
                yield token

        mock_llm.generate_stream = mock_generate_stream

        # Mock history store
        mock_history = MagicMock()
        mock_history.add_message = AsyncMock(return_value="msg-001")

        # Create ChatService with mocks
        chat_service = ChatService(
            llm_client=mock_llm,
            rag_service=None,
            history_store=mock_history
        )

        # Process message
        session_id = "test-session-001"
        user_message = "안녕하세요"

        events = []
        async for event in chat_service.process_message(
            session_id=session_id,
            message=user_message,
            use_rag=False
        ):
            events.append(event)

        # Verify events
        token_events = [e for e in events if e.get("type") == "token"]
        complete_events = [e for e in events if e.get("type") == "complete"]

        assert len(token_events) > 0, "Should have token events"
        assert len(complete_events) == 1, "Should have complete event"
        assert complete_events[0]["session_id"] == session_id

        # Verify history was saved
        assert mock_history.add_message.call_count == 2  # user + assistant

    @pytest.mark.asyncio
    async def test_chat_flow_without_llm_client(self):
        """LLM 클라이언트 없이 기본 응답 반환 테스트"""
        from services.backend.app.services.chat_service import ChatService

        # ChatService without LLM client
        chat_service = ChatService(
            llm_client=None,
            rag_service=None,
            history_store=None
        )

        events = []
        async for event in chat_service.process_message(
            session_id="test-session",
            message="Hello",
            use_rag=False
        ):
            events.append(event)

        # Should have default response
        token_events = [e for e in events if e.get("type") == "token"]
        assert len(token_events) == 1
        assert "Hello" in token_events[0]["content"]


class TestChatWithRagFlow:
    """RAG 연동 채팅 플로우 테스트"""

    @pytest.mark.asyncio
    async def test_chat_with_rag_flow(self):
        """
        RAG 연동 채팅 플로우 테스트:
        1. 사용자 메시지 수신
        2. RAG 컨텍스트 검색
        3. 컨텍스트와 함께 LLM 호출
        4. 출처 정보와 함께 응답 반환
        """
        from services.backend.app.services.chat_service import ChatService

        # Mock RAG service
        mock_rag = MagicMock()
        mock_rag.retrieve = MagicMock(return_value=[
            {
                "content": "EdgeVoice는 음성 AI 플랫폼입니다.",
                "score": 0.92,
                "doc_id": "doc-001",
                "metadata": {"filename": "overview.md"}
            },
            {
                "content": "STT, LLM, TTS 파이프라인을 지원합니다.",
                "score": 0.88,
                "doc_id": "doc-002",
                "metadata": {"filename": "architecture.md"}
            }
        ])

        # Mock LLM client
        mock_llm = MagicMock()

        async def mock_generate_stream(message, system_prompt=None):
            tokens = ["EdgeVoice", "는 ", "음성 AI", " 플랫폼", "입니다."]
            for token in tokens:
                yield token

        mock_llm.generate_stream = mock_generate_stream

        # Create ChatService
        chat_service = ChatService(
            llm_client=mock_llm,
            rag_service=mock_rag,
            history_store=None
        )

        # Process message with RAG
        events = []
        async for event in chat_service.process_message(
            session_id="test-session",
            message="EdgeVoice란 무엇인가요?",
            use_rag=True
        ):
            events.append(event)

        # Verify RAG context event
        rag_events = [e for e in events if e.get("type") == "rag_context"]
        assert len(rag_events) == 1
        assert "EdgeVoice" in rag_events[0]["content"]
        assert len(rag_events[0]["sources"]) == 2

        # Verify complete event has sources
        complete_events = [e for e in events if e.get("type") == "complete"]
        assert len(complete_events[0]["sources"]) == 2

    @pytest.mark.asyncio
    async def test_chat_with_rag_formats_context_properly(self):
        """RAG 컨텍스트가 올바른 형식으로 포맷되는지 테스트"""
        from services.backend.app.services.chat_rag_integration import ChatRAGIntegration

        # Mock RAG service
        mock_rag = MagicMock()
        mock_rag.retrieve = MagicMock(return_value=[
            {"content": "첫 번째 문서 내용", "score": 0.9, "doc_id": "1", "metadata": {"filename": "doc1.md"}},
            {"content": "두 번째 문서 내용", "score": 0.8, "doc_id": "2", "metadata": {"filename": "doc2.md"}}
        ])

        integration = ChatRAGIntegration(
            rag_service=mock_rag,
            embedding_service=None
        )

        # Get context
        context, sources = await integration.get_context_for_query(
            query="테스트 쿼리",
            top_k=3
        )

        assert context is not None
        assert "첫 번째 문서 내용" in context
        assert "두 번째 문서 내용" in context
        assert len(sources) == 2

    @pytest.mark.asyncio
    async def test_chat_without_rag_skips_retrieval(self):
        """RAG 비활성화 시 검색을 건너뛰는지 테스트"""
        from services.backend.app.services.chat_service import ChatService

        # Mock RAG service that should NOT be called
        mock_rag = MagicMock()
        mock_rag.retrieve = MagicMock(return_value=[])

        # Create ChatService
        chat_service = ChatService(
            llm_client=None,
            rag_service=mock_rag,
            history_store=None
        )

        # Process message with RAG disabled
        events = []
        async for event in chat_service.process_message(
            session_id="test-session",
            message="Hello",
            use_rag=False
        ):
            events.append(event)

        # RAG should not be called
        mock_rag.retrieve.assert_not_called()

        # No RAG context event
        rag_events = [e for e in events if e.get("type") == "rag_context"]
        assert len(rag_events) == 0


class TestChatHistoryFlow:
    """대화 기록 플로우 테스트"""

    @pytest.mark.asyncio
    async def test_chat_history_flow(self):
        """
        대화 기록 플로우 테스트:
        1. 메시지 전송 시 사용자 메시지 저장
        2. 응답 완료 시 AI 응답 저장
        3. 세션별로 그룹화
        """
        from services.backend.app.services.chat_service import ChatService

        # Mock history store
        saved_messages = []

        async def mock_add_message(session_id, role, content, metadata=None):
            saved_messages.append({
                "session_id": session_id,
                "role": role,
                "content": content,
                "metadata": metadata
            })
            return f"msg-{len(saved_messages)}"

        mock_history = MagicMock()
        mock_history.add_message = mock_add_message

        # Create ChatService
        chat_service = ChatService(
            llm_client=None,
            rag_service=None,
            history_store=mock_history
        )

        session_id = "test-session-001"

        # Process message
        async for _ in chat_service.process_message(
            session_id=session_id,
            message="안녕하세요",
            use_rag=False
        ):
            pass

        # Verify messages saved
        assert len(saved_messages) == 2
        assert saved_messages[0]["role"] == "user"
        assert saved_messages[0]["content"] == "안녕하세요"
        assert saved_messages[1]["role"] == "assistant"

    @pytest.mark.asyncio
    async def test_chat_history_saves_rag_sources(self):
        """RAG 출처가 메타데이터로 저장되는지 테스트"""
        from services.backend.app.services.chat_service import ChatService

        # Mock RAG service
        mock_rag = MagicMock()
        mock_rag.retrieve = MagicMock(return_value=[
            {"content": "테스트 내용", "score": 0.9, "doc_id": "doc1", "metadata": {"filename": "test.md"}}
        ])

        # Mock history store
        saved_messages = []

        async def mock_add_message(session_id, role, content, metadata=None):
            saved_messages.append({
                "session_id": session_id,
                "role": role,
                "content": content,
                "metadata": metadata
            })
            return f"msg-{len(saved_messages)}"

        mock_history = MagicMock()
        mock_history.add_message = mock_add_message

        # Create ChatService
        chat_service = ChatService(
            llm_client=None,
            rag_service=mock_rag,
            history_store=mock_history
        )

        # Process message with RAG
        async for _ in chat_service.process_message(
            session_id="test-session",
            message="질문입니다",
            use_rag=True
        ):
            pass

        # Verify assistant message has RAG metadata
        assistant_msg = saved_messages[1]
        assert assistant_msg["metadata"]["rag_used"] is True
        assert len(assistant_msg["metadata"]["sources"]) > 0

    @pytest.mark.asyncio
    async def test_chat_history_groups_by_session(self):
        """세션별로 대화 기록이 그룹화되는지 테스트"""
        from services.backend.app.services.chat_service import ChatService

        # Mock history store with session tracking
        sessions = {}

        async def mock_add_message(session_id, role, content, metadata=None):
            if session_id not in sessions:
                sessions[session_id] = []
            sessions[session_id].append({
                "role": role,
                "content": content,
                "metadata": metadata
            })
            return f"msg-{len(sessions[session_id])}"

        mock_history = MagicMock()
        mock_history.add_message = mock_add_message

        # Create ChatService
        chat_service = ChatService(
            llm_client=None,
            rag_service=None,
            history_store=mock_history
        )

        # Process messages in different sessions
        async for _ in chat_service.process_message("session-1", "Hello", False):
            pass
        async for _ in chat_service.process_message("session-2", "안녕", False):
            pass

        # Verify sessions are separate
        assert len(sessions) == 2
        assert len(sessions["session-1"]) == 2
        assert len(sessions["session-2"]) == 2
        assert sessions["session-1"][0]["content"] == "Hello"
        assert sessions["session-2"][0]["content"] == "안녕"
