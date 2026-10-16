"""
Test: Backend Client
Phase 19.1: Orchestrator 상태 보고 클라이언트

TDD Red Phase: 이 테스트는 처음에 실패해야 합니다.
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


def test_backend_client_class_exists():
    """BackendClient 클래스가 존재하는지 확인"""
    from app.backend_client import BackendClient
    assert BackendClient is not None


def test_backend_client_report_state_method():
    """BackendClient에 report_state 메서드가 있는지 확인"""
    from app.backend_client import BackendClient

    client = BackendClient()
    assert hasattr(client, "report_state"), "BackendClient에 report_state 메서드가 없습니다"


@pytest.mark.asyncio
async def test_backend_client_sends_http_post():
    """report_state가 HTTP POST 요청을 보내는지 확인"""
    from app.backend_client import BackendClient

    with patch("httpx.AsyncClient.post") as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "ok"}
        mock_post.return_value = mock_response

        client = BackendClient(base_url="http://test-backend:11000")
        result = await client.report_state(
            state="LISTENING",
            session_id="test-session-123"
        )

        # HTTP POST가 호출되었는지 확인
        mock_post.assert_called_once()
        call_args = mock_post.call_args

        # URL에 /api/orchestrator/state가 포함되어야 함
        assert "/api/orchestrator/state" in str(call_args)
