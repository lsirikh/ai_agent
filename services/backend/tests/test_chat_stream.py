"""
Test: Chat SSE Stream
Phase 18.4.1: Chat SSE 스트림

TDD Red Phase: 이 테스트는 처음에 실패해야 합니다.
"""
import pytest
from unittest.mock import AsyncMock
from uuid import uuid4


def test_chat_stream_endpoint_exists():
    """GET /api/chat/stream 엔드포인트가 존재하는지 확인"""
    from app.routes.chat import router

    # 라우터에서 /stream 경로 확인
    routes = [route.path for route in router.routes]
    assert "/stream" in routes or any("/stream" in r for r in routes), \
        "chat 라우터에 /stream 엔드포인트가 없습니다"


def test_chat_stream_function_exists():
    """stream_chat 함수가 존재하는지 확인"""
    from app.routes.chat import stream_chat
    assert callable(stream_chat)


@pytest.mark.asyncio
async def test_chat_stream_returns_sse():
    """chat stream이 SSE 응답을 반환하는지 확인"""
    from app.routes.chat import stream_chat
    from fastapi.responses import StreamingResponse

    session_id = str(uuid4())

    # stream_chat 호출
    response = await stream_chat(session_id=session_id)

    # StreamingResponse인지 확인
    assert isinstance(response, StreamingResponse)

    # Content-type 확인
    assert response.media_type == "text/event-stream"
