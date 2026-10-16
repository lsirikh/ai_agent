"""
말하는 중 상태 유지 테스트

LLM 스트림이 끝나자마자 READY 로 돌아가 TTS 가 실제로 말하는 몇 초 동안
트레이·오버레이가 '말하는 중'(TTS 단계)을 보여 주지 못했다.
TTS 는 문장마다 tts:complete 를 보내므로 마지막 문장이 끝날 때 READY 로 간다.
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest


def _orchestrator(reply_tokens: list[str]):
    from services.orchestrator.app.orchestrator import Orchestrator

    with patch.object(Orchestrator, "_setup_redis", return_value=AsyncMock()):
        orchestrator = Orchestrator(redis_client=AsyncMock())

    async def fake_stream_request(messages, **kwargs):
        for token in reply_tokens:
            yield {"choices": [{"delta": {"content": token}, "finish_reason": None}]}
        yield {"choices": [{"delta": {}, "finish_reason": "stop"}]}

    orchestrator.llm_client._make_stream_request = fake_stream_request
    return orchestrator


@pytest.mark.asyncio
async def test_should_stay_speaking_until_last_sentence_completes() -> None:
    from services.orchestrator.app.state_machine import State

    orchestrator = _orchestrator(["첫 문장입니다. ", "두 번째 문장입니다."])
    await orchestrator.handle_wake_word()
    await orchestrator.handle_stt_result("두 문장으로 답해 줘")

    assert orchestrator.state_machine.current_state == State.TTS_PROCESSING

    await orchestrator.handle_speaking_complete()
    assert orchestrator.state_machine.current_state == State.TTS_PROCESSING

    await orchestrator.handle_speaking_complete()
    assert orchestrator.state_machine.current_state == State.READY


@pytest.mark.asyncio
async def test_should_return_ready_when_reply_is_empty() -> None:
    from services.orchestrator.app.state_machine import State

    orchestrator = _orchestrator([])
    await orchestrator.handle_wake_word()
    await orchestrator.handle_stt_result("아무 말")

    assert orchestrator.state_machine.current_state == State.READY


@pytest.mark.asyncio
async def test_should_return_ready_when_tts_never_completes() -> None:
    from services.orchestrator.app.state_machine import State

    orchestrator = _orchestrator(["한 문장입니다."])
    orchestrator.TTS_COMPLETE_TIMEOUT_SECONDS = 0.1
    await orchestrator.handle_wake_word()
    await orchestrator.handle_stt_result("한 문장으로 답해 줘")
    assert orchestrator.state_machine.current_state == State.TTS_PROCESSING

    await asyncio.sleep(0.3)

    assert orchestrator.state_machine.current_state == State.READY
