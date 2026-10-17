"""
브라우저 조작 보조 (실측 2026-10-17: 로컬 LLM 이 크롬으로 사이트를 열고 작업하지 못함)

- 주소 정리: 모델이 'newtab' · 'naver.com' · '네이버' 처럼 주면 열 수 있는 주소로
- 페이지 구조 요약: 네이버 첫 화면 구조는 27,518토큰(문맥 16k 보다 큼)이라
  1,500토큰에서 잘렸다.
  입력칸·버튼·링크만 [ref] 와 함께 짧게 추려 LLM 이 ref 로 다루게 한다.
"""

import json

import pytest

from shared.browser_assist import compact_snapshot, normalize_url

SNAPSHOT = """### Page
- Page URL: https://www.naver.com/
- Page Title: NAVER
### Snapshot
```yaml
- generic [ref=e1]:
  - link "상단영역 바로가기" [ref=e2] [cursor=pointer]:
    - /url: "#topAsideButton"
  - search [ref=e56]:
    - group "검색" [ref=e57]:
      - combobox "검색어를 입력해 주세요." [active] [ref=e60]
      - button "AI 검색" [ref=e61] [cursor=pointer]
  - img "NAVER" [ref=e50]
  - link "카페" [ref=e90] [cursor=pointer]:
    - /url: https://section.cafe.naver.com
```
"""


@pytest.mark.parametrize(
    "given, expected",
    [
        ("newtab", "about:blank"),
        ("", "about:blank"),
        ("chrome://newtab", "about:blank"),
        ("naver.com", "https://naver.com"),
        ("https://www.daum.net", "https://www.daum.net"),
        ("네이버", "https://www.naver.com"),
        ("네이버 카페", "https://section.cafe.naver.com"),
        ("유튜브", "https://www.youtube.com"),
    ],
)
def test_should_turn_model_guesses_into_openable_urls(given, expected) -> None:
    assert normalize_url(given) == expected


def test_unknown_words_become_a_search() -> None:
    assert normalize_url("엣지보이스 깃허브").startswith(
        "https://search.naver.com/search.naver?query="
    )


def test_compact_snapshot_lists_inputs_first_with_refs() -> None:
    text = compact_snapshot(SNAPSHOT)

    lines = text.splitlines()
    assert lines[0].startswith("- Page URL: https://www.naver.com/")
    assert '- combobox "검색어를 입력해 주세요." [ref=e60]' in lines
    assert lines.index('- combobox "검색어를 입력해 주세요." [ref=e60]') < lines.index(
        '- link "카페" [ref=e90]'
    )
    assert "/url" not in text and "img" not in text and "generic" not in text


def test_compact_snapshot_is_short_for_huge_pages() -> None:
    huge = (
        "```yaml\n"
        + "\n".join(f'- link "기사 {i}" [ref=e{i}]' for i in range(3000))
        + "\n```"
    )

    text = compact_snapshot(huge)

    assert len(text.splitlines()) <= 80


@pytest.mark.asyncio
async def test_tool_loop_normalizes_arguments_before_confirm_and_run() -> None:
    from shared.tool_calling import stream_with_tools
    from shared.tools import Tool, ToolRegistry, ToolResult

    ran = []

    async def navigate(args):
        ran.append(args)
        return ToolResult("ok")

    registry = ToolRegistry(
        [
            Tool(
                "browser__browser_navigate",
                "열기",
                {"type": "object"},
                navigate,
                normalize=lambda a: {**a, "url": normalize_url(a.get("url", ""))},
            )
        ]
    )

    def call(url):
        return {
            "choices": [
                {
                    "delta": {
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "c1",
                                "type": "function",
                                "function": {
                                    "name": "browser__browser_navigate",
                                    "arguments": json.dumps({"url": url}),
                                },
                            }
                        ]
                    }
                }
            ]
        }

    responses = [[call("newtab")], [{"choices": [{"delta": {"content": "열었어요."}}]}]]

    async def llm(messages, tools, tool_choice=None):
        for item in responses.pop(0):
            yield item

    events = [
        e
        async for e in stream_with_tools(
            llm, [{"role": "user", "content": "크롬 열어"}], registry
        )
        if isinstance(e, dict)
    ]

    assert ran == [{"url": "about:blank"}]
    assert json.loads(events[0]["arguments"]) == {"url": "about:blank"}


