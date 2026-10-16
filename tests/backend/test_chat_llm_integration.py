"""
Backend API - Chat LLM Integration Tests

Phase 11.1: chat.py가 실제 LLMClient를 사용하는지 테스트
Phase 11.2: RAG 컨텍스트 연동 테스트
"""
import json
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from fastapi.testclient import TestClient


class TestChatUsesLLMClient:
    """chat.py가 LLMClient를 사용하는지 테스트"""

    def test_chat_uses_llm_client(self):
        """
        chat.py가 ChatService를 통해 LLMClient를 사용해야 함.
        LLMClient 없이도 ChatService는 동작하며, echo 패턴이 아닌 응답을 반환해야 함.
        """
        from services.backend.app.main import app
        client = TestClient(app)

        response = client.post(
            "/api/chat/message",
            json={
                "message": "안녕하세요",
                "use_rag": False
            }
        )

        assert response.status_code == 200

        # SSE 스트리밍 응답 파싱
        content = response.text

        # echo 응답이 아닌 ChatService 응답이어야 함
        # ChatService는 LLM 없이도 "안녕하세요! '{message}'에 대해 말씀해 주셨네요." 형식 사용
        # 이전 echo: "안녕하세요! '{message}'라고 말씀하셨네요."
        assert "라고 말씀하셨네요" not in content, \
            "chat.py가 아직 echo 응답을 사용함. ChatService 연동 필요"


