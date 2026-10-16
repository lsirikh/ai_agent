"""
Backend API - Chat History Tests

Phase 9.4: 채팅 기록 자동 저장 테스트
"""
from unittest.mock import AsyncMock, MagicMock

import pytest


class TestChatSavesMessages:
    """채팅 메시지 저장 테스트"""

    @pytest.mark.asyncio
    async def test_chat_saves_user_message(self):
        """사용자 메시지가 저장되어야 한다"""
        from services.backend.app.services.chat_service import ChatService

        mock_llm = MagicMock()

        async def mock_stream(text, system_prompt=None, **kwargs):
            yield "응답"

        mock_llm.generate_stream = mock_stream

        mock_history = MagicMock()
        mock_history.add_message = AsyncMock()

        service = ChatService(
            llm_client=mock_llm,
            history_store=mock_history
        )

        events = []
        async for event in service.process_message(
            session_id="test-session",
            message="안녕하세요",
            use_rag=False
        ):
            events.append(event)

        # add_message가 호출되었는지 확인
        calls = mock_history.add_message.call_args_list

        # 사용자 메시지 저장 확인
        user_calls = [
            c for c in calls
            if c.kwargs.get("role") == "user"
        ]
        assert len(user_calls) == 1
        assert user_calls[0].kwargs["content"] == "안녕하세요"

    @pytest.mark.asyncio
    async def test_chat_saves_assistant_response(self):
        """AI 응답이 저장되어야 한다"""
        from services.backend.app.services.chat_service import ChatService

        mock_llm = MagicMock()

        async def mock_stream(text, system_prompt=None, **kwargs):
            yield "AI 응답"

        mock_llm.generate_stream = mock_stream

        mock_history = MagicMock()
        mock_history.add_message = AsyncMock()

        service = ChatService(
            llm_client=mock_llm,
            history_store=mock_history
        )

        events = []
        async for event in service.process_message(
            session_id="test-session",
            message="테스트",
            use_rag=False
        ):
            events.append(event)

        calls = mock_history.add_message.call_args_list

        # AI 응답 저장 확인
        assistant_calls = [
            c for c in calls
            if c.kwargs.get("role") == "assistant"
        ]
        assert len(assistant_calls) == 1
        assert "AI 응답" in assistant_calls[0].kwargs["content"]

    @pytest.mark.asyncio
    async def test_chat_saves_rag_sources(self):
        """RAG 출처가 메타데이터에 저장되어야 한다"""
        from services.backend.app.services.chat_service import ChatService

        mock_llm = MagicMock()

        async def mock_stream(text, system_prompt=None, **kwargs):
            yield "응답"

        mock_llm.generate_stream = mock_stream

        mock_rag = MagicMock()
        mock_rag.retrieve = MagicMock(return_value=[
            {
                "content": "문서 내용",
                "doc_id": "doc-1",
                "metadata": {"filename": "test.pdf"},
                "score": 0.9
            }
        ])

        mock_history = MagicMock()
        mock_history.add_message = AsyncMock()

        service = ChatService(
            llm_client=mock_llm,
            rag_service=mock_rag,
            history_store=mock_history
        )

        events = []
        async for event in service.process_message(
            session_id="test-session",
            message="테스트",
            use_rag=True
        ):
            events.append(event)

        calls = mock_history.add_message.call_args_list

        # AI 응답에 메타데이터가 있는지 확인
        assistant_calls = [
            c for c in calls
            if c.kwargs.get("role") == "assistant"
        ]
        assert len(assistant_calls) == 1
        assert "metadata" in assistant_calls[0].kwargs
        assert assistant_calls[0].kwargs["metadata"]["rag_used"] is True
        assert len(assistant_calls[0].kwargs["metadata"]["sources"]) > 0

    @pytest.mark.asyncio
    async def test_chat_groups_by_session(self):
        """세션별로 메시지가 그룹핑되어야 한다"""
        from services.backend.app.services.chat_service import ChatService

        mock_llm = MagicMock()

        async def mock_stream(text, system_prompt=None, **kwargs):
            yield "응답"

        mock_llm.generate_stream = mock_stream

        mock_history = MagicMock()
        mock_history.add_message = AsyncMock()

        service = ChatService(
            llm_client=mock_llm,
            history_store=mock_history
        )

        # 세션 1
        async for event in service.process_message(
            session_id="session-1",
            message="테스트 1",
            use_rag=False
        ):
            pass

        # 세션 2
        async for event in service.process_message(
            session_id="session-2",
            message="테스트 2",
            use_rag=False
        ):
            pass

        calls = mock_history.add_message.call_args_list

        # 세션 ID가 올바르게 전달되었는지 확인
        session_ids = [c.kwargs.get("session_id") for c in calls]
        assert "session-1" in session_ids
        assert "session-2" in session_ids


class TestChatHistoryStore:
    """대화 기록 저장소 테스트"""

    def test_persistent_history_store_init(self):
        """PersistentHistoryStore가 초기화되어야 한다"""
        from services.backend.app.services.persistent_history import PersistentHistoryStore

        store = PersistentHistoryStore(database_url="mock://localhost/test")
        assert store is not None
        assert store.database_url == "mock://localhost/test"

    @pytest.mark.asyncio
    async def test_add_message_returns_id(self):
        """add_message가 메시지 ID를 반환해야 한다"""
        from services.backend.app.services.persistent_history import PersistentHistoryStore
        import uuid

        store = PersistentHistoryStore(database_url="mock://localhost/test")

        # Mock pool - conn.execute and conn.fetchval must be AsyncMock
        mock_conn = MagicMock()
        mock_conn.execute = AsyncMock()  # Phase 33: execute도 async
        mock_conn.fetchval = AsyncMock(return_value=123)  # UUID가 아닌 int ID 반환
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=None)

        mock_pool = MagicMock()
        mock_pool.acquire = MagicMock(return_value=mock_conn)
        store.pool = mock_pool

        # 유효한 UUID 사용
        session_id = str(uuid.uuid4())
        msg_id = await store.add_message(
            session_id=session_id,
            role="user",
            content="테스트 메시지"
        )

        assert msg_id == "123"

    @pytest.mark.asyncio
    async def test_get_session_messages(self):
        """세션의 메시지를 조회할 수 있어야 한다"""
        from services.backend.app.services.persistent_history import PersistentHistoryStore
        import uuid

        store = PersistentHistoryStore(database_url="mock://localhost/test")

        # 유효한 UUID 세션 ID
        session_id = str(uuid.uuid4())

        # Mock pool
        mock_conn = MagicMock()
        mock_rows = [
            {
                "id": 1,
                "session_id": session_id,
                "role": "user",
                "content": "안녕",
                "rag_sources": "[]",
                "created_at": "2025-12-08T10:00:00"
            },
            {
                "id": 2,
                "session_id": session_id,
                "role": "assistant",
                "content": "안녕하세요!",
                "rag_sources": "[]",
                "created_at": "2025-12-08T10:00:01"
            }
        ]
        mock_conn.fetch = AsyncMock(return_value=mock_rows)
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=None)

        mock_pool = MagicMock()
        mock_pool.acquire = MagicMock(return_value=mock_conn)
        store.pool = mock_pool

        messages = await store.get_session_messages(
            session_id=session_id,
            limit=100
        )

        assert len(messages) == 2
        assert messages[0]["role"] == "user"
        assert messages[1]["role"] == "assistant"