@pytest.mark.asyncio
async def test_page_changing_tools_get_elements_with_refs_attached() -> None:
    from shared.browser_assist import with_page_elements
    from shared.tools import ToolResult

    async def snapshot():
        return ToolResult(SNAPSHOT)

    result = await with_page_elements(
        "browser_navigate", ToolResult("- Page URL: https://www.naver.com/"), snapshot
    )

    assert "[ref=e60]" in result.content and "target" in result.content
    assert len(result.content) < len(SNAPSHOT) * 2


@pytest.mark.asyncio
async def test_snapshot_tool_result_itself_is_compacted() -> None:
    from shared.browser_assist import with_page_elements
    from shared.tools import ToolResult

    async def never():
        raise AssertionError("스냅샷 도구는 다시 찍지 않는다")

    result = await with_page_elements("browser_snapshot", ToolResult(SNAPSHOT), never)

    assert "[ref=e60]" in result.content and "/url" not in result.content


@pytest.mark.asyncio
async def test_errors_and_other_tools_are_left_alone() -> None:
    from shared.browser_assist import with_page_elements
    from shared.tools import ToolResult

    async def never():
        raise AssertionError

    error = ToolResult("Error: x", is_error=True)
    assert await with_page_elements("browser_type", error, never) is error
    other = ToolResult("탭 목록")
    assert await with_page_elements("browser_tabs", other, never) is other


def test_browser_tasks_get_enough_tool_rounds() -> None:
    # 열기 → 입력 → 결과 확인만 해도 3번을 넘는다(실측: 3번 한도에서 입력 전에 끝남)
    from shared.tool_calling import MAX_TOOL_ROUNDS

    assert MAX_TOOL_ROUNDS >= 8


def _registry_with_browser(ran):
    from shared.tools import Tool, ToolRegistry, ToolResult

    async def run(args):
        ran.append(args)
        return ToolResult("ok")

    return ToolRegistry(
        [
            Tool(
                "browser__browser_navigate",
                "열기",
                {"type": "object"},
                run,
                normalize=lambda a: {**a, "url": normalize_url(a.get("url", ""))},
            ),
            Tool("browser__browser_type", "입력", {"type": "object"}, run),
        ]
    )


def test_site_named_in_question_wins_over_a_wrong_url() -> None:
    # 실측: '크롬으로 다음에 들어가서…' 에 모델이 'https://kr金钱兑换器' 를 열려 했다
    from shared.browser_assist import adapt_to_question

    registry = adapt_to_question(
        _registry_with_browser([]), "크롬으로 다음에 들어가서 환율 검색해 줘"
    )
    navigate = registry.get("browser__browser_navigate")

    assert (
        navigate.normalize({"url": "https://kr金钱兑换器"})["url"]
        == "https://www.daum.net"
    )
    # 그 사이트 안의 주소(검색 결과 등)는 그대로 둔다
    kept = "https://search.daum.net/search?q=환율"
    assert navigate.normalize({"url": kept})["url"] == kept


def test_search_request_submits_typed_text() -> None:
    # 실측: 검색창에 입력만 하고 submit=false 라 검색되지 않았다
    from shared.browser_assist import adapt_to_question

    registry = adapt_to_question(
        _registry_with_browser([]), "네이버 검색창에 EdgeVoice 입력하고 검색해 줘"
    )
    typed = registry.get("browser__browser_type").normalize(
        {"target": "e37", "text": "EdgeVoice", "submit": False}
    )

    assert typed["submit"] is True


