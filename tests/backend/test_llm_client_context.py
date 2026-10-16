"""
Tests for SimpleLLMClient conversation_history support

Phase 15.2: SimpleLLMClient 수정
- conversation_history 파라미터 추가
- 히스토리 포함 메시지 구성
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import json


class TestSimpleLLMClientContext:
    """SimpleLLMClient conversation_history 테스트"""

    def test_generate_stream_accepts_history(self):
        """generate_stream이 conversation_history 파라미터를 수용해야 함"""
        from services.backend.app.services.llm_client import SimpleLLMClient

        client = SimpleLLMClient()

        # conversation_history 파라미터가 있어야 함
        import inspect
        sig = inspect.signature(client.generate_stream)
        params = list(sig.parameters.keys())

        assert "conversation_history" in params

    @pytest.mark.asyncio
    async def test_generate_stream_builds_messages_with_history(self):
        """conversation_history가 있으면 messages에 포함되어야 함"""
        from services.backend.app.services.llm_client import SimpleLLMClient

        client = SimpleLLMClient(base_url="http://test:11003")
        client.model_name = "test-model"  # 모델 조회 스킵

        captured_payload = {}

        # AsyncMock으로 context manager 패턴 모킹
        mock_response = AsyncMock()

        async def aiter_lines():
            yield 'data: {"choices":[{"delta":{"content":"응답"}}]}'
            yield 'data: [DONE]'

        mock_response.aiter_lines = aiter_lines

        # stream 메서드 모킹 - 동기 함수로, async with에서 사용 가능한 객체 반환
        class MockStreamContextManager:
            def __init__(self, json_payload):
                captured_payload.update(json_payload or {})

            async def __aenter__(self):
                return mock_response

            async def __aexit__(self, *args):
                pass

        def mock_stream(method, url, json=None):
            return MockStreamContextManager(json)

        client._http_client.stream = mock_stream

        history = [
            {"role": "user", "content": "내 이름은 철수야"},
            {"role": "assistant", "content": "안녕하세요 철수님!"}
        ]

        tokens = []
        async for token in client.generate_stream(
            prompt="내 이름이 뭐야?",
            conversation_history=history
        ):
            tokens.append(token)

        # payload가 캡처되어야 함
        assert captured_payload is not None
        assert len(captured_payload) > 0

        # messages 구조 확인
        messages = captured_payload.get("messages", [])
        assert len(messages) == 4  # system + 2 history + user

        # 첫 번째는 system
        assert messages[0]["role"] == "system"

        # 히스토리가 포함되어 있어야 함
        assert messages[1]["role"] == "user"
        assert messages[1]["content"] == "내 이름은 철수야"
        assert messages[2]["role"] == "assistant"
        assert messages[2]["content"] == "안녕하세요 철수님!"

        # 마지막은 현재 user 메시지
        assert messages[3]["role"] == "user"
        assert messages[3]["content"] == "내 이름이 뭐야?"

    @pytest.mark.asyncio
    async def test_generate_stream_without_history(self):
        """conversation_history가 없어도 정상 동작해야 함"""
        from services.backend.app.services.llm_client import SimpleLLMClient

        client = SimpleLLMClient(base_url="http://test:11003")
        client.model_name = "test-model"

        captured_payload = {}

        mock_response = AsyncMock()

        async def aiter_lines():
            yield 'data: {"choices":[{"delta":{"content":"안녕"}}]}'
            yield 'data: [DONE]'

        mock_response.aiter_lines = aiter_lines

        class MockStreamContextManager:
            def __init__(self, json_payload):
                captured_payload.update(json_payload or {})

            async def __aenter__(self):
                return mock_response

            async def __aexit__(self, *args):
                pass

        def mock_stream(method, url, json=None):
            return MockStreamContextManager(json)

        client._http_client.stream = mock_stream

        tokens = []
        async for token in client.generate_stream(
            prompt="안녕하세요",
            conversation_history=None  # 명시적으로 None
        ):
            tokens.append(token)

        # payload가 캡처되어야 함
        assert len(captured_payload) > 0

        # messages 구조 확인: system + user만
        messages = captured_payload.get("messages", [])
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        assert messages[1]["content"] == "안녕하세요"

    @pytest.mark.asyncio
    async def test_generate_stream_empty_history(self):
        """빈 conversation_history도 처리해야 함"""
        from services.backend.app.services.llm_client import SimpleLLMClient

        client = SimpleLLMClient(base_url="http://test:11003")
        client.model_name = "test-model"

        captured_payload = {}

        mock_response = AsyncMock()

        async def aiter_lines():
            yield 'data: {"choices":[{"delta":{"content":"테스트"}}]}'
            yield 'data: [DONE]'

        mock_response.aiter_lines = aiter_lines

        class MockStreamContextManager:
            def __init__(self, json_payload):
                captured_payload.update(json_payload or {})

            async def __aenter__(self):
                return mock_response

            async def __aexit__(self, *args):
                pass

        def mock_stream(method, url, json=None):
            return MockStreamContextManager(json)

        client._http_client.stream = mock_stream

        tokens = []
        async for token in client.generate_stream(
            prompt="테스트",
            conversation_history=[]  # 빈 리스트
        ):
            tokens.append(token)

        # messages 구조 확인: system + user만 (빈 히스토리)
        messages = captured_payload.get("messages", [])
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
