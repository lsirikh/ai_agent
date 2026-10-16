"""
Test: Message Sync
Phase 19.4: 메시지 실시간 저장

TDD Red Phase: 이 테스트는 처음에 실패해야 합니다.
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


def test_backend_client_save_message_method():
    """BackendClient에 save_message 메서드가 있는지 확인"""
    from app.backend_client import BackendClient

    client = BackendClient()
    assert hasattr(client, "save_message"), "BackendClient에 save_message 메서드가 없습니다"


@pytest.mark.asyncio
async def test_message_saved_with_voice_source():
    """메시지가 voice source로 저장되는지 확인"""
    from app.backend_client import BackendClient

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message_id": "msg-123",
            "status": "created"
        }
        mock_client.post.return_value = mock_response

        client = BackendClient(base_url="http://test-backend:11000")
        client.current_session_id = "test-session-123"

        result = await client.save_message(
            role="user",
            content="안녕하세요",
            source="voice"
        )

        # HTTP POST가 호출되었는지 확인
        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args

        # URL에 /api/messages/pipeline이 포함되어야 함
        assert "/api/messages/pipeline" in str(call_args)

        # 요청 본문에 source가 포함되어야 함
        request_body = call_args[1]["json"]
        assert request_body["source"] == "voice"


@pytest.mark.asyncio
async def test_message_broadcasts_to_chat_stream():
    """메시지가 chat stream에 브로드캐스트되는지 확인"""
    from app.backend_client import BackendClient

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message_id": "msg-456",
            "broadcasted": True
        }
        mock_client.post.return_value = mock_response

        client = BackendClient(base_url="http://test-backend:11000")
        client.current_session_id = "test-session-123"

        result = await client.save_message(
            role="assistant",
            content="안녕하세요! 무엇을 도와드릴까요?",
            source="voice"
        )

        # message_id가 반환되어야 함
        assert result is not None
        assert "message_id" in result
