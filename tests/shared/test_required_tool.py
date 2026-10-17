"""
분명히 도구가 필요한 질문은 첫 요청에서 그 도구를 지정한다 (실측 2026-10-17)

같은 질문에 도구 없이 답한 기록이 세션에 있으면 Qwen2.5-7B 는 tool_choice=auto 에서
도구를 부르지 않고 옛 답을 베꼈다(날씨 "최저 -15°C, 최고 45°C", 뉴스 지어내기).
기록 6턴·프롬프트 규칙으로도 0/8. 이름을 지정하면 기록이 있어도 도구와 인자를 맞게 냈다.
"""

import pytest

from shared.tool_calling import stream_with_tools
from shared.tools import Tool, ToolRegistry, ToolResult, required_tool

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
