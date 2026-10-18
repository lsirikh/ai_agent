"""
크롬·유튜브를 하라고 했는데 '하겠다' 고만 하고 하지 않던 문제
(사용자 보고 2026-10-19, 대화 기록 10-18 20:23 ~ 10-19 07:10 분석)

- '크롬 자체를 종료시켜' · '켜져있거든 … 크롬도 꺼!' 가 '종료시켜'·'켜져' 의 '켜' 때문에
  열기(browser_navigate)로 강제돼 about:blank 로 가 놓고 '종료했습니다' 라고 답했다
- '유튜브 꺼줘' · '영상 재생해' · '광고 건너뛰기 버튼 클릭해줘' 는 정해진 도구가 없어
  모델(auto)이 도구를 부르지 않고 '했습니다/하겠습니다' 라고만 했다
- 크롬을 닫는 도구가 없었다(browser_close 는 공유 브라우저라 실패)
"""

from shared.tools import (
    ANY_TOOL,
    CANNOT_DO_REPLY,
    required_tools,
    unavailable_action_reply,
)

OFFERED = [
    "browser__browser_click", "browser__browser_close",
    "browser__browser_navigate", "browser__browser_snapshot",
    "browser__browser_tabs", "browser__browser_type",
    "browser__play_youtube", "browser__close_browser",
    "browser__skip_youtube_ad",
    "desktop__open_app", "desktop__press_keys", "get_time", "web_search",
]


def test_closing_chrome_uses_close_browser_not_navigate() -> None:
    for question in (
        "이상한 소리 하지 말고 그냥 크롬 끄라고 크롬 자체를 종료시켜",
        "무슨 뻘소리 하지 말고 지금 크롬 브라우저 그대로 켜져있거든"
        " 유튜브 꺼! 크롬도 꺼!",
        "크롬 브라우저를 종료시켜달라고 털미네이트 프로그램 털미네이트",
        "Alt F4 눌러서 크롬 종료시켜.",
        "유튜브 꺼줘",
        "크롬 닫아 줘",
    ):
        assert required_tools(question, OFFERED) == ["browser__close_browser"], question


def test_opening_is_still_navigate() -> None:
    assert required_tools("크롬 켜 줘", OFFERED) == ["browser__browser_navigate"]
    assert required_tools("네이버 열어줘", OFFERED) == ["browser__browser_navigate"]


def test_play_said_as_teulgo_plays_on_youtube() -> None:
    # 10-19 07:10: '틀고' 를 틀기로 보지 않아 검색 결과만 열고
    # '재생할 수 있는 상태' 라고 답했다
    question = "인터넷 들어가서 유튜브 들어가서 아이유의 반편지 틀고"

    assert required_tools(question, OFFERED) == ["browser__play_youtube"]


def test_skipping_an_ad_uses_its_tool() -> None:
    for question in (
        "그 크롬 브라우저에서 유튜브 밑에 광고 건너뛰기라고 버튼 나오거든"
        " 그거 누를 수 있냐고",
        "광고 건너뛰어 줘",
        "광고 스킵해",
    ):
        plan = required_tools(question, OFFERED)
        assert plan == ["browser__skip_youtube_ad"], question


def test_playing_with_an_ad_skip_skips_after_playing() -> None:
    question = "유튜브에서 아이유 밤편지 틀고 광고 나오면 건너뛰어 줘"

    assert required_tools(question, OFFERED) == [
        "browser__play_youtube", "browser__skip_youtube_ad"
    ]


def test_follow_up_after_using_the_browser_is_a_browser_request() -> None:
    # 앞 턴에 브라우저를 썼으면 사이트 이름 없이 말해도 브라우저 일이다
    assert required_tools("영상 재생해", OFFERED, browser_active=True) == [
        "browser__play_youtube"
    ]
    assert required_tools("꺼 줘", OFFERED, browser_active=True) == [
        "browser__close_browser"
    ]
    assert required_tools(
        "아이유에 반편집 클릭하고 광고 건너뛰기 나오면은 그 버튼 클릭해줘",
        OFFERED, browser_active=True,
    ) == ["browser__browser_snapshot", "browser__browser_click",
          "browser__skip_youtube_ad"]
    # 정할 도구가 없는 브라우저 일은 아무 도구라도 부르게 한다(말만 하지 않게)
    assert required_tools("검색창에 날씨 입력해", OFFERED, browser_active=True) == [
        "browser__browser_snapshot", "browser__browser_type"
    ]
    assert required_tools("뒤로 가 줘", OFFERED, browser_active=True) == [ANY_TOOL]


def test_without_the_browser_follow_ups_are_left_to_the_model() -> None:
    assert required_tools("영상 재생해", OFFERED) == []
    assert required_tools("꺼 줘", OFFERED) == []


def test_talk_that_is_not_a_browser_request_is_not_forced() -> None:
    # 방 안의 다른 사람 말·잡담은 브라우저를 쓴 뒤라도 도구로 보내지 않는다
    for question in (
        "자동차 정리해 빨리 정리 안해봐",
        "조용히 좀 해줘",
        "방금 뭐라고 그랬어?",
        "고양시 삼송동에 대해서 알려줘",
    ):
        assert ANY_TOOL not in required_tools(question, OFFERED, browser_active=True)
        assert "browser__close_browser" not in required_tools(
            question, OFFERED, browser_active=True
        )


def test_closing_without_a_close_tool_says_it_cannot() -> None:
    offered = ["get_time", "web_search"]

    assert unavailable_action_reply("크롬 꺼 줘", offered) == CANNOT_DO_REPLY


def test_any_tool_plan_asks_the_model_to_call_some_tool() -> None:
    import asyncio

    from shared.tool_calling import stream_with_tools, tool_choice_for
    from shared.tools import Tool, ToolRegistry, ToolResult

    assert tool_choice_for(ANY_TOOL) == "required"

    async def run(args):
        return ToolResult("뒤로 갔습니다")

    registry = ToolRegistry()
    registry.add(Tool(name="browser__browser_navigate_back", description="뒤로",
                      parameters={"type": "object", "properties": {}}, run=run))
    seen = []

    async def request(messages, tools, tool_choice=None):
        seen.append(tool_choice)
        yield {"choices": [{"delta": {"content": "네"}}]}

    async def collect():
        return [x async for x in stream_with_tools(
            request, [{"role": "user", "content": "뒤로 가 줘"}], registry,
            required=[ANY_TOOL],
        )]

    asyncio.run(collect())

    assert seen[0] == ANY_TOOL
