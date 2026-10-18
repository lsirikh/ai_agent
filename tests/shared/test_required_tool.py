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
    required_tools,
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


@pytest.mark.parametrize(
    "question",
    [
        # 실측 실패 문장(STT 가 '들어가 줘' 를 '들어가죠' 로 적었다)
        "웹페이지 열어가지고 네이버 카페 들어가죠",
        "크롬 페이지 열어줘",
        # '날씨' 가 있어도 크롬·사이트를 말했으면 브라우저 (실측: 날씨 도구로 갔다)
        "크롬으로 네이버에 들어가서 검색창에 오늘 날씨를 입력하고 검색해 줘",
        "유튜브 들어가서 음악 틀어 줘",
    ],
)
def test_spoken_browser_requests_use_browser(question) -> None:
    assert required_tool(question, BROWSER) == "browser__browser_navigate"


def test_plain_weather_question_still_uses_weather() -> None:
    assert required_tool("오늘 서울 날씨 어때?", BROWSER) == "get_weather"


def test_spoken_open_request_without_browser_is_admitted() -> None:
    reply = unavailable_action_reply("웹페이지 열어가지고 네이버 카페 들어가죠", ALL)
    assert reply and "없" in reply


BROWSER_ALL = BROWSER + ["browser__browser_type", "browser__browser_click"]


def test_browser_search_is_planned_as_open_then_type() -> None:
    # 실측: 열기만 지정하면 그다음에 입력하지 않고 '입력하고 검색했습니다' 라고 지어냈다
    assert required_tools(
        "크롬으로 네이버에 들어가서 검색창에 EdgeVoice 를 입력하고 검색해 줘",
        BROWSER_ALL,
    ) == ["browser__browser_navigate", "browser__browser_type"]


def test_click_request_adds_click_step() -> None:
    assert required_tools("네이버 들어가서 카페 메뉴 눌러 줘", BROWSER_ALL) == [
        "browser__browser_navigate",
        "browser__browser_click",
    ]


def test_plain_open_is_one_step_and_others_unchanged() -> None:
    assert required_tools("크롬 열어줘", BROWSER_ALL) == ["browser__browser_navigate"]
    assert required_tools("오늘 서울 날씨 어때?", BROWSER_ALL) == ["get_weather"]
    assert required_tools("안녕?", BROWSER_ALL) == []


@pytest.mark.asyncio
async def test_tool_loop_follows_the_plan_round_by_round() -> None:
    llm = RecordingLLM(
        [_call("get_weather", '{"location": "부산"}')],
        [_call("get_weather", '{"location": "서울"}')],
        [_text("끝.")],
    )

    async for _ in stream_with_tools(
        llm, [{"role": "user", "content": "q"}], _weather_registry(),
        required=["get_weather", "get_weather"],
    ):
        pass

    assert llm.choices == ["get_weather", "get_weather", None]


@pytest.mark.parametrize(
    "question, expected",
    [
        # 실측: 검색 없이 '원당시장(동작구 원당동)' 이라고 지어냈다. '알아?' 질문은
        # 프롬프트 규칙을 더해도 1/4 만 검색했다
        ("원당시장에 있는 세계로마트 알아?", "web_search"),
        ("원당 시장에 대해 알려줘", "web_search"),
        ("고양시 화정역 근처 맛집 알려줘", "web_search"),
        ("이 근처 병원 어디 있어?", "web_search"),
        # 실측(2026-10-18): '좋은 날' 을 '2008년 5월 8일 발매한 10번째 싱글' 이라고
        # 지어냈다(실제 2010년 12월) — 노래·영화·책·인물 정보도 검색한다
        ("아이유 좋은 날 어떤 노래야?", "web_search"),
        ("영화 기생충 알아?", "web_search"),
        ("뉴진스 멤버 알려줘", "web_search"),
        # 검색하지 않는다: 일반 상식·개인 질문·인사·말버릇
        ("파이썬이 뭐야?", None),
        ("내 이름 뭐야?", None),
        ("너 나 알아?", None),
        ("안녕, 반가워", None),
        ("역시 대단해", None),
        ("오늘 날씨 알려줘", "get_weather"),
    ],
)
def test_specific_facts_are_searched_before_answering(question, expected) -> None:
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


@pytest.mark.parametrize(
    "question, expected",
    [
        # 시나리오 시험(2026-10-18): '다음'·'깃허브' 를 사이트로 보지 않았다
        ("다음 열어줘", ["browser__browser_navigate"]),
        ("다음 띄워 줘", ["browser__browser_navigate"]),
        ("깃허브 열어줘", ["browser__browser_navigate"]),
        ("다음에서 맛집 검색해줘",
         ["browser__browser_navigate", "browser__browser_type"]),
        ("다음에서 오늘 날씨 검색해줘",
         ["browser__browser_navigate", "browser__browser_type"]),
        # '다음' 이 사이트가 아닐 때는 그대로
        ("다음 단계 알려줘", []),
        ("다음에 또 보자", []),
        ("롯데월드 어때?", ["web_search"]),
        ("인천공항 정보 알려줘", ["web_search"]),
    ],
)
def test_daum_github_and_landmarks(question, expected) -> None:
    offered = [
        "get_weather", "web_search", "browser__browser_navigate",
        "browser__browser_type", "browser__browser_click",
    ]
    assert required_tools(question, offered) == expected


@pytest.mark.parametrize(
    "question, expected",
    [
        # 시나리오 시험(2026-10-18): 올해·오늘의 사실을 검색 없이 답했다
        ("올해 노벨 문학상 수상자는?", ["web_search"]),
        ("오늘 코스피 지수 알려줘", ["web_search"]),
        ("요즘 유행하는 노래 알려줘", ["web_search"]),
        # 시각·날짜·날씨 질문은 그대로
        ("오늘 며칠이야?", []),
        ("오늘 무슨 요일이야?", []),
        ("오늘 서울 날씨 어때?", ["get_weather"]),
        # 시나리오 시험: 기분을 말한 것까지 날씨 도구로 보냈다
        ("비가 와서 우울해", []),
        ("눈이 와서 기분 좋아", []),
        # 오늘·요즘이 들어가도 기분·일상 이야기는 검색하지 않는다
        ("오늘 기분이 좀 안 좋아", []),
        ("오늘 하루 어땠어?", []),
        ("요즘 너무 피곤해", []),
        # 시나리오 시험(2026-10-18): 추천·제안을 바라는 말을 사실 검색으로 보냈다
        ("오늘 점심 뭐 먹을까?", []),
        ("오늘 뭐 할까?", []),
        ("요즘 볼 만한 거 추천해 줘", []),
    ],
)
def test_current_facts_search_and_moods_skip_weather(question, expected) -> None:
    offered = ["get_weather", "web_search", "get_time"]
    assert required_tools(question, offered) == expected


def test_weather_question_without_weather_tool_is_answered_honestly() -> None:
    # 시나리오 시험: 날씨 스킬을 끄자 '강수 확률 100%' 라고 날씨를 지어냈다
    reply = unavailable_action_reply("서울 날씨 어때?", ["get_time"])

    assert reply and "날씨" in reply
    assert unavailable_action_reply("서울 날씨 어때?", ["get_weather"]) is None
    # 검색할 수 있으면 검색으로 찾는다
    assert unavailable_action_reply("서울 날씨 어때?", ["web_search"]) is None
    assert required_tools("서울 날씨 어때?", ["web_search"]) == ["web_search"]
