"""
Backend API - History Store Connection Tests

Phase 17: History Store 연결 문제 수정 테스트
"""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch


class TestHistoryStoreConnection:
    """Phase 17.1: History Store 연결 테스트"""

    @pytest.mark.asyncio
    async def test_get_history_store_calls_connect(self):
        """get_history_store가 connect()를 호출해야 한다"""
        from services.backend.app.routes import chat as chat_module

        # Reset cached instance
        chat_module._history_store = None

        # Mock PersistentHistoryStore
        mock_store = MagicMock()
        mock_store.connect = AsyncMock()
        mock_store.pool = MagicMock()  # Simulate connected state

        # 함수 내 import를 패치
        with patch('services.backend.app.services.persistent_history.PersistentHistoryStore', return_value=mock_store):
            with patch.dict('os.environ', {'HISTORY_ENABLED': 'true', 'DATABASE_URL': 'postgresql://test:test@localhost/test'}):
                # get_history_store 호출 (async 함수가 되어야 함)
                store = await chat_module.get_history_store()

                # connect가 호출되어야 함
                mock_store.connect.assert_called_once()

    @pytest.mark.asyncio
    async def test_history_store_saves_messages_when_connected(self):
        """연결된 History Store가 메시지를 저장해야 한다"""
        from services.backend.app.services.persistent_history import PersistentHistoryStore
        import uuid

        # Mock pool - Phase 33: conn.execute도 async
        mock_pool = MagicMock()
        mock_conn = MagicMock()
        mock_conn.execute = AsyncMock()  # INSERT INTO sessions
        mock_conn.fetchval = AsyncMock(return_value=123)
        mock_pool.acquire = MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_conn), __aexit__=AsyncMock()))

        store = PersistentHistoryStore("postgresql://test:test@localhost/test")
        store.pool = mock_pool

        # 메시지 저장 - 유효한 UUID 사용
        session_id = str(uuid.uuid4())
        result = await store.add_message(
            session_id=session_id,
            role="user",
            content="Hello"
        )

        # 결과 확인
        assert result == "123"

    @pytest.mark.asyncio
    async def test_history_store_returns_empty_when_not_connected(self):
        """연결되지 않은 History Store는 빈 리스트를 반환해야 한다"""
        from services.backend.app.services.persistent_history import PersistentHistoryStore

        store = PersistentHistoryStore("postgresql://test:test@localhost/test")
        # pool은 None (연결 안됨)

        # 메시지 조회
        result = await store.get_session_messages("test-session")

        # 빈 리스트
        assert result == []


class TestChatServiceWithHistory:
    """Phase 17.2: ChatService + History Store 통합 테스트"""

    @pytest.mark.asyncio
    async def test_chat_service_loads_history_when_context_enabled(self):
        """context_enabled가 True일 때 히스토리를 로드해야 한다"""
        from services.backend.app.services.chat_service import ChatService

        # Mock history store with messages
        mock_history = MagicMock()
        mock_history.get_session_messages = AsyncMock(return_value=[
            {"role": "user", "content": "안녕"},
            {"role": "assistant", "content": "안녕하세요!"}
        ])
        mock_history.add_message = AsyncMock()

        # Mock LLM client
        mock_llm = MagicMock()

        async def mock_generate(*args, **kwargs):
            # conversation_history가 전달되었는지 확인
            history = kwargs.get('conversation_history', [])
            assert len(history) == 2  # 이전 대화 2개
            yield "응답입니다."

        mock_llm.generate_stream = mock_generate

        service = ChatService(
            llm_client=mock_llm,
            history_store=mock_history,
            context_enabled=True,
            context_window_size=20
        )

        # 메시지 처리
        events = []
        async for event in service.process_message("test-session", "테스트"):
            events.append(event)

        # 히스토리가 로드되었는지 확인
        mock_history.get_session_messages.assert_called_once()

    @pytest.mark.asyncio
    async def test_chat_service_skips_history_when_context_disabled(self):
        """context_enabled가 False일 때 히스토리를 로드하지 않아야 한다"""
        from services.backend.app.services.chat_service import ChatService

        # Mock history store
        mock_history = MagicMock()
        mock_history.get_session_messages = AsyncMock(return_value=[])
        mock_history.add_message = AsyncMock()

        # Mock LLM client
        mock_llm = MagicMock()

        async def mock_generate(*args, **kwargs):
            # conversation_history가 비어있어야 함
            history = kwargs.get('conversation_history', [])
            assert len(history) == 0
            yield "응답입니다."

        mock_llm.generate_stream = mock_generate

        service = ChatService(
            llm_client=mock_llm,
            history_store=mock_history,
            context_enabled=False,  # 비활성화
            context_window_size=20
        )

        # 메시지 처리
        events = []
        async for event in service.process_message("test-session", "테스트"):
            events.append(event)

        # 히스토리가 로드되지 않아야 함
        mock_history.get_session_messages.assert_not_called()


class TestKoreanLanguagePrompt:
    """Phase 17.3: 한국어 유지 시스템 프롬프트 테스트"""

    def test_system_prompt_enforces_korean(self):
        """시스템 프롬프트가 한국어를 강제해야 한다"""
        from services.backend.app.services.llm_client import LANGUAGE_PROMPTS

        korean_prompt = LANGUAGE_PROMPTS.get("ko", "")

        # 한국어 응답 강제 문구 확인
        assert "한국어" in korean_prompt
        assert "응답" in korean_prompt or "답변" in korean_prompt

    def test_chat_service_build_system_prompt_includes_language(self):
        """ChatService가 한국어 강제 프롬프트를 포함해야 한다"""
        from services.backend.app.services.chat_service import ChatService

        service = ChatService()
        prompt = service._build_system_prompt()

        # 한국어 관련 지시가 포함되어야 함
        assert "한국어" in prompt or "Korean" in prompt or "EdgeVoice" in prompt
