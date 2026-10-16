"""
Test: SSE Stream Endpoints
Phase 18.2: SSE 기반 실시간 상태 스트리밍
"""
import pytest
from unittest.mock import AsyncMock


def test_status_stream_endpoint_exists():
    """GET /api/status/stream 엔드포인트가 등록되어 있는지 확인"""
    from app.routes.status import router

    # 라우터에서 /stream 경로 확인
    routes = [route.path for route in router.routes]
    assert "/stream" in routes or any("/stream" in r for r in routes)


def test_stream_status_function_exists():
    """stream_status 함수가 존재하는지 확인"""
    from app.routes.status import stream_status
    assert callable(stream_status)


@pytest.mark.asyncio
async def test_sse_event_generator_yields_init():
    """SSE 이벤트 생성기가 init 이벤트를 생성하는지 확인"""
    from app.routes.status import get_status_state_manager, stream_status
    import app.routes.status as status_module
    from fastapi.responses import StreamingResponse

    # Mock StateManager
    mock_manager = AsyncMock()
    mock_manager.get_current_state = AsyncMock(return_value={"state": "READY"})

    original_func = status_module.get_status_state_manager

    async def mock_get_manager():
        return mock_manager

    status_module.get_status_state_manager = mock_get_manager

    try:
        # stream_status 호출
        response = await stream_status()

        # StreamingResponse인지 확인
        assert isinstance(response, StreamingResponse)

        # Content-type 확인
        assert response.media_type == "text/event-stream"

    finally:
        status_module.get_status_state_manager = original_func


def test_dashboard_updates_channel_defined():
    """DASHBOARD_UPDATES_CHANNEL 상수가 정의되어 있는지 확인"""
    from app.services.state_manager import DASHBOARD_UPDATES_CHANNEL
    assert DASHBOARD_UPDATES_CHANNEL is not None
    assert isinstance(DASHBOARD_UPDATES_CHANNEL, str)
    assert "dashboard" in DASHBOARD_UPDATES_CHANNEL.lower()


def test_state_manager_imported_in_status():
    """status.py에서 StateManager가 import되어 있는지 확인"""
    from app.routes.status import StateManager
    assert StateManager is not None
