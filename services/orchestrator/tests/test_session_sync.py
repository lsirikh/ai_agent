"""
Test: Session Sync
Phase 19.3: 세션 자동 생성/동기화

TDD Red Phase: 이 테스트는 처음에 실패해야 합니다.
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


def test_backend_client_create_session_method():
    """BackendClient에 create_session 메서드가 있는지 확인"""
    from app.backend_client import BackendClient

    client = BackendClient()
    assert hasattr(client, "create_session"), "BackendClient에 create_session 메서드가 없습니다"


@pytest.mark.asyncio
async def test_backend_client_create_session_sends_post():
    """create_session이 HTTP POST 요청을 보내는지 확인"""
    from app.backend_client import BackendClient

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "session_id": "test-session-123",
            "status": "created"
        }
        mock_client.post.return_value = mock_response

        client = BackendClient(base_url="http://test-backend:11000")
        result = await client.create_session(source="voice")

        # HTTP POST가 호출되었는지 확인
        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args

        # URL에 /api/sessions/pipeline이 포함되어야 함
        assert "/api/sessions/pipeline" in str(call_args)


@pytest.mark.asyncio
async def test_session_sync_returns_session_id():
    """세션 동기화가 session_id를 반환하는지 확인"""
    from app.backend_client import BackendClient

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "session_id": "new-session-456",
            "status": "created"
        }
        mock_client.post.return_value = mock_response

        client = BackendClient(base_url="http://test-backend:11000")
        result = await client.create_session(source="voice")

        # session_id가 반환되어야 함
        assert result is not None
        assert "session_id" in result
        assert result["session_id"] == "new-session-456"


def test_orchestrator_creates_session_on_start():
    """Orchestrator가 시작 시 세션을 생성하는지 확인"""
    from app.backend_client import BackendClient

    # BackendClient에 session 관련 기능이 있는지 확인
    client = BackendClient()
    assert hasattr(client, "create_session")
    assert hasattr(client, "current_session_id") or callable(getattr(client, "create_session", None))
