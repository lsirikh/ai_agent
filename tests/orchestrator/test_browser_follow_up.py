"""
음성으로 브라우저를 다루다 이어서 한 말 · 단계별 로그
(사용자 보고 2026-10-19: 크롬·유튜브를 하라고 하면 '하겠다' 고만 하고 하지 않는다)

10-19 07:10 실측: '아이유 반편지 틀고'(검색 결과만 열림) 다음의 '영상 재생해' 에 도구를
부르지 않고 '재생해 주겠습니다' 라고만 했다. 로그에는 어떤 도구를 내놓고 불렀는지가
남지 않아 말만 한 턴을 가려낼 수 없었다.
"""

from unittest.mock import AsyncMock

import pytest

from shared.tools import Tool, ToolRegistry, ToolResult
from tests.orchestrator.test_voice_tools import call_chunk, make, text_chunk, voice_turn


def _registry(ran):
    registry = ToolRegistry()

    def tool(name):
        async def run(args):
            ran.append((name, args))
            return ToolResult(f"{name} 결과")

        return Tool(name=name, description=name,
                    parameters={"type": "object", "properties": {
                        "query": {"type": "string"}}},
                    run=run)

    for name in ("browser__play_youtube", "browser__browser_navigate",
                 "browser__close_browser", "get_time"):
        registry.add(tool(name))
    return registry


def _forced(request):
    choice = request["tool_choice"]
    return choice["function"]["name"] if isinstance(choice, dict) else choice


@pytest.mark.asyncio
async def test_follow_up_after_playing_is_sent_to_the_browser_tool() -> None:
    ran = []
    orchestrator, _, requests, _ = make(
        [
            [call_chunk(("browser__play_youtube", '{"query": "아이유 밤편지"}'))],
            [text_chunk("틀었어요.")],
            [call_chunk(("browser__play_youtube", '{"query": "아이유 밤편지"}'))],
            [text_chunk("다시 틀었어요.")],
        ],
        registry=_registry(ran),
    )

    await voice_turn(orchestrator, "유튜브에서 아이유 밤편지 틀어줘")
    await voice_turn(orchestrator, "영상 재생해")

    assert _forced(requests[2]) == "browser__play_youtube"
    assert [name for name, _ in ran] == ["browser__play_youtube"] * 2


@pytest.mark.asyncio
async def test_without_using_the_browser_a_follow_up_is_left_to_the_model() -> None:
    orchestrator, _, requests, _ = make(
        [[text_chunk("무엇을 재생할까요?")]], registry=_registry([])
    )

    await voice_turn(orchestrator, "영상 재생해")

    assert _forced(requests[0]) == "auto"


def _events(logger):
    return [
        (c.kwargs.get("event") or (c.args[0] if c.args else None), c.kwargs)
        for c in logger.log.await_args_list
    ]


@pytest.mark.asyncio
async def test_each_step_is_logged() -> None:
    orchestrator, _, _, _ = make(
        [
            [call_chunk(("browser__play_youtube", '{"query": "아이유 밤편지"}'))],
            [text_chunk("틀었어요.")],
        ],
        registry=_registry([]),
    )
    orchestrator._logger = AsyncMock()
    orchestrator.llm_client._logger = AsyncMock()

    await voice_turn(orchestrator, "유튜브에서 아이유 밤편지 틀어줘")

    plan = [k for e, k in _events(orchestrator.llm_client._logger) if e == "tool_plan"]
    assert plan and plan[0]["data"]["plan"] == ["browser__play_youtube"]
    events = dict(_events(orchestrator._logger))
    assert events["tool_call"]["data"]["name"] == "browser__play_youtube"
    assert "아이유 밤편지" in events["tool_call"]["data"]["arguments"]
    assert events["tool_result"]["data"]["is_error"] is False
    assert events["turn_tools"]["data"]["called"] == ["browser__play_youtube"]


@pytest.mark.asyncio
async def test_saying_it_was_done_without_a_tool_is_flagged() -> None:
    orchestrator, _, _, _ = make(
        [[text_chunk("네, 크롬 브라우저의 유튜브를 종료했습니다!")]],
        registry=_registry([]),
    )
    orchestrator._logger = AsyncMock()

    await voice_turn(orchestrator, "음악 그만")

    events = dict(_events(orchestrator._logger))
    flagged = events["action_claim_without_tool"]
    assert flagged["level"] == "warning"
    assert "종료했습니다" in flagged["data"]["answer"]


@pytest.mark.asyncio
async def test_plain_talk_is_not_flagged() -> None:
    orchestrator, _, _, _ = make(
        [[text_chunk("삼송동은 고양시 덕양구에 있어요.")]], registry=_registry([])
    )
    orchestrator._logger = AsyncMock()

    await voice_turn(orchestrator, "삼송동이 어디야")

    assert "action_claim_without_tool" not in dict(_events(orchestrator._logger))
