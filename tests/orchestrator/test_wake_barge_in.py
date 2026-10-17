"""
말하는 도중 '헤이 자비스' 로 끼어들기 (사용자 요청 2026-10-17)

답을 만들거나 말하는 중에 호출어가 오면 그 답을 멈추고 바로 듣는다.
(전에는 바쁜 상태의 호출어를 무시해 끝까지 들어야 했다)
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest


def _orchestrator():
    from services.orchestrator.app.orchestrator import Orchestrator

    with patch.object(Orchestrator, "_setup_redis", return_value=AsyncMock()):
        return Orchestrator(redis_client=AsyncMock())


@pytest.mark.asyncio
@pytest.mark.parametrize("busy", ["LLM_PROCESSING", "TTS_PROCESSING"])
async def test_wake_word_while_busy_cancels_answer_and_listens(busy) -> None:
    from services.orchestrator.app.state_machine import State

    orchestrator = _orchestrator()
    orchestrator.state_machine.transition_to(State.LISTENING)
    orchestrator.state_machine.transition_to(State.STT_PROCESSING)
    orchestrator.state_machine.transition_to(State.LLM_PROCESSING)
    if busy == "TTS_PROCESSING":
        orchestrator.state_machine.transition_to(State.TTS_PROCESSING)
    answering = asyncio.create_task(asyncio.sleep(30))
    orchestrator._processing_task = answering
    orchestrator._pending_tts = 3

    handled = await orchestrator.handle_wake_word()
    await asyncio.sleep(0)

    assert handled is True
    assert orchestrator.state_machine.current_state == State.LISTENING
    assert answering.cancelled()
    assert orchestrator._pending_tts == 0
    assert orchestrator._listening_task is not None
