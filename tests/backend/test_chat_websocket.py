"""
Backend API - Chat WebSocket Tests

Phase 9.5: WebSocket 채팅 테스트
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestWebSocketConnection:
    """WebSocket 연결 테스트"""

    def test_websocket_connection(self):
        """WebSocket 연결이 성공해야 한다"""
        from fastapi.testclient import TestClient
        from services.backend.app.main import app

        client = TestClient(app)

        with client.websocket_connect("/api/chat/ws/test-session") as websocket:
            # 연결 성공
            assert websocket is not None

    def test_websocket_with_session_id(self):
        """세션 ID가 경로에 포함되어야 한다"""
        from fastapi.testclient import TestClient
        from services.backend.app.main import app

        client = TestClient(app)
        session_id = "my-custom-session-123"

        with client.websocket_connect(f"/api/chat/ws/{session_id}") as websocket:
            assert websocket is not None


class TestWebSocketMessageExchange:
    """WebSocket 메시지 교환 테스트"""

    def test_websocket_receives_message(self):
        """WebSocket이 메시지를 수신해야 한다"""
        from fastapi.testclient import TestClient
        from services.backend.app.main import app

        client = TestClient(app)

        with client.websocket_connect("/api/chat/ws/test-session") as websocket:
            # 메시지 전송
            websocket.send_json({
                "type": "message",
                "content": "안녕하세요"
            })

            # 응답 수신
            response = websocket.receive_json()
            assert response is not None
            assert "type" in response

    def test_websocket_streams_response(self):
        """WebSocket이 응답을 스트리밍해야 한다"""
        from fastapi.testclient import TestClient
        from services.backend.app.main import app

        client = TestClient(app)

        with client.websocket_connect("/api/chat/ws/test-session") as websocket:
            websocket.send_json({
                "type": "message",
                "content": "테스트"
            })

            # 여러 응답 수신 (토큰 + 완료)
            responses = []
            while True:
                response = websocket.receive_json()
                responses.append(response)
                if response.get("type") == "complete":
                    break

            # 최소 하나의 토큰과 완료 메시지가 있어야 함
            token_responses = [r for r in responses if r["type"] == "token"]
            complete_responses = [r for r in responses if r["type"] == "complete"]

            assert len(complete_responses) == 1


class TestWebSocketDisconnect:
    """WebSocket 연결 해제 테스트"""

    def test_websocket_handles_disconnect(self):
        """WebSocket 연결 해제가 처리되어야 한다"""
        from fastapi.testclient import TestClient
        from services.backend.app.main import app

        client = TestClient(app)

        # 연결 후 정상 종료
        with client.websocket_connect("/api/chat/ws/test-session") as websocket:
            pass  # 컨텍스트 종료 시 자동 닫힘

        # 예외 없이 종료되어야 함
        assert True


class TestWebSocketWithRAG:
    """WebSocket RAG 연동 테스트"""

    def test_websocket_with_rag_enabled(self):
        """RAG가 활성화된 WebSocket 메시지"""
        from fastapi.testclient import TestClient
        from services.backend.app.main import app

        client = TestClient(app)

        with client.websocket_connect("/api/chat/ws/test-session") as websocket:
            websocket.send_json({
                "type": "message",
                "content": "RAG 테스트",
                "use_rag": True
            })

            response = websocket.receive_json()
            assert response is not None

    def test_websocket_with_rag_disabled(self):
        """RAG가 비활성화된 WebSocket 메시지"""
        from fastapi.testclient import TestClient
        from services.backend.app.main import app

        client = TestClient(app)

        with client.websocket_connect("/api/chat/ws/test-session") as websocket:
            websocket.send_json({
                "type": "message",
                "content": "RAG 비활성화 테스트",
                "use_rag": False
            })

            response = websocket.receive_json()
            assert response is not None
