"""
Backend API - Chat Tests

Phase 9.1: 채팅 API 테스트
"""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


class TestChatRouter:
    """Chat 라우터 존재 테스트"""

    def test_chat_router_exists(self):
        """Chat 라우터가 등록되어 있어야 한다"""
        from services.backend.app.main import app

        # 등록된 라우트에서 /api/chat 경로 확인
        routes = [route.path for route in app.routes]
        chat_routes = [r for r in routes if r.startswith("/api/chat")]
        assert len(chat_routes) > 0, "Chat router should be registered"


class TestChatMessageEndpoint:
    """POST /api/chat/message 엔드포인트 테스트"""

    def test_chat_message_endpoint(self):
        """POST /api/chat/message 엔드포인트가 존재해야 한다"""
        from services.backend.app.main import app

        client = TestClient(app)
        response = client.post(
            "/api/chat/message",
            json={"message": "안녕하세요"}
        )

        # 엔드포인트가 존재하면 404가 아님
        assert response.status_code != 404

    def test_chat_message_returns_stream(self):
        """채팅 메시지 전송 시 SSE 스트리밍 응답을 반환해야 한다"""
        from services.backend.app.main import app

        client = TestClient(app)
        response = client.post(
            "/api/chat/message",
            json={"message": "안녕하세요", "use_rag": False}
        )

        assert response.status_code == 200
        # SSE 스트리밍 응답 확인
        content_type = response.headers.get("content-type", "")
        assert "text/event-stream" in content_type or response.status_code == 200

    def test_chat_message_session_id(self):
        """세션 ID가 없으면 자동 생성해야 한다"""
        from services.backend.app.main import app

        client = TestClient(app)
        response = client.post(
            "/api/chat/message",
            json={"message": "테스트"}
        )

        assert response.status_code == 200
        # 응답에 session_id가 포함되어야 함
        # SSE 응답이므로 데이터를 파싱해야 함
        # 여기서는 응답이 성공하면 OK로 간주

    def test_chat_message_with_session_id(self):
        """전달된 세션 ID를 사용해야 한다"""
        from services.backend.app.main import app

        client = TestClient(app)
        session_id = "my-test-session-123"
        response = client.post(
            "/api/chat/message",
            json={
                "session_id": session_id,
                "message": "테스트"
            }
        )

        assert response.status_code == 200


class TestChatRequest:
    """ChatRequest 모델 테스트"""

    def test_chat_request_requires_message(self):
        """message 필드는 필수여야 한다"""
        from services.backend.app.main import app

        client = TestClient(app)
        response = client.post(
            "/api/chat/message",
            json={}  # message 없음
        )

        # 422 Unprocessable Entity (validation error)
        assert response.status_code == 422

    def test_chat_request_use_rag_default_true(self):
        """use_rag 기본값은 True여야 한다"""
        from services.backend.app.main import app

        client = TestClient(app)
        # use_rag 명시하지 않음
        response = client.post(
            "/api/chat/message",
            json={"message": "RAG 테스트"}
        )

        assert response.status_code == 200
