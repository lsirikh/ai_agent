"""
Test Chat Integration

Phase 14.3.3: Chat Router Integration Tests
- Chat saves user message to DB
- Chat saves assistant message to DB
- Chat saves RAG context to DB
- Chat creates session if new
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import uuid


class TestChatSavesUserMessage:
    """Tests for chat saving user messages."""

    @pytest.mark.asyncio
    async def test_chat_saves_user_message(self):
        """
        Test that ChatService saves user messages to history store.

        Requirements:
        - Process a chat message
        - Verify user message is saved to history_store
        """
        from services.backend.app.services.chat_service import ChatService

        # Create mock history store
        mock_history = AsyncMock()
        mock_history.add_message = AsyncMock()

        # Create ChatService with mock history store (no LLM/RAG)
        service = ChatService(
            llm_client=None,
            rag_service=None,
            history_store=mock_history
        )

        session_id = f"test-session-{uuid.uuid4().hex[:8]}"
        user_message = "Hello, this is a test message"

        # Process message (consume all events)
        events = []
        async for event in service.process_message(
            session_id=session_id,
            message=user_message,
            use_rag=False
        ):
            events.append(event)

        # Verify user message was saved
        calls = mock_history.add_message.call_args_list
        assert len(calls) >= 1

        # Find the user message call
        user_call = next(
            (c for c in calls if c.kwargs.get("role") == "user"),
            None
        )
        assert user_call is not None
        assert user_call.kwargs["session_id"] == session_id
        assert user_call.kwargs["content"] == user_message


class TestChatSavesAssistantMessage:
    """Tests for chat saving assistant messages."""

    @pytest.mark.asyncio
    async def test_chat_saves_assistant_message(self):
        """
        Test that ChatService saves assistant messages to history store.

        Requirements:
        - Process a chat message
        - Verify assistant response is saved to history_store
        """
        from services.backend.app.services.chat_service import ChatService

        # Create mock history store
        mock_history = AsyncMock()
        mock_history.add_message = AsyncMock()

        # Create mock LLM client
        mock_llm = AsyncMock()

        async def mock_generate_stream(message, system_prompt=None, **kwargs):
            yield "This is "
            yield "a test "
            yield "response."

        mock_llm.generate_stream = mock_generate_stream

        # Create ChatService with mocks
        service = ChatService(
            llm_client=mock_llm,
            rag_service=None,
            history_store=mock_history
        )

        session_id = f"test-session-{uuid.uuid4().hex[:8]}"

        # Process message
        events = []
        async for event in service.process_message(
            session_id=session_id,
            message="Test question",
            use_rag=False
        ):
            events.append(event)

        # Verify assistant message was saved
        calls = mock_history.add_message.call_args_list
        assert len(calls) >= 2  # user + assistant

        # Find the assistant message call
        assistant_call = next(
            (c for c in calls if c.kwargs.get("role") == "assistant"),
            None
        )
        assert assistant_call is not None
        assert assistant_call.kwargs["session_id"] == session_id
        assert "This is a test response." in assistant_call.kwargs["content"]


class TestChatSavesRagContext:
    """Tests for chat saving RAG context."""

    @pytest.mark.asyncio
    async def test_chat_saves_rag_context(self):
        """
        Test that ChatService saves RAG context/sources with assistant message.

        Requirements:
        - Process a chat message with RAG enabled
        - Verify RAG sources are saved in metadata
        """
        from services.backend.app.services.chat_service import ChatService

        # Create mock history store
        mock_history = AsyncMock()
        mock_history.add_message = AsyncMock()

        # Create mock RAG service
        mock_rag = MagicMock()
        mock_rag.retrieve = AsyncMock(return_value=[
            {
                "content": "Relevant document content",
                "doc_id": "doc-123",
                "metadata": {"filename": "test.pdf"},
                "score": 0.95
            }
        ])

        # Create mock LLM
        mock_llm = AsyncMock()

        async def mock_generate_stream(message, system_prompt=None, **kwargs):
            yield "Based on the document, here is the answer."

        mock_llm.generate_stream = mock_generate_stream

        # Create ChatService with mocks
        service = ChatService(
            llm_client=mock_llm,
            rag_service=mock_rag,
            history_store=mock_history
        )

        session_id = f"test-session-{uuid.uuid4().hex[:8]}"

        # Process message with RAG
        events = []
        async for event in service.process_message(
            session_id=session_id,
            message="What does the document say?",
            use_rag=True
        ):
            events.append(event)

        # Verify RAG context event was emitted
        rag_events = [e for e in events if e["type"] == "rag_context"]
        assert len(rag_events) >= 1

        # Verify assistant message has RAG sources in metadata
        calls = mock_history.add_message.call_args_list
        assistant_call = next(
            (c for c in calls if c.kwargs.get("role") == "assistant"),
            None
        )
        assert assistant_call is not None
        assert "metadata" in assistant_call.kwargs
        assert assistant_call.kwargs["metadata"]["rag_used"] is True
        assert len(assistant_call.kwargs["metadata"]["sources"]) > 0


class TestChatCreatesSessionIfNew:
    """Tests for chat creating sessions automatically."""

    @pytest.mark.asyncio
    async def test_chat_creates_session_if_new(self):
        """
        Test that chat creates a new session ID if none provided.

        Requirements:
        - Send chat request without session_id
        - Verify a new session_id is generated
        - Verify messages are saved with the generated session_id
        """
        from services.backend.app.services.chat_service import ChatService

        # Create mock history store
        mock_history = AsyncMock()
        mock_history.add_message = AsyncMock()

        # Create ChatService
        service = ChatService(
            llm_client=None,
            rag_service=None,
            history_store=mock_history
        )

        # Process message with a session_id
        session_id = f"new-session-{uuid.uuid4().hex[:8]}"

        events = []
        async for event in service.process_message(
            session_id=session_id,
            message="Hello!",
            use_rag=False
        ):
            events.append(event)

        # Verify session_id is in all events
        for event in events:
            assert event["session_id"] == session_id

        # Verify messages were saved with session_id
        calls = mock_history.add_message.call_args_list
        for call in calls:
            assert call.kwargs["session_id"] == session_id

    @pytest.mark.asyncio
    async def test_chat_router_generates_session_id(self):
        """
        Test that the chat router generates a session_id when not provided.
        """
        from services.backend.app.main import app
        from services.backend.app.routes import chat as chat_module
        from httpx import AsyncClient, ASGITransport

        # Reset services to ensure clean state
        chat_module.reset_services()

        # Mock the chat service
        mock_service = AsyncMock()

        async def mock_process(*args, **kwargs):
            session_id = kwargs.get("session_id", "unknown")
            yield {"type": "token", "content": "Hi!", "session_id": session_id, "sources": []}
            yield {"type": "complete", "content": "Hi!", "session_id": session_id, "sources": []}

        mock_service.process_message = mock_process

        with patch.object(chat_module, "get_chat_service", return_value=mock_service):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                # Send message without session_id
                response = await client.post(
                    "/api/chat/message",
                    json={
                        "message": "Hello!"
                        # No session_id provided
                    }
                )

                assert response.status_code == 200

                # Parse SSE events
                content = response.text
                assert "session_id" in content
                # Session ID should be a UUID-like string (not None or empty)
                assert '"session_id": "' in content or '"session_id":"' in content
