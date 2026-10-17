"""
유튜브에서 노래·영상 틀기
(사용자 보고 2026-10-18: '유튜브에서 아이유 좋은 날 틀어 줘' 를 못 했다)

실측: 로컬 LLM 이 검색 결과에서 동영상 링크(e123) 대신 바로 뒤의 '채널로 이동'
링크를 눌러 채널로 갔고, 다시 검색하다 끝났다. 자주 쓰는 일이라 전용 도구로
검색 결과의 첫 동영상을 확실히 연다(LLM 은 도구와 검색어만 고른다).
"""

import os
from types import SimpleNamespace

import pytest

from shared.browser_assist import first_video
from shared.mcp_client import MCPManager, MCPServerConfig
from shared.tools import ToolResult, required_tools

FIXTURE = os.path.join(
    os.path.dirname(__file__), "fixtures", "youtube_results_snapshot.yml"
)


def test_first_video_skips_channel_links() -> None:
    snapshot = open(FIXTURE, encoding="utf-8").read()

    ref, title = first_video(snapshot)

    assert ref == "e123"
    assert title.startswith("IU (아이유) _ Good Day (좋은 날) _ MV")


def test_no_video_on_page() -> None:
    assert first_video('- link "YouTube 홈" [ref=e12]') == (None, None)


def test_playing_on_youtube_is_one_tool() -> None:
    offered = ["browser__browser_navigate", "browser__play_youtube", "get_time"]

    for question in (
        "유튜브에서 아이유의 좋은 날 틀어줘",
        "크롬으로 유튜브 열어서 아이유 좋은 날 재생해 줘",
        "유튜브 가서 뉴진스 하입보이 플레이해",
    ):
        assert required_tools(question, offered) == ["browser__play_youtube"]

    assert required_tools("유튜브 열어 줘", offered) == ["browser__browser_navigate"]


class FakeBrowser:
    """브라우저 MCP 흉내: 이동한 주소와 누른 대상을 기록한다."""

    def __init__(self, snapshot, after_click_url):
        self.calls = []
        self.snapshot = snapshot
        self.url = ""
        self.after_click_url = after_click_url

    async def call_tool(self, name, args):
        self.calls.append((name, args))
        if name == "browser_navigate":
            self.url = args["url"]
            text = f"- Page URL: {self.url}"
        elif name == "browser_click":
            self.url = self.after_click_url
            text = f"- Page URL: {self.url}"
        else:
            text = self.snapshot.replace(
                "- Page URL: https://www.youtube.com/results",
                f"- Page URL: {self.url}#",
            )
        return SimpleNamespace(
            content=[SimpleNamespace(text=text)], is_error=False
        )


def _manager(browser):
    manager = MCPManager([MCPServerConfig(
        name="browser", url="http://x/mcp", trusted=True,
        allowed_tools=["browser_navigate", "browser_snapshot", "browser_click"],
    )])
    server = manager.servers[0]
    server.client, server.stale = browser, False
    server.tools = [
        SimpleNamespace(name=n, description=n, input_schema={}, annotations=None)
        for n in ("browser_navigate", "browser_snapshot", "browser_click")
    ]
    return manager


@pytest.mark.asyncio
async def test_play_youtube_searches_and_clicks_first_video() -> None:
    browser = FakeBrowser(
        open(FIXTURE, encoding="utf-8").read(), "https://www.youtube.com/watch?v=jeqdYqsrsA0"
    )
    tools = {t.name: t for t in await _manager(browser).tools()}

    result = await tools["browser__play_youtube"].run({"query": "아이유 좋은 날"})

    assert isinstance(result, ToolResult) and result.is_error is False
    assert "Good Day" in result.content
    navigate = browser.calls[0]
    assert navigate[0] == "browser_navigate"
    assert "search_query=%EC%95%84" in navigate[1]["url"]
    assert ("browser_click", {"element": navigate and result.content.split("'")[1],
                              "target": "e123"}) in browser.calls
    assert tools["browser__play_youtube"].needs_confirm is False


@pytest.mark.asyncio
async def test_play_youtube_reports_failure_when_video_did_not_open() -> None:
    browser = FakeBrowser(open(FIXTURE, encoding="utf-8").read(), "https://www.youtube.com/@1theK")
    tools = {t.name: t for t in await _manager(browser).tools()}

    result = await tools["browser__play_youtube"].run({"query": "아이유 좋은 날"})

    assert result.is_error is True


def test_drawing_request_uses_draw_picture() -> None:
    # 실측(2026-10-18): '그림판 열어서 강아지 그려 줘' 를 못 했다(그리는 도구가 없었다)
    offered = ["desktop__open_app", "desktop__draw_picture", "desktop__write_document"]

    for question in (
        "그림판 열어서 강아지 그림 그려줘",
        "그림판에 고양이 그려 줘",
        "강아지 그림 그려 줘",
    ):
        assert required_tools(question, offered) == ["desktop__draw_picture"]

    assert required_tools("그림판 열어 줘", offered) == ["desktop__open_app"]


@pytest.mark.asyncio
async def test_list_argument_given_as_json_text_is_parsed() -> None:
    # 실측: 로컬 LLM 이 shapes 를 '[{"type": ...}]' 글로 넘겨 검증 오류가 났다
    manager = MCPManager([MCPServerConfig(
        name="desktop", url="http://x/mcp", trusted=True,
        allowed_tools=["draw_picture"],
    )])
    server = manager.servers[0]
    server.client, server.stale = object(), False
    server.tools = [SimpleNamespace(
        name="draw_picture", description="그리기", annotations=None,
        input_schema={"type": "object", "properties": {
            "shapes": {"type": "array", "items": {"type": "object"}},
            "title": {"type": "string"},
        }},
    )]
    (tool,) = [t for t in await manager.tools() if t.name == "desktop__draw_picture"]

    fixed = tool.normalize({"shapes": '[{"type": "circle"}]', "title": "[강아지]"})

    assert fixed == {"shapes": [{"type": "circle"}], "title": "[강아지]"}
