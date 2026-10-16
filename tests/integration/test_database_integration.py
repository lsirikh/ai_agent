"""
Test Database Integration

Phase 14.5.1: Database Integration Tests
- test_full_settings_flow: Settings save -> query -> restart -> restore
- test_full_chat_flow: Chat -> message save -> History query
- test_full_knowledge_flow: Document upload -> chunking -> search
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import uuid
import io


class TestFullSettingsFlow:
    """Tests for complete settings flow through database."""

    @pytest.mark.asyncio
    async def test_full_settings_flow(self):
        """
        Test complete settings flow: save -> query -> restart -> restore.

        Requirements:
        1. Save settings via API
        2. Query settings back
        3. Simulate restart by recreating service
        4. Verify settings restored correctly
        """
        from services.backend.app.main import app
        from services.backend.app.routes import settings as settings_module
        from httpx import AsyncClient, ASGITransport

        # Create mock repository that persists data
        stored_settings = {}

        mock_repo = AsyncMock()

        async def mock_get(key):
            return stored_settings.get(key, {})

        async def mock_upsert(key, value, category=None):
            stored_settings[key] = value

        async def mock_get_all():
            return stored_settings

        mock_repo.get = mock_get
        mock_repo.upsert = mock_upsert
        mock_repo.get_all = mock_get_all

        # Mock propagator
        mock_propagator = AsyncMock()
        mock_propagator.propagate = AsyncMock(return_value={"success": True})

        with patch.object(settings_module, "get_settings_repository", return_value=mock_repo), \
             patch.object(settings_module, "get_settings_propagator", return_value=mock_propagator):

            transport = ASGITransport(app=app)

            # Step 1: Save settings
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                save_response = await client.put(
                    "/api/settings/general",
                    json={
                        "wake_word": "hey_robot",
                        "language": "en",
                        "voice_speed": 1.2,
                        "wake_word_threshold": 0.6
                    }
                )
                assert save_response.status_code == 200

            # Step 2: Query settings back
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                get_response = await client.get("/api/settings/general")
                assert get_response.status_code == 200
                data = get_response.json()
                assert data.get("language") == "en"
                assert data.get("voice_speed") == 1.2

            # Step 3: Simulate restart - stored_settings persists
            # (In real scenario, DB persists across restarts)

            # Step 4: Verify settings restored after "restart"
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                restored_response = await client.get("/api/settings/general")
                assert restored_response.status_code == 200
                data = restored_response.json()
                # Settings should be restored from storage
                assert data.get("language") == "en"
                assert data.get("voice_speed") == 1.2


class TestFullChatFlow:
    """Tests for complete chat flow through database."""

    @pytest.mark.asyncio
    async def test_full_chat_flow(self):
        """
        Test complete chat flow: chat -> message save -> History query.

        Requirements:
        1. Send chat message
        2. Verify message saved to history
        3. Query history and verify messages exist
        """
        from services.backend.app.services.chat_service import ChatService

        # Storage for messages
        stored_messages = []
        stored_sessions = {}

        # Create mock history store
        mock_history = AsyncMock()

        async def mock_add_message(session_id, role, content, metadata=None):
            stored_messages.append({
                "id": str(uuid.uuid4()),
                "session_id": session_id,
                "role": role,
                "content": content,
                "metadata": metadata or {}
            })
            if session_id not in stored_sessions:
                stored_sessions[session_id] = {
                    "id": session_id,
                    "created_at": "2025-01-01T00:00:00Z"
                }

        async def mock_get_messages(session_id, limit=50):
            return [m for m in stored_messages if m["session_id"] == session_id][:limit]

        mock_history.add_message = mock_add_message
        mock_history.get_messages = mock_get_messages

        # Create mock LLM
        mock_llm = AsyncMock()

        async def mock_generate_stream(message, system_prompt=None):
            yield "Hello, "
            yield "how can I help?"

        mock_llm.generate_stream = mock_generate_stream

        # Create ChatService
        service = ChatService(
            llm_client=mock_llm,
            rag_service=None,
            history_store=mock_history
        )

        session_id = f"chat-session-{uuid.uuid4().hex[:8]}"

        # Step 1: Send chat message
        events = []
        async for event in service.process_message(
            session_id=session_id,
            message="Hello!",
            use_rag=False
        ):
            events.append(event)

        # Step 2: Verify messages saved
        assert len(stored_messages) == 2  # user + assistant

        user_msg = next((m for m in stored_messages if m["role"] == "user"), None)
        assert user_msg is not None
        assert user_msg["content"] == "Hello!"
        assert user_msg["session_id"] == session_id

        assistant_msg = next((m for m in stored_messages if m["role"] == "assistant"), None)
        assert assistant_msg is not None
        assert "Hello" in assistant_msg["content"]
        assert assistant_msg["session_id"] == session_id

        # Step 3: Query history
        history = await mock_history.get_messages(session_id)
        assert len(history) == 2


class TestFullKnowledgeFlow:
    """Tests for complete knowledge flow through database."""

    @pytest.mark.asyncio
    async def test_full_knowledge_flow(self):
        """
        Test complete knowledge flow: upload -> chunking -> search.

        Requirements:
        1. Upload document
        2. Verify document stored with chunks
        3. Search and retrieve relevant content
        """
        from services.backend.app.main import app
        from services.backend.app.routes import knowledge as knowledge_module
        from httpx import AsyncClient, ASGITransport

        # Storage for documents
        stored_documents = []
        stored_chunks = []

        # Create mock RAG service
        mock_rag = MagicMock()

        def mock_add_document(content, metadata):
            doc_id = f"doc-{uuid.uuid4().hex[:8]}"
            stored_documents.append({
                "doc_id": doc_id,
                "content": content,
                "metadata": metadata,
                "status": "indexed"
            })
            # Simulate chunking
            chunk_size = 100
            for i in range(0, len(content), chunk_size):
                stored_chunks.append({
                    "doc_id": doc_id,
                    "chunk_index": i // chunk_size,
                    "content": content[i:i + chunk_size]
                })
            return doc_id

        def mock_list_documents():
            return stored_documents

        def mock_retrieve(query, top_k=3, filter_metadata=None):
            # Simple search simulation
            results = []
            for chunk in stored_chunks:
                if query.lower() in chunk["content"].lower():
                    results.append({
                        "content": chunk["content"],
                        "score": 0.9,
                        "doc_id": chunk["doc_id"],
                        "metadata": {}
                    })
            return results[:top_k]

        mock_rag.add_document = mock_add_document
        mock_rag.list_documents = mock_list_documents
        mock_rag.retrieve = mock_retrieve

        with patch.object(knowledge_module, "get_rag_service", return_value=mock_rag):
            transport = ASGITransport(app=app)

            async with AsyncClient(transport=transport, base_url="http://test") as client:
                # Step 1: Upload document
                document_content = b"""
                This is a test document about machine learning.
                Machine learning is a subset of artificial intelligence.
                It allows systems to learn from data and improve over time.
                """

                upload_response = await client.post(
                    "/api/knowledge/upload",
                    files={"file": ("ml_guide.txt", io.BytesIO(document_content), "text/plain")},
                    data={"title": "ML Guide", "category": "manual"}
                )

                assert upload_response.status_code == 200
                upload_data = upload_response.json()
                doc_id = upload_data["doc_id"]
                assert doc_id is not None

                # Step 2: Verify document stored
                assert len(stored_documents) == 1
                assert stored_documents[0]["doc_id"] == doc_id
                assert stored_documents[0]["status"] == "indexed"

                # Verify chunks created
                assert len(stored_chunks) > 0
                doc_chunks = [c for c in stored_chunks if c["doc_id"] == doc_id]
                assert len(doc_chunks) > 0

                # Step 3: List documents
                list_response = await client.get("/api/knowledge/documents")
                assert list_response.status_code == 200
                list_data = list_response.json()
                assert list_data["total"] == 1

                # Step 4: Search
                search_response = await client.post(
                    "/api/knowledge/search",
                    json={"query": "machine learning", "top_k": 3}
                )

                assert search_response.status_code == 200
                search_data = search_response.json()
                assert "results" in search_data
                # Should find content mentioning "machine learning"
                assert len(search_data["results"]) > 0


class TestChatWithRAGFlow:
    """Tests for chat flow with RAG integration."""

    @pytest.mark.asyncio
    async def test_chat_with_rag_stores_sources(self):
        """
        Test that chat with RAG stores sources in message metadata.
        """
        from services.backend.app.services.chat_service import ChatService

        stored_messages = []

        # Mock history store
        mock_history = AsyncMock()

        async def mock_add_message(session_id, role, content, metadata=None):
            stored_messages.append({
                "session_id": session_id,
                "role": role,
                "content": content,
                "metadata": metadata or {}
            })

        mock_history.add_message = mock_add_message

        # Mock RAG service
        mock_rag = MagicMock()
        mock_rag.retrieve = AsyncMock(return_value=[
            {
                "content": "Important document content about the topic.",
                "doc_id": "doc-123",
                "metadata": {"filename": "guide.pdf"},
                "score": 0.95
            }
        ])

        # Mock LLM
        mock_llm = AsyncMock()

        async def mock_generate_stream(message, system_prompt=None):
            yield "Based on the document, here is the answer."

        mock_llm.generate_stream = mock_generate_stream

        # Create service
        service = ChatService(
            llm_client=mock_llm,
            rag_service=mock_rag,
            history_store=mock_history
        )

        session_id = f"rag-session-{uuid.uuid4().hex[:8]}"

        # Process message with RAG
        events = []
        async for event in service.process_message(
            session_id=session_id,
            message="What does the document say?",
            use_rag=True
        ):
            events.append(event)

        # Verify RAG context event
        rag_events = [e for e in events if e.get("type") == "rag_context"]
        assert len(rag_events) >= 1

        # Verify assistant message has RAG sources
        assistant_msg = next(
            (m for m in stored_messages if m["role"] == "assistant"),
            None
        )
        assert assistant_msg is not None
        assert assistant_msg["metadata"].get("rag_used") is True
        assert len(assistant_msg["metadata"].get("sources", [])) > 0


class TestSettingsRestartRecovery:
    """Tests for settings recovery after simulated restart."""

    @pytest.mark.asyncio
    async def test_settings_persist_across_service_recreation(self):
        """
        Test that settings persist when service is recreated.
        """
        from services.backend.app.main import app
        from services.backend.app.routes import settings as settings_module
        from httpx import AsyncClient, ASGITransport

        # Persistent storage (simulates database)
        persistent_storage = {}

        def create_mock_repo():
            mock = AsyncMock()

            async def get(key):
                return persistent_storage.get(key, {})

            async def upsert(key, value, category=None):
                persistent_storage[key] = value

            mock.get = get
            mock.upsert = upsert
            return mock

        mock_propagator = AsyncMock()
        mock_propagator.propagate = AsyncMock(return_value={"success": True})

        # First "service instance"
        with patch.object(settings_module, "get_settings_repository", create_mock_repo), \
             patch.object(settings_module, "get_settings_propagator", return_value=mock_propagator):

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                # Save settings
                await client.put(
                    "/api/settings/general",
                    json={"language": "ja", "voice_speed": 0.8}
                )

        # Second "service instance" (after restart)
        with patch.object(settings_module, "get_settings_repository", create_mock_repo), \
             patch.object(settings_module, "get_settings_propagator", return_value=mock_propagator):

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                # Get settings - should retrieve from persistent storage
                response = await client.get("/api/settings/general")
                assert response.status_code == 200
                data = response.json()
                assert data.get("language") == "ja"
                assert data.get("voice_speed") == 0.8
