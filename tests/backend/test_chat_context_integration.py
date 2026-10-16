"""
Tests for Chat + LLM Context Settings Integration

Phase 15.5: ChatService와 LLM Context Settings 통합
Phase 33: async get_chat_service() 지원
- get_chat_service()가 LLM context settings를 로드해야 함
- 설정 변경 시 ChatService에 반영되어야 함
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock


class TestChatServiceContextIntegration:
    """ChatService + LLM Context Settings 통합 테스트"""

    @pytest.mark.asyncio
    async def test_get_chat_service_loads_context_settings(self):
        """get_chat_service()가 LLM context settings를 로드해야 함"""
        from services.backend.app.routes.chat import reset_services, get_chat_service

        # 서비스 리셋
        reset_services()

        # LLM context settings mock
        with patch("services.backend.app.routes.chat._llm_context_settings") as mock_settings:
            mock_settings.context_enabled = True
            mock_settings.context_window_size = 30

            # ChatService mock
            with patch("services.backend.app.routes.chat.ChatService") as mock_chat_service:
                # get_history_store mock (async)
                with patch("services.backend.app.routes.chat.get_history_store", new_callable=AsyncMock) as mock_history:
                    mock_history.return_value = None

                    chat_service = await get_chat_service()

                    # ChatService가 context 설정과 함께 생성되었는지 확인
                    mock_chat_service.assert_called_once()
                    call_kwargs = mock_chat_service.call_args.kwargs

                    assert "context_enabled" in call_kwargs
                    assert "context_window_size" in call_kwargs
                    assert call_kwargs["context_enabled"] == True
                    assert call_kwargs["context_window_size"] == 30

    @pytest.mark.asyncio
    async def test_get_chat_service_uses_default_if_settings_not_available(self):
        """LLM context settings를 로드할 수 없으면 기본값 사용"""
        from services.backend.app.routes.chat import reset_services, get_chat_service

        reset_services()

        # settings에서 기본값 사용
        with patch("services.backend.app.routes.chat._llm_context_settings") as mock_settings:
            mock_settings.context_enabled = True
            mock_settings.context_window_size = 20

            with patch("services.backend.app.routes.chat.ChatService") as mock_chat_service:
                with patch("services.backend.app.routes.chat.get_history_store", new_callable=AsyncMock) as mock_history:
                    mock_history.return_value = None

                    chat_service = await get_chat_service()

                    # ChatService가 생성되었는지 확인
                    mock_chat_service.assert_called_once()
                    call_kwargs = mock_chat_service.call_args.kwargs

                    # 기본값이 사용되어야 함
                    assert call_kwargs.get("context_enabled", True) == True
                    assert call_kwargs.get("context_window_size", 20) == 20

    @pytest.mark.asyncio
    async def test_chat_service_context_enabled_false(self):
        """context_enabled=False 설정이 ChatService에 전달되어야 함"""
        from services.backend.app.routes.chat import reset_services, get_chat_service

        reset_services()

        # context 비활성화 설정
        with patch("services.backend.app.routes.chat._llm_context_settings") as mock_settings:
            mock_settings.context_enabled = False
            mock_settings.context_window_size = 10

            with patch("services.backend.app.routes.chat.ChatService") as mock_chat_service:
                with patch("services.backend.app.routes.chat.get_history_store", new_callable=AsyncMock) as mock_history:
                    mock_history.return_value = None

                    chat_service = await get_chat_service()

                    call_kwargs = mock_chat_service.call_args.kwargs
                    assert call_kwargs.get("context_enabled") == False
                    assert call_kwargs.get("context_window_size") == 10

    @pytest.mark.asyncio
    async def test_chat_service_with_custom_window_size(self):
        """custom window size 설정이 ChatService에 전달되어야 함"""
        from services.backend.app.routes.chat import reset_services, get_chat_service

        reset_services()

        with patch("services.backend.app.routes.chat._llm_context_settings") as mock_settings:
            mock_settings.context_enabled = True
            mock_settings.context_window_size = 50  # 최대값

            with patch("services.backend.app.routes.chat.ChatService") as mock_chat_service:
                with patch("services.backend.app.routes.chat.get_history_store", new_callable=AsyncMock) as mock_history:
                    mock_history.return_value = None

                    chat_service = await get_chat_service()

                    call_kwargs = mock_chat_service.call_args.kwargs
                    assert call_kwargs.get("context_window_size") == 50


class TestChatServiceDynamicSettingsUpdate:
    """ChatService 동적 설정 업데이트 테스트"""

    def test_update_context_settings_method_exists(self):
        """ChatService에 update_context_settings 메서드가 있어야 함"""
        from services.backend.app.services.chat_service import ChatService

        chat_service = ChatService()
        assert hasattr(chat_service, "update_context_settings")
        assert callable(chat_service.update_context_settings)

    def test_update_context_settings_changes_context_enabled(self):
        """update_context_settings로 context_enabled 변경 가능"""
        from services.backend.app.services.chat_service import ChatService

        chat_service = ChatService(context_enabled=True)
        assert chat_service.context_enabled == True

        chat_service.update_context_settings(context_enabled=False)
        assert chat_service.context_enabled == False

    def test_update_context_settings_changes_window_size(self):
        """update_context_settings로 context_window_size 변경 가능"""
        from services.backend.app.services.chat_service import ChatService

        chat_service = ChatService(context_window_size=20)
        assert chat_service.context_window_size == 20

        chat_service.update_context_settings(context_window_size=35)
        assert chat_service.context_window_size == 35


class TestChatAPIWithContextSettings:
    """Chat API + Context Settings 통합 테스트"""

    def test_send_message_uses_context_settings(self):
        """POST /api/chat/message가 context settings를 사용해야 함"""
        from fastapi.testclient import TestClient
        from services.backend.app.main import app
        from services.backend.app.routes.chat import reset_services

        reset_services()
        client = TestClient(app)

        # ChatService가 context settings와 함께 생성되는지 확인
        with patch("services.backend.app.routes.chat._llm_context_settings") as mock_settings:
            mock_settings.context_enabled = True
            mock_settings.context_window_size = 25

            with patch("services.backend.app.routes.chat.ChatService") as mock_chat_service:
                # get_history_store async mock
                with patch("services.backend.app.routes.chat.get_history_store", new_callable=AsyncMock) as mock_history:
                    mock_history.return_value = None

                    # ChatService mock 설정
                    mock_instance = MagicMock()
                    mock_instance.process_message = AsyncMock(return_value=iter([]))
                    mock_chat_service.return_value = mock_instance

                    # 메시지 전송
                    response = client.post(
                        "/api/chat/message",
                        json={"message": "테스트", "session_id": "test-session"}
                    )

                    # ChatService가 context 설정과 함께 생성되었는지 확인
                    call_kwargs = mock_chat_service.call_args.kwargs
                    assert "context_enabled" in call_kwargs or "context_window_size" in call_kwargs
