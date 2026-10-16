"""
Tests for ChatService context loading

Phase 15.3: ChatService 컨텍스트 로드
- context_enabled, context_window_size 속성
- _load_conversation_history 메서드
- process_message에서 히스토리 전달
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestChatServiceContextSettings:
    """ChatService 컨텍스트 설정 테스트"""

    def test_chat_service_has_context_settings(self):
        """ChatService가 context_enabled, context_window_size 속성을 가져야 함"""
        from services.backend.app.services.chat_service import ChatService

        service = ChatService()

        # 기본값 확인
        assert hasattr(service, 'context_enabled')
        assert hasattr(service, 'context_window_size')
        assert service.context_enabled is True
        assert service.context_window_size == 20

    def test_chat_service_custom_context_settings(self):
        """ChatService에 커스텀 컨텍스트 설정을 전달할 수 있어야 함"""
        from services.backend.app.services.chat_service import ChatService

        service = ChatService(
            context_enabled=False,
            context_window_size=10
        )

        assert service.context_enabled is False
        assert service.context_window_size == 10


class TestChatServiceLoadConversationHistory:
    """ChatService._load_conversation_history 테스트"""

    @pytest.mark.asyncio
    async def test_load_conversation_history_when_enabled(self):
        """context_enabled=True일 때 히스토리를 로드해야 함"""
        from services.backend.app.services.chat_service import ChatService

        # history_store 모킹
        mock_history_store = AsyncMock()
        mock_history_store.get_session_messages = AsyncMock(return_value=[
            {"role": "assistant", "content": "응답2"},
            {"role": "user", "content": "메시지2"},
            {"role": "assistant", "content": "응답1"},
            {"role": "user", "content": "메시지1"}
        ])

        service = ChatService(
            history_store=mock_history_store,
            context_enabled=True,
            context_window_size=10
        )

        # 히스토리 로드
        history = await service._load_conversation_history("session123")

        # 검증
        assert len(history) == 4
        # 시간순 정렬 확인 (오래된 순)
        assert history[0]["content"] == "메시지1"
        assert history[1]["content"] == "응답1"
        assert history[2]["content"] == "메시지2"
        assert history[3]["content"] == "응답2"

        # limit이 전달되었는지 확인
        mock_history_store.get_session_messages.assert_called_once_with(
            "session123",
            limit=10
        )

    @pytest.mark.asyncio
    async def test_no_history_when_disabled(self):
        """context_enabled=False일 때 빈 히스토리 반환"""
        from services.backend.app.services.chat_service import ChatService

        mock_history_store = AsyncMock()

        service = ChatService(
            history_store=mock_history_store,
            context_enabled=False,
            context_window_size=10
        )

        # 히스토리 로드
        history = await service._load_conversation_history("session123")

        # 검증
        assert history == []
        # get_session_messages가 호출되지 않아야 함
        mock_history_store.get_session_messages.assert_not_called()

    @pytest.mark.asyncio
    async def test_context_window_size_limit(self):
        """context_window_size 제한이 적용되어야 함"""
        from services.backend.app.services.chat_service import ChatService

        mock_history_store = AsyncMock()
        mock_history_store.get_session_messages = AsyncMock(return_value=[])

        service = ChatService(
            history_store=mock_history_store,
            context_enabled=True,
            context_window_size=5  # 5개로 제한
        )

        # 히스토리 로드
        await service._load_conversation_history("session123")

        # limit=5로 호출되었는지 확인
        mock_history_store.get_session_messages.assert_called_once_with(
            "session123",
            limit=5
        )

    @pytest.mark.asyncio
    async def test_history_time_order(self):
        """히스토리가 시간순으로 정렬되어야 함 (오래된 순 → 최신순)"""
        from services.backend.app.services.chat_service import ChatService

        # DB는 DESC로 반환 (최신순)
        mock_history_store = AsyncMock()
        mock_history_store.get_session_messages = AsyncMock(return_value=[
            {"role": "user", "content": "세 번째"},
            {"role": "user", "content": "두 번째"},
            {"role": "user", "content": "첫 번째"}
        ])

        service = ChatService(
            history_store=mock_history_store,
            context_enabled=True,
            context_window_size=10
        )

        history = await service._load_conversation_history("session123")

        # 오래된 순으로 정렬되어야 함
        assert history[0]["content"] == "첫 번째"
        assert history[1]["content"] == "두 번째"
        assert history[2]["content"] == "세 번째"

    @pytest.mark.asyncio
    async def test_no_history_store_returns_empty(self):
        """history_store가 없으면 빈 히스토리 반환"""
        from services.backend.app.services.chat_service import ChatService

        service = ChatService(
            history_store=None,
            context_enabled=True,
            context_window_size=10
        )

        history = await service._load_conversation_history("session123")
        assert history == []


class TestChatServiceProcessMessageWithContext:
    """ChatService.process_message 컨텍스트 전달 테스트"""

    @pytest.mark.asyncio
    async def test_process_message_passes_history_to_llm(self):
        """process_message가 LLM 호출 시 히스토리를 전달해야 함"""
        from services.backend.app.services.chat_service import ChatService

        # LLM 클라이언트 모킹
        captured_history = None

        async def mock_generate_stream(prompt, system_prompt=None, conversation_history=None):
            nonlocal captured_history
            captured_history = conversation_history
            yield "응답입니다"

        mock_llm = MagicMock()
        mock_llm.generate_stream = mock_generate_stream

        # History store 모킹
        mock_history_store = AsyncMock()
        mock_history_store.get_session_messages = AsyncMock(return_value=[
            {"role": "assistant", "content": "이전 응답"},
            {"role": "user", "content": "이전 질문"}
        ])
        mock_history_store.add_message = AsyncMock()

        service = ChatService(
            llm_client=mock_llm,
            history_store=mock_history_store,
            context_enabled=True,
            context_window_size=20
        )

        # 메시지 처리
        events = []
        async for event in service.process_message(
            session_id="session123",
            message="현재 질문",
            use_rag=False
        ):
            events.append(event)

        # 히스토리가 LLM에 전달되었는지 확인
        assert captured_history is not None
        assert len(captured_history) == 2
        assert captured_history[0]["content"] == "이전 질문"
        assert captured_history[1]["content"] == "이전 응답"

    @pytest.mark.asyncio
    async def test_update_context_settings_runtime(self):
        """런타임에 컨텍스트 설정을 변경할 수 있어야 함"""
        from services.backend.app.services.chat_service import ChatService

        service = ChatService(
            context_enabled=True,
            context_window_size=20
        )

        # 초기값 확인
        assert service.context_enabled is True
        assert service.context_window_size == 20

        # 런타임 변경
        service.update_context_settings(
            context_enabled=False,
            context_window_size=10
        )

        # 변경된 값 확인
        assert service.context_enabled is False
        assert service.context_window_size == 10
