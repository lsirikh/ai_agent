"""
음성 한 턴 계약 테스트 (실제 마이크 흐름 E2E 에서 드러난 문제)

1. 녹음에 웨이크워드 꼬리가 섞여 STT 가 "Hey Jarvis. 질문" 으로 오므로
   앞의 웨이크워드를 떼야 한다.
2. 음성 경로에 시스템 프롬프트가 없어 LLM 이 영어로 답했다
   → 한국어 음성용 프롬프트를 보낸다.
3. 듣기 타이머가 웨이크워드부터 10초라 말하는 중·STT 처리 중에 READY 로 돌아갔다
   → 발화 여유 시간만큼 더 기다린다.
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from tests.orchestrator.message_helpers import without_reference


def _orchestrator(sent: list, **kwargs):
    from services.orchestrator.app.orchestrator import Orchestrator

    with patch.object(Orchestrator, "_setup_redis", return_value=AsyncMock()):
        orchestrator = Orchestrator(**kwargs)

    async def fake_stream_request(messages, **kw):
        sent.append([dict(m) for m in messages])
        yield {"choices": [{"delta": {"content": "네."}, "finish_reason": None}]}
        yield {"choices": [{"delta": {}, "finish_reason": "stop"}]}

    orchestrator.llm_client._make_stream_request = fake_stream_request
    orchestrator.publish_tts_request = AsyncMock()
    return orchestrator


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "heard",
    [
        # (날씨 질문은 날씨·검색 도구가 없으면 LLM 없이 '확인할 수 없다' 고 답하므로
        #  호출어 떼기를 보는 이 시험은 일반 질문을 쓴다)
        "Hey Jarvis. 파이썬이 뭐야?",
        "hey jarvis, 파이썬이 뭐야?",
        "헤이 자비스 파이썬이 뭐야?",
    ],
)
async def test_should_strip_wake_phrase_before_llm(heard: str) -> None:
    sent: list = []
    orchestrator = _orchestrator(sent)
    await orchestrator.handle_wake_word()

    await orchestrator.handle_stt_result(heard)

    user_turns = [
        without_reference(m["content"]) for m in sent[0] if m["role"] == "user"
    ]
    assert user_turns == ["파이썬이 뭐야?"]


@pytest.mark.asyncio
async def test_should_skip_llm_when_only_wake_phrase_heard() -> None:
    sent: list = []
    orchestrator = _orchestrator(sent)
    await orchestrator.handle_wake_word()

    await orchestrator.handle_stt_result("Hey Jarvis.")

    assert sent == []


@pytest.mark.asyncio
async def test_should_send_korean_voice_system_prompt() -> None:
    sent: list = []
    orchestrator = _orchestrator(sent)
    await orchestrator.handle_wake_word()

    await orchestrator.handle_stt_result("파이썬이 뭐야?")

    system = [m["content"] for m in sent[0] if m["role"] == "system"]
    assert system and "한국어" in system[0]


@pytest.mark.asyncio
async def test_should_stay_listening_while_user_may_still_be_speaking() -> None:
    from services.orchestrator.app.state_machine import State

    sent: list = []
    orchestrator = _orchestrator(sent, listening_timeout=0.05)
    orchestrator.UTTERANCE_GRACE_SECONDS = 0.3
    await orchestrator.handle_wake_word()

    await asyncio.sleep(0.15)
    assert orchestrator.state_machine.current_state == State.LISTENING

    await asyncio.sleep(0.4)
    assert orchestrator.state_machine.current_state != State.LISTENING
