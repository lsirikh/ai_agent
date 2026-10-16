"""
Backend API - ChatService Tests

Phase 9.2: ChatService 클래스 테스트
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestChatServiceInitialization:
    """ChatService 초기화 테스트"""

    def test_chat_service_initialization(self):
        """ChatService가 정상적으로 초기화되어야 한다"""
        from services.backend.app.services.chat_service import ChatService

        service = ChatService()

        assert service is not None
        assert hasattr(service, "llm_client")
        assert hasattr(service, "rag_service")


class TestChatServiceProcessMessage:
    """ChatService 메시지 처리 테스트"""

    @pytest.mark.asyncio
    async def test_process_message_calls_llm(self):
        """process_message가 LLM을 호출해야 한다"""
        from services.backend.app.services.chat_service import ChatService

        # Mock LLM client
        mock_llm = MagicMock()

        async def mock_stream(text, system_prompt=None, **kwargs):
            yield "응답"
            yield "입니다"

        mock_llm.generate_stream = mock_stream

        service = ChatService(llm_client=mock_llm)

        # 메시지 처리
        events = []
        async for event in service.process_message(
            session_id="test-session",
            message="테스트 메시지",
            use_rag=False
        ):
            events.append(event)

        # 최소 하나의 이벤트가 발생해야 함
        assert len(events) > 0

    @pytest.mark.asyncio
    async def test_process_message_streams_tokens(self):
        """process_message가 토큰을 스트리밍해야 한다"""
        from services.backend.app.services.chat_service import ChatService

        mock_llm = MagicMock()

        async def mock_stream(text, system_prompt=None, **kwargs):
            yield "첫"
            yield "번"
            yield "째"

        mock_llm.generate_stream = mock_stream

        service = ChatService(llm_client=mock_llm)

        events = []
        async for event in service.process_message(
            session_id="test-session",
            message="테스트",
            use_rag=False
        ):
            events.append(event)

        # 토큰 이벤트 확인
        token_events = [e for e in events if e["type"] == "token"]
        assert len(token_events) >= 1

    @pytest.mark.asyncio
    async def test_process_message_returns_complete(self):
        """process_message가 완료 이벤트를 반환해야 한다"""
        from services.backend.app.services.chat_service import ChatService

        mock_llm = MagicMock()

        async def mock_stream(text, system_prompt=None, **kwargs):
            yield "응답"

        mock_llm.generate_stream = mock_stream

        service = ChatService(llm_client=mock_llm)

        events = []
        async for event in service.process_message(
            session_id="test-session",
            message="테스트",
            use_rag=False
        ):
            events.append(event)

        # 완료 이벤트 확인
        complete_events = [e for e in events if e["type"] == "complete"]
        assert len(complete_events) == 1
        assert "content" in complete_events[0]
        assert "session_id" in complete_events[0]


class TestChatServiceSystemPrompt:
    """ChatService 시스템 프롬프트 테스트"""

    def test_build_system_prompt_without_rag(self):
        """RAG 없이 기본 시스템 프롬프트를 생성해야 한다"""
        from services.backend.app.services.chat_service import ChatService

        service = ChatService()
        prompt = service._build_system_prompt()

        assert "EdgeVoice" in prompt or "어시스턴트" in prompt

    def test_build_system_prompt_with_rag_context(self):
        """RAG 컨텍스트가 있으면 프롬프트에 포함해야 한다"""
        from services.backend.app.services.chat_service import ChatService

        service = ChatService()
        rag_context = "관련 문서 내용입니다."
        prompt = service._build_system_prompt(rag_context=rag_context)

        assert rag_context in prompt
