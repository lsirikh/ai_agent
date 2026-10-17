"""
분명히 도구가 필요한 질문은 첫 요청에서 그 도구를 지정한다 (실측 2026-10-17)

같은 질문에 도구 없이 답한 기록이 세션에 있으면 Qwen2.5-7B 는 tool_choice=auto 에서
도구를 부르지 않고 옛 답을 베꼈다(날씨 "최저 -15°C, 최고 45°C", 뉴스 지어내기).
기록 6턴·프롬프트 규칙으로도 0/8. 이름을 지정하면 기록이 있어도 도구와 인자를 맞게 냈다.
"""

import pytest

from shared.tool_calling import stream_with_tools
from shared.tools import (
    Tool,
    ToolRegistry,
    ToolResult,
    required_tool,
    unavailable_action_reply,
)

ALL = ["get_time", "get_weather", "web_fetch", "web_search"]


@pytest.mark.parametrize(
    "question, expected",
    [
        ("오늘 서울 날씨 어때?", "get_weather"),
        ("부산은 지금 비 와?", "get_weather"),
        ("내일 제주 우산 챙겨야 해?", "get_weather"),
        ("지금 기온 몇 도야?", "get_weather"),
        ("인터넷에서 오늘 주요 뉴스 하나 찾아 줘", "web_search"),
        ("엔비디아 최신 GPU 검색해 줘", "web_search"),
        ("안녕?", None),
        ("윤하람 소속사 어디야?", None),
        ("지금 몇 시야?", None),
    ],
)
def test_should_pick_tool_the_question_clearly_needs(question, expected) -> None:
    assert required_tool(question, ALL) == expected


BROWSER = ALL + ["browser__browser_navigate", "browser__browser_snapshot"]


@pytest.mark.parametrize(
    "question",
    [
        "크롬 켜서 네이버 들어가",
        "크롬 켜줘.",
        "인터넷으로 네이버 들어가 줄 수 있어?",
        "브라우저로 다음 사이트 열어 줘",
    ],
)
def test_should_force_browser_for_open_requests(question) -> None:
    # 실측: 브라우저 도구 없이 "크롬을 열었고, 네이버에 접속했습니다" 라고 지어냈다
    assert required_tool(question, BROWSER) == "browser__browser_navigate"
    assert unavailable_action_reply(question, BROWSER) is None


@pytest.mark.parametrize(
    "question",
    ["크롬 켜줘.", "인터넷으로 네이버 들어가 줄 수 있어?", "메모장 열어 줘"],
)
def test_should_admit_it_cannot_open_without_a_tool(question) -> None:
    # 실측: 프롬프트로 막아도 기록을 따라 12번 중 8번 "열었습니다" 라고 지어냈다
    reply = unavailable_action_reply(question, ALL)
    assert reply and "없" in reply


@pytest.mark.parametrize(
    "question",
    [
        "오늘 날씨 알려줘",
        "접속 방법 알려줘",
        "창문 열어도 돼?",
        "네이버 뉴스 검색해 줘",
    ],
)
def test_should_not_block_questions_that_are_not_open_requests(question) -> None:
    assert unavailable_action_reply(question, ALL) is None


DESKTOP = ALL + ["desktop__open_app", "desktop__write_document"]


@pytest.mark.parametrize(
    "question, expected",
    [
        ("메모장 열어 줘", "desktop__open_app"),
        ("엑셀 실행해 줘", "desktop__open_app"),
        ("워드 켜줘", "desktop__open_app"),
        ("메모장에 장보기 목록 써서 저장해 줘", "desktop__write_document"),
        ("엑셀로 가계부 만들어서 저장해", "desktop__write_document"),
        ("워드에 회의록 작성해 줘", "desktop__write_document"),
    ],
)
def test_should_use_desktop_tools_for_programs(question, expected) -> None:
    # 사용자 요청: 로컬 LLM 이 메모장·워드·엑셀을 실행하고 저장한다
    assert required_tool(question, DESKTOP) == expected
    assert unavailable_action_reply(question, DESKTOP) is None


FILES = DESKTOP + ["desktop__list_test_files", "desktop__read_test_file"]


@pytest.mark.parametrize(
    "question, expected",
    [
        ("Tests 폴더에 저장된 파일 목록 알려 줘", "desktop__list_test_files"),
        ("저장된 파일 뭐 있어?", "desktop__list_test_files"),
        ("할일목록.txt 내용 읽어 줘", "desktop__read_test_file"),
        ("매출표.xlsx 파일 내용 보여 줘", "desktop__read_test_file"),
    ],
)
def test_should_check_saved_files_with_tools(question, expected) -> None:
    # 실측: 도구 없이 파일 목록을 지어냈다(있는 장보기.txt 가 빠짐)
    assert required_tool(question, FILES) == expected


def test_should_admit_it_cannot_save_without_desktop_tools() -> None:
    reply = unavailable_action_reply("메모장에 장보기 목록 저장해 줘", ALL)
    assert reply and "없" in reply


def test_should_not_require_tool_that_is_not_offered() -> None:
    # 인터넷 도구가 꺼져 있으면 날씨·검색 도구가 없다
    assert required_tool("오늘 서울 날씨 어때?", ["get_time"]) is None
    assert required_tool("뉴스 검색해 줘", ["get_time"]) is None


class RecordingLLM:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.choices = []

    async def __call__(self, messages, tools, tool_choice=None):
        self.choices.append(tool_choice)
        for item in self.responses.pop(0):
            yield item


def _call(name, arguments):
    return {
        "choices": [
            {
                "delta": {
                    "tool_calls": [
                        {
                            "index": 0,
                            "id": "call_1",
                            "type": "function",
                            "function": {"name": name, "arguments": arguments},
                        }
                    ]
                }
            }
        ]
    }


def _text(text):
    return {"choices": [{"delta": {"content": text}}]}


def _weather_registry():
    async def weather(args):
        return ToolResult(f"{args.get('location')} 맑음")

    return ToolRegistry([Tool("get_weather", "날씨", {"type": "object"}, weather)])


@pytest.mark.asyncio
async def test_should_force_required_tool_only_on_first_round() -> None:
    llm = RecordingLLM(
        [_call("get_weather", '{"location": "부산"}')], [_text("맑아요.")]
    )

    text = ""
    async for item in stream_with_tools(
        llm, [{"role": "user", "content": "부산 날씨"}], _weather_registry(),
        required="get_weather",
    ):
        if isinstance(item, str):
            text += item

    assert text == "맑아요."
    assert llm.choices == ["get_weather", None]


@pytest.mark.asyncio
async def test_should_ignore_required_tool_missing_from_registry() -> None:
    llm = RecordingLLM([_text("안녕하세요.")])

    async for _ in stream_with_tools(
        llm, [{"role": "user", "content": "hi"}], _weather_registry(),
        required="web_search",
    ):
        pass

    assert llm.choices == [None]
