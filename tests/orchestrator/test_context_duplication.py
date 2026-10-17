"""
음성 경로 컨텍스트 회귀 테스트

사용자 발화가 LLM 요청 메시지에 한 번만 들어가야 한다.
(이전: process_user_input 이 컨텍스트에 먼저 넣고
_build_messages 가 다시 붙여 두 번 전송)
"""

from unittest.mock import AsyncMock, patch

import pytest

from tests.orchestrator.message_helpers import roles_and_questions, without_reference


def _make_orchestrator_with_real_llm_client(sent_requests: list) -> object:
    from services.orchestrator.app.llm_client import LLMClient
    from services.orchestrator.app.orchestrator import Orchestrator

    llm = LLMClient(base_url="http://llm.test", model_name="test-model")

    async def fake_stream_request(messages, **kwargs):
        sent_requests.append([dict(m) for m in messages])
        yield {
            "choices": [{"delta": {"content": "응답입니다."}, "finish_reason": None}]
        }
        yield {"choices": [{"delta": {}, "finish_reason": "stop"}]}

    llm._make_stream_request = fake_stream_request

    with patch.object(Orchestrator, "_setup_redis", return_value=AsyncMock()):
        orchestrator = Orchestrator(llm_client=llm)
    orchestrator.publish_tts_request = AsyncMock()
    return orchestrator


class TestUserTurnSentOnce:
    @pytest.mark.asyncio
    async def test_should_send_user_turn_once_when_processing_first_input(self):
        sent_requests: list = []
        orchestrator = _make_orchestrator_with_real_llm_client(sent_requests)

        await orchestrator.process_user_input("오늘 날씨 어때?")

        user_turns = [m for m in sent_requests[0] if m["role"] == "user"]
        assert [without_reference(m["content"]) for m in user_turns] == [
            "오늘 날씨 어때?"
        ]

    @pytest.mark.asyncio
    async def test_should_keep_alternating_history_when_processing_second_input(self):
        sent_requests: list = []
        orchestrator = _make_orchestrator_with_real_llm_client(sent_requests)

        await orchestrator.process_user_input("첫 번째 질문")
        await orchestrator.process_user_input("두 번째 질문")

        roles_and_contents = roles_and_questions(sent_requests[1])
        assert roles_and_contents == [
            ("user", "첫 번째 질문"),
            ("assistant", "응답입니다."),
            ("user", "두 번째 질문"),
        ]