@pytest.mark.asyncio
async def test_failed_tool_is_disclosed_when_answer_claims_success() -> None:
    # 실측: 주소 열기·입력이 모두 실패했는데 '검색했습니다' 라고 답했다
    from shared.tool_calling import stream_with_tools
    from shared.tools import Tool, ToolRegistry, ToolResult

    async def broken(args):
        return ToolResult("Error: net::ERR_NAME_NOT_RESOLVED", is_error=True)

    registry = ToolRegistry(
        [Tool("browser__browser_navigate", "열기", {"type": "object"}, broken)]
    )
    call = {
        "choices": [
            {
                "delta": {
                    "tool_calls": [
                        {
                            "index": 0,
                            "id": "c1",
                            "type": "function",
                            "function": {
                                "name": "browser__browser_navigate",
                                "arguments": "{}",
                            },
                        }
                    ]
                }
            }
        ]
    }
    responses = [
        [call],
        [{"choices": [{"delta": {"content": "다음에서 검색했습니다."}}]}],
    ]

    async def llm(messages, tools, tool_choice=None):
        for item in responses.pop(0):
            yield item

    text = "".join(
        [
            e
            async for e in stream_with_tools(
                llm, [{"role": "user", "content": "q"}], registry
            )
            if isinstance(e, str)
        ]
    )

    assert text.startswith("다음에서 검색했습니다.")
    assert "실패" in text and "ERR_NAME_NOT_RESOLVED" in text


def test_type_target_is_fixed_to_a_real_input_on_the_current_page() -> None:
    # 실측: 다음에서 '[ref=e60]'(네이버 기억), 유튜브에서 '#search-box'(없는 요소)로
    # 입력해 실패
    from shared.browser_assist import BrowserState

    state = BrowserState()
    state.update(SNAPSHOT)

    assert (
        state.fix_type_target({"target": "[ref=e60]", "text": "x"})["target"] == "e60"
    )
    assert (
        state.fix_type_target({"target": "#search-box", "text": "x"})["target"] == "e60"
    )
    # 입력칸이 아닌 요소(링크 e90)에는 입력할 수 없다.
    # 실측: 다른 사이트에서 기억한 'e60' 이 이 페이지에선 입력칸이 아니라
    # 'Ref e60 not found' 로 실패
    assert state.fix_type_target({"target": "e90", "text": "x"})["target"] == "e60"


def test_frame_prefixed_refs_are_understood() -> None:
    # 실측: 같은 브라우저를 여러 연결이 쓰자 ref 가 'e60' 이 아니라 'f57e2' 꼴로 나왔고,
    # 'e숫자' 만 알아보던 요약이 비어 입력 대상 보정도 동작하지 않았다
    from shared.browser_assist import BrowserState

    snapshot = SNAPSHOT.replace("[ref=e", "[ref=f57e")
    state = BrowserState()
    state.update(snapshot)

    combobox = '- combobox "검색어를 입력해 주세요." [ref=f57e60]'
    assert combobox in compact_snapshot(snapshot)
    assert state.inputs == ["f57e60"]
    assert state.fix_type_target({"target": "[ref=f57e60]"})["target"] == "f57e60"
    assert state.fix_type_target({"target": "e60"})["target"] == "f57e60"


def test_click_target_only_drops_ref_brackets() -> None:
    from shared.browser_assist import BrowserState

    state = BrowserState()
    state.update(SNAPSHOT)

    assert state.fix_click_target({"target": "[ref=e90]"})["target"] == "e90"
    assert state.fix_click_target({"target": "a.cafe"})["target"] == "a.cafe"


@pytest.mark.asyncio
async def test_page_elements_update_browser_state() -> None:
    from shared.browser_assist import BrowserState, with_page_elements
    from shared.tools import ToolResult

    state = BrowserState()

    async def snapshot():
        return ToolResult(SNAPSHOT)

    await with_page_elements("browser_navigate", ToolResult("ok"), snapshot, state)

    assert state.inputs == ["e60"] and "e90" in state.refs


def test_submit_keeps_the_target_fix() -> None:
    from shared.browser_assist import adapt_to_question
    from shared.tools import Tool, ToolRegistry, ToolResult

    async def run(args):
        return ToolResult("ok")

    registry = ToolRegistry(
        [
            Tool(
                "browser__browser_type",
                "입력",
                {"type": "object"},
                run,
                normalize=lambda a: {**a, "target": "e60"},
            )
        ]
    )
    typed = adapt_to_question(registry, "검색해 줘").get("browser__browser_type")

    assert typed.normalize({"target": "#x"}) == {"target": "e60", "submit": True}