class TestChatStreamsLLMTokens:
    """chat.py가 ChatService를 통해 응답 스트리밍하는지 테스트"""

    def test_chat_streams_response(self):
        """SSE 응답이 스트리밍되어야 함"""
        from services.backend.app.main import app
        client = TestClient(app)

        response = client.post(
            "/api/chat/message",
            json={
                "message": "테스트 메시지",
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

        # 이벤트가 있어야 함 (token 또는 complete)
        assert len(events) > 0, "SSE 이벤트가 있어야 함"

        # 완료 이벤트가 있어야 함
        complete_events = [e for e in events if e.get("type") == "complete"]
        assert len(complete_events) == 1, "완료 이벤트가 하나 있어야 함"

        # 세션 ID가 있어야 함
        assert complete_events[0].get("session_id"), "세션 ID가 있어야 함"


class TestWebSocketUsesLLMClient:
    """WebSocket 채팅이 ChatService를 사용하는지 테스트"""

    def test_websocket_uses_chat_service(self):
        """WebSocket 채팅도 ChatService를 통해 응답해야 함"""
        from services.backend.app.main import app
        client = TestClient(app)

        with client.websocket_connect("/api/chat/ws/test-session-123") as websocket:
            # 메시지 전송
            websocket.send_json({
                "type": "message",
                "content": "안녕하세요",
                "use_rag": False
            })

            # 응답 수신 (타임아웃 방지를 위해 제한적으로 수집)
            messages = []
            import time
            start_time = time.time()
            max_wait = 5  # 최대 5초 대기

            while time.time() - start_time < max_wait:
                try:
                    msg = websocket.receive_json()
                    messages.append(msg)
                    if msg.get("type") == "complete":
                        break
                except Exception:
                    break

            # 완료 메시지가 있어야 함
            complete_msg = next((m for m in messages if m.get("type") == "complete"), None)
            assert complete_msg is not None, "완료 메시지가 있어야 함"

            # ChatService 응답이어야 함 (echo 패턴이 없어야 함)
            content = complete_msg.get("content", "")
            assert "라고 말씀하셨네요" not in content, \
                "WebSocket도 아직 echo 응답 사용. ChatService 연동 필요"


# =============================================================================
# Phase 11.2: RAG 컨텍스트 연동 테스트
# =============================================================================

class TestChatRetrievesRAGContext:
    """chat.py가 RAG 컨텍스트를 검색하는지 테스트"""

    def test_chat_retrieves_rag_context(self):
        """
        use_rag=True일 때 RAGService.retrieve가 호출되어야 함.
        RAGService가 연결되어 있으면 rag_context 이벤트가 발생해야 함.
        """
        from services.backend.app.routes.chat import reset_services
        reset_services()

        # Mock RAGService 생성
        mock_rag_service = MagicMock()
        mock_rag_service.retrieve.return_value = [
            {
                "content": "테스트 문서 내용입니다.",
                "score": 0.95,
                "metadata": {"filename": "test.pdf"},
                "doc_id": "doc-123"
            }
        ]

        # ChatService에 mock RAG 주입
        with patch('services.backend.app.routes.chat.get_rag_service') as mock_get_rag:
            mock_get_rag.return_value = mock_rag_service

            from services.backend.app.main import app
            client = TestClient(app)

            response = client.post(
                "/api/chat/message",
                json={
                    "message": "테스트 질문",
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

            # RAG 컨텍스트 이벤트가 있어야 함
            rag_events = [e for e in events if e.get("type") == "rag_context"]
            assert len(rag_events) == 1, \
                "RAGService가 연결되면 rag_context 이벤트가 발생해야 함"

            # RAGService.retrieve가 호출되었어야 함
            mock_rag_service.retrieve.assert_called_once()


class TestChatInjectsRAGToPrompt:
    """chat.py가 RAG 컨텍스트를 프롬프트에 주입하는지 테스트"""

    def test_chat_injects_rag_to_prompt(self):
        """
        RAG 컨텍스트가 있으면 시스템 프롬프트에 포함되어야 함.
        """
        from services.backend.app.services.chat_service import ChatService

        # RAG 컨텍스트가 있을 때 시스템 프롬프트 생성
        chat_service = ChatService()
        rag_context = "관련 문서: AI 에이전트는 자율적으로 작업을 수행합니다."

        system_prompt = chat_service._build_system_prompt(rag_context)

        # RAG 컨텍스트가 시스템 프롬프트에 포함되어야 함
        assert rag_context in system_prompt, \
            "RAG 컨텍스트가 시스템 프롬프트에 포함되어야 함"
        assert "관련 문서" in system_prompt, \
            "문서 관련 안내가 시스템 프롬프트에 있어야 함"


class TestChatReturnsRAGSources:
    """chat.py가 RAG 출처를 반환하는지 테스트"""

    def test_chat_returns_rag_sources(self):
        """
        RAG 검색 결과의 출처가 complete 이벤트에 포함되어야 함.
        """
        from services.backend.app.routes.chat import reset_services
        reset_services()

        # Mock RAGService 생성
        mock_rag_service = MagicMock()
        mock_rag_service.retrieve.return_value = [
            {
                "content": "EdgeVoice는 엣지 AI 음성 시스템입니다.",
                "score": 0.92,
                "metadata": {"filename": "edgevoice-manual.pdf"},
                "doc_id": "doc-456"
            },
            {
                "content": "TTS 엔진은 음성을 합성합니다.",
                "score": 0.85,
                "metadata": {"filename": "tts-guide.pdf"},
                "doc_id": "doc-789"
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

            # complete 이벤트 찾기
            complete_events = [e for e in events if e.get("type") == "complete"]
            assert len(complete_events) == 1, "complete 이벤트가 있어야 함"

            # sources 필드에 RAG 출처가 있어야 함
            sources = complete_events[0].get("sources", [])
            assert len(sources) == 2, "2개의 RAG 출처가 있어야 함"

            # 출처 정보 확인
            filenames = [s.get("filename") for s in sources]
            assert "edgevoice-manual.pdf" in filenames, \
                "edgevoice-manual.pdf가 출처에 있어야 함"
            assert "tts-guide.pdf" in filenames, \
                "tts-guide.pdf가 출처에 있어야 함"


# =============================================================================
# Phase 11.3: History 자동 저장 테스트
# =============================================================================

class TestChatSavesToHistory:
    """chat.py가 대화를 History에 저장하는지 테스트"""

    def test_chat_saves_to_history(self):
        """
        채팅 완료 후 대화가 History에 저장되어야 함.
        """
        from services.backend.app.routes.chat import reset_services
        reset_services()

        # Mock HistoryStore 생성
        mock_history_store = MagicMock()
        mock_history_store.add_message = AsyncMock(return_value="msg-123")

        with patch('services.backend.app.routes.chat.get_history_store') as mock_get_history:
            mock_get_history.return_value = mock_history_store

            from services.backend.app.main import app
            client = TestClient(app)

            response = client.post(
                "/api/chat/message",
                json={
                    "message": "안녕하세요",
                    "use_rag": False
                }
            )

            assert response.status_code == 200

            # History에 저장 호출 확인 (user + assistant = 2번)
            assert mock_history_store.add_message.call_count == 2, \
                "사용자 메시지와 AI 응답이 저장되어야 함"

            # 첫 번째 호출: 사용자 메시지
            first_call = mock_history_store.add_message.call_args_list[0]
            assert first_call.kwargs.get("role") == "user", \
                "첫 번째 저장은 사용자 메시지여야 함"

            # 두 번째 호출: AI 응답
            second_call = mock_history_store.add_message.call_args_list[1]
            assert second_call.kwargs.get("role") == "assistant", \
                "두 번째 저장은 AI 응답이어야 함"


class TestChatHistoryIncludesMetadata:
    """chat.py가 RAG 메타데이터를 History에 포함하는지 테스트"""

    def test_chat_history_includes_metadata(self):
        """
        RAG 출처 정보가 History 메타데이터에 포함되어야 함.
        """
        from services.backend.app.routes.chat import reset_services
        reset_services()

        # Mock RAGService
        mock_rag_service = MagicMock()
        mock_rag_service.retrieve.return_value = [
            {
                "content": "테스트 문서",
                "score": 0.9,
                "metadata": {"filename": "test.pdf"},
                "doc_id": "doc-1"
            }
        ]

        # Mock HistoryStore
        mock_history_store = MagicMock()
        mock_history_store.add_message = AsyncMock(return_value="msg-456")

        with patch('services.backend.app.routes.chat.get_rag_service') as mock_get_rag, \
             patch('services.backend.app.routes.chat.get_history_store') as mock_get_history:
            mock_get_rag.return_value = mock_rag_service
            mock_get_history.return_value = mock_history_store

            from services.backend.app.main import app
            client = TestClient(app)

            response = client.post(
                "/api/chat/message",
                json={
                    "message": "테스트 질문",
                    "use_rag": True
                }
            )

            assert response.status_code == 200

            # AI 응답 저장 시 메타데이터 확인
            assistant_call = mock_history_store.add_message.call_args_list[1]
            metadata = assistant_call.kwargs.get("metadata", {})

            assert metadata.get("rag_used") is True, \
                "RAG 사용 여부가 메타데이터에 있어야 함"
            assert len(metadata.get("sources", [])) > 0, \
                "RAG 출처가 메타데이터에 있어야 함"


# =============================================================================
# Phase 11.4: Dashboard Chat API 통합 테스트
# =============================================================================

class TestDashboardChatUsesAPI:
    """Dashboard Chat이 실제 API를 사용하는지 테스트"""

    def test_dashboard_chat_api_exists(self):
        """
        Dashboard가 사용하는 /api/chat/message 엔드포인트가 존재해야 함.
        """
        from services.backend.app.main import app
        client = TestClient(app)

        response = client.post(
            "/api/chat/message",
            json={
                "message": "테스트",
                "use_rag": False
            }
        )

        assert response.status_code == 200, \
            "Dashboard용 /api/chat/message 엔드포인트가 있어야 함"

    def test_dashboard_chat_returns_sse_stream(self):
        """
        Chat API가 SSE 스트리밍 응답을 반환해야 함.
        """
        from services.backend.app.main import app
        client = TestClient(app)

        response = client.post(
            "/api/chat/message",
            json={
                "message": "Hello",
                "use_rag": False
            }
        )

        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", ""), \
            "SSE 스트리밍 응답이어야 함"

        # SSE 포맷 확인
        assert "data: " in response.text, \
            "SSE data: 프리픽스가 있어야 함"


class TestDashboardChatStreamsResponse:
    """Dashboard Chat이 응답을 스트리밍하는지 테스트"""

    def test_dashboard_chat_streams_tokens(self):
        """
        Chat 응답이 token 이벤트로 스트리밍되어야 함.
        """
        from services.backend.app.main import app
        client = TestClient(app)

        response = client.post(
            "/api/chat/message",
            json={
                "message": "안녕",
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

        # token 이벤트가 있어야 함
        token_events = [e for e in events if e.get("type") == "token"]
        assert len(token_events) >= 1, "token 이벤트가 있어야 함"

        # complete 이벤트가 있어야 함
        complete_events = [e for e in events if e.get("type") == "complete"]
        assert len(complete_events) == 1, "complete 이벤트가 있어야 함"

        # session_id가 있어야 함
        assert complete_events[0].get("session_id"), \
            "Dashboard가 세션 관리를 위한 session_id가 필요함"
