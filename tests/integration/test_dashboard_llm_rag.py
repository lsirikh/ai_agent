"""
Integration Tests - Dashboard LLM/RAG Integration

Phase 11.5: Dashboard Chat이 LLM, RAG, History와 완전히 통합되었는지 테스트
"""
import json
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from fastapi.testclient import TestClient


class TestFullChatWithRealLLM:
    """실제 LLM과 Chat 통합 테스트"""

    def test_full_chat_with_real_llm(self):
        """
        Chat API가 실제 LLMClient를 통해 응답을 생성해야 함.
        LLM이 없으면 ChatService의 기본 응답 사용.
        """
        from services.backend.app.routes.chat import reset_services
        reset_services()

        from services.backend.app.main import app
        client = TestClient(app)

        response = client.post(
            "/api/chat/message",
            json={
                "message": "안녕하세요, 테스트입니다.",
                "use_rag": False
            }
        )

        assert response.status_code == 200

        # SSE 이벤트 파싱
        events = []
        for line in response.text.split("\n"):
            if line.startswith("data: "):
                try:
                    event = json.loads(line[6:])
                    events.append(event)
                except json.JSONDecodeError:
                    pass

        # 응답이 있어야 함
        assert len(events) > 0, "응답 이벤트가 있어야 함"

        # complete 이벤트 확인
        complete_events = [e for e in events if e.get("type") == "complete"]
        assert len(complete_events) == 1, "complete 이벤트가 있어야 함"

        # 응답 내용이 있어야 함
        content = complete_events[0].get("content", "")
        assert len(content) > 0, "응답 내용이 있어야 함"


class TestRAGContextInLLMResponse:
    """RAG 컨텍스트가 LLM 응답에 포함되는지 테스트"""

    def test_rag_context_in_llm_response(self):
        """
        RAG 검색 결과가 LLM 프롬프트에 주입되어야 함.
        """
        from services.backend.app.routes.chat import reset_services
        reset_services()

        # Mock RAGService
        mock_rag_service = MagicMock()
        mock_rag_service.retrieve.return_value = [
            {
                "content": "EdgeVoice는 엣지 디바이스용 AI 음성 비서입니다.",
                "score": 0.95,
                "metadata": {"filename": "readme.md"},
                "doc_id": "doc-001"
            }
        ]

        with patch('services.backend.app.routes.chat.get_rag_service') as mock_get_rag:
            mock_get_rag.return_value = mock_rag_service

            from services.backend.app.main import app
            client = TestClient(app)

            response = client.post(
                "/api/chat/message",
                json={
                    "message": "EdgeVoice가 뭐야?",
                    "use_rag": True
                }
            )

            assert response.status_code == 200

            # SSE 이벤트 파싱
            events = []
            for line in response.text.split("\n"):
                if line.startswith("data: "):
                    try:
                        event = json.loads(line[6:])
                        events.append(event)
                    except json.JSONDecodeError:
                        pass

            # rag_context 이벤트가 있어야 함
            rag_events = [e for e in events if e.get("type") == "rag_context"]
            assert len(rag_events) == 1, "RAG 컨텍스트 이벤트가 있어야 함"

            # RAG 컨텍스트에 문서 내용이 포함되어야 함
            rag_content = rag_events[0].get("content", "")
            assert "EdgeVoice" in rag_content or "엣지" in rag_content, \
                "RAG 컨텍스트에 문서 내용이 있어야 함"

            # complete 이벤트에 sources가 있어야 함
            complete_events = [e for e in events if e.get("type") == "complete"]
            assert len(complete_events) == 1
            sources = complete_events[0].get("sources", [])
            assert len(sources) > 0, "출처 정보가 있어야 함"


class TestHistoryPersistedAfterChat:
    """채팅 후 History가 저장되는지 테스트"""

    def test_history_persisted_after_chat(self):
        """
        채팅 완료 후 대화 내용이 History에 저장되어야 함.
        """
        from services.backend.app.routes.chat import reset_services
        reset_services()

        # Mock HistoryStore
        mock_history_store = MagicMock()
        mock_history_store.add_message = AsyncMock(return_value="msg-123")

        with patch('services.backend.app.routes.chat.get_history_store') as mock_get_history:
            mock_get_history.return_value = mock_history_store

            from services.backend.app.main import app
            client = TestClient(app)

            response = client.post(
                "/api/chat/message",
                json={
                    "message": "테스트 메시지입니다.",
                    "session_id": "test-session-001",
                    "use_rag": False
                }
            )

            assert response.status_code == 200

            # History 저장이 호출되어야 함
            assert mock_history_store.add_message.call_count == 2, \
                "사용자 메시지와 AI 응답 모두 저장되어야 함"

            # 세션 ID가 올바르게 전달되어야 함
            calls = mock_history_store.add_message.call_args_list
            for call in calls:
                assert call.kwargs.get("session_id") == "test-session-001", \
                    "세션 ID가 올바르게 전달되어야 함"

            # 역할이 올바르게 저장되어야 함
            roles = [call.kwargs.get("role") for call in calls]
            assert "user" in roles, "사용자 메시지가 저장되어야 함"
            assert "assistant" in roles, "AI 응답이 저장되어야 함"


class TestEndToEndChatFlow:
    """전체 채팅 흐름 E2E 테스트"""

    def test_end_to_end_chat_flow(self):
        """
        전체 채팅 흐름: 메시지 -> RAG 검색 -> LLM 응답 -> History 저장
        """
        from services.backend.app.routes.chat import reset_services
        reset_services()

        # Mock RAGService
        mock_rag_service = MagicMock()
        mock_rag_service.retrieve.return_value = [
            {
                "content": "테스트 문서 내용",
                "score": 0.9,
                "metadata": {"filename": "test.pdf"},
                "doc_id": "doc-test"
            }
        ]

        # Mock HistoryStore
        mock_history_store = MagicMock()
        mock_history_store.add_message = AsyncMock(return_value="msg-e2e")

        with patch('services.backend.app.routes.chat.get_rag_service') as mock_get_rag, \
             patch('services.backend.app.routes.chat.get_history_store') as mock_get_history:
            mock_get_rag.return_value = mock_rag_service
            mock_get_history.return_value = mock_history_store

            from services.backend.app.main import app
            client = TestClient(app)

            response = client.post(
                "/api/chat/message",
                json={
                    "message": "E2E 테스트",
                    "use_rag": True
                }
            )

            assert response.status_code == 200

            # SSE 이벤트 파싱
            events = []
            event_types = []
            for line in response.text.split("\n"):
                if line.startswith("data: "):
                    try:
                        event = json.loads(line[6:])
                        events.append(event)
                        event_types.append(event.get("type"))
                    except json.JSONDecodeError:
                        pass

            # 이벤트 순서 확인: rag_context -> token(s) -> complete
            assert "rag_context" in event_types, "RAG 컨텍스트 이벤트가 있어야 함"
            assert "token" in event_types, "토큰 이벤트가 있어야 함"
            assert "complete" in event_types, "완료 이벤트가 있어야 함"

            # RAG 서비스가 호출되었어야 함
            mock_rag_service.retrieve.assert_called_once()

            # History가 저장되었어야 함
            assert mock_history_store.add_message.call_count == 2
