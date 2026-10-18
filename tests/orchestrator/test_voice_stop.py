"""
[중단] 버튼(사용자 요청 2026-10-18): 답을 쓰고·말하는 도중이든 듣는 중이든
멈추고 대기로.
끼어들기와 달리 다시 듣지 않는다.
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest


def _orchestrator():
    from services.orchestrator.app.orchestrator import Orchestrator

    with patch.object(Orchestrator, "_setup_redis", return_value=AsyncMock()):
        orchestrator = Orchestrator()
    orchestrator.publish_tts_request = AsyncMock()
    return orchestrator


@pytest.mark.asyncio
async def test_stop_while_answering_cancels_and_goes_ready() -> None:
    from services.orchestrator.app.state_machine import State

    orchestrator = _orchestrator()
    await orchestrator.handle_wake_word()
    orchestrator.state_machine.transition_to(State.STT_PROCESSING)
    orchestrator.state_machine.transition_to(State.LLM_PROCESSING)
    orchestrator._processing_task = asyncio.create_task(asyncio.sleep(30))
    orchestrator._pending_tts = 3

    await orchestrator.handle_stop()
    await asyncio.sleep(0)

    assert orchestrator._processing_task.cancelled()
    assert orchestrator._pending_tts == 0
    assert orchestrator.state_machine.current_state == State.READY


@pytest.mark.asyncio
async def test_stop_while_listening_goes_ready_without_listening_again() -> None:
    from services.orchestrator.app.state_machine import State

    orchestrator = _orchestrator()
    await orchestrator.handle_wake_word()
    assert orchestrator.state_machine.current_state == State.LISTENING

    await orchestrator.handle_stop()

    assert orchestrator.state_machine.current_state == State.READY


@pytest.mark.asyncio
async def test_stop_message_on_channel_is_handled() -> None:
    orchestrator = _orchestrator()
    orchestrator.handle_stop = AsyncMock()

    await orchestrator._handle_message(
        orchestrator.CHANNELS["voice_stop"], {"type": "stop"}
    )

    orchestrator.handle_stop.assert_awaited_once()
