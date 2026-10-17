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


@pytest.mark.asyncio
async def test_event_loop_keeps_listening_while_answering() -> None:
    # 실측: STT 결과 처리가 답을 다 만들 때까지 이벤트 루프를 막아,
    # 말하는 도중의 호출어를 답이 끝난 뒤(5초 뒤)에야 처리했다
    orchestrator = _orchestrator()
    answering = asyncio.Event()

    async def slow_answer(text):
        answering.set()
        await asyncio.sleep(30)

    orchestrator.handle_stt_result = slow_answer

    await asyncio.wait_for(
        orchestrator._handle_message(
            orchestrator.CHANNELS["stt_result"], {"text": "질문"}
        ),
        timeout=1,
    )
    await asyncio.wait_for(answering.wait(), timeout=1)
    orchestrator._stt_task.cancel()


@pytest.mark.asyncio
async def test_interrupted_answer_is_saved_so_it_is_not_repeated() -> None:
    # 실측: 끊긴 답이 기록에 없어 다음 질문('지금 몇 시야?') 에
    # 앞 답(사계절)을 처음부터 다시 말했다
    from tests.orchestrator.test_voice_tools import make, text_chunk

    orchestrator, backend, _, spoken = make(
        [[text_chunk("봄은 따뜻합니다. "), text_chunk("여름은 "), "wait"]]
    )
    await orchestrator.handle_wake_word()
    turn = asyncio.create_task(orchestrator.handle_stt_result("사계절 설명해 줘"))
    for _ in range(50):
        if spoken:
            break
        await asyncio.sleep(0.02)

    await orchestrator.handle_wake_word()  # 끼어들기
    await asyncio.sleep(0.05)
    turn.cancel()

    saved = [m for m in backend.saved if m["role"] == "assistant"]
    assert saved and saved[-1]["content"].startswith("봄은 따뜻합니다.")
    assert "끼어들어 중단" in saved[-1]["content"]
