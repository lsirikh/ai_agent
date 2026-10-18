"""
크롬 닫기 · 유튜브 광고 건너뛰기 · 튼 뒤 실제로 재생 중인지
(사용자 보고 2026-10-19: '크롬 꺼' 를 못 했고, 광고 건너뛰기를 '하겠다' 고만 했다)

실측(EdgeVoice 크롬, Playwright MCP --shared-browser-context):
- browser_close 는 'The browser context is shared … cannot be closed' 로 실패했다
- 마지막 탭을 닫아도 창은 about:blank 로 남았다
- page.context().close() 로는 창이 닫히고, 다음 요청에서 크롬이 다시 열렸다
  (닫히는 도중이라 결과는 'Target page, context or browser has been closed' 오류로 온다)
"""

from types import SimpleNamespace

import pytest

from shared.mcp_client import MCPManager, MCPServerConfig


class FakeBrowser:
    """브라우저 MCP 흉내: 부른 도구를 기록하고 정해 둔 결과를 준다."""

    def __init__(self, replies=None):
        self.calls = []
        self.replies = replies or {}

    async def call_tool(self, name, args):
        self.calls.append((name, args))
        text, error = self.replies.get(name, (f"- Page URL: about:{name}", False))
        return SimpleNamespace(content=[SimpleNamespace(text=text)], is_error=error)


SERVER_TOOLS = (
    "browser_navigate", "browser_snapshot", "browser_click",
    "browser_evaluate", "browser_run_code_unsafe",
)


async def _tools(browser, server_tools=SERVER_TOOLS):
    manager = MCPManager([MCPServerConfig(
        name="browser", url="http://x/mcp", trusted=True,
        allowed_tools=["browser_navigate", "browser_snapshot", "browser_click"],
    )])
    server = manager.servers[0]
    server.client, server.stale = browser, False
    server.tools = [
        SimpleNamespace(name=n, description=n, input_schema={}, annotations=None)
        for n in server_tools
    ]
    return {t.name: t for t in await manager.tools()}


CLOSED = (
    "### Error\nError: browserContext.close: "
    "Target page, context or browser has been closed"
)


@pytest.mark.asyncio
async def test_close_browser_stops_the_page_and_closes_the_window() -> None:
    browser = FakeBrowser({"browser_run_code_unsafe": (CLOSED, True)})
    tools = await _tools(browser)

    result = await tools["browser__close_browser"].run({})

    assert result.is_error is False
    assert "닫았습니다" in result.content
    names = [name for name, _ in browser.calls]
    assert names == ["browser_navigate", "browser_run_code_unsafe"]
    assert browser.calls[0][1] == {"url": "about:blank"}  # 소리부터 멈춘다
    assert "context().close()" in browser.calls[1][1]["code"]
    assert tools["browser__close_browser"].needs_confirm is False


@pytest.mark.asyncio
async def test_close_browser_reports_when_the_window_stays_open() -> None:
    browser = FakeBrowser({"browser_run_code_unsafe": ("### Error\nError: boom", True)})
    tools = await _tools(browser)

    result = await tools["browser__close_browser"].run({})

    assert result.is_error is True
    assert "boom" in result.content


@pytest.mark.asyncio
async def test_no_close_tool_when_the_server_cannot_run_code() -> None:
    tools = await _tools(FakeBrowser(), server_tools=SERVER_TOOLS[:4])

    assert "browser__close_browser" not in tools
    assert "browser__skip_youtube_ad" in tools


@pytest.mark.parametrize(
    "state, is_error, said",
    [
        ('"state:skipped:1"', False, "건너뛰었습니다"),
        ('"state:no_ad"', False, "광고가 나오지 않"),
        ('"state:ad_unskippable:0"', False, "건너뛰기 버튼이 나오지 않"),
        ('"state:no_player"', True, "동영상"),
    ],
)
@pytest.mark.asyncio
async def test_skip_youtube_ad_reports_what_happened(state, is_error, said) -> None:
    browser = FakeBrowser({"browser_evaluate": (f"### Result\n{state}\n", False)})
    tools = await _tools(browser)

    result = await tools["browser__skip_youtube_ad"].run({})

    assert result.is_error is is_error
    assert said in result.content
    name, args = browser.calls[0]
    assert name == "browser_evaluate" and "ytp-skip-ad-button" in args["function"]


@pytest.mark.parametrize(
    "state, said",
    [
        ('"state:ad"', "광고"),
        ('"state:playing"', "재생 중"),
        ('"state:paused"', "멈춰"),
    ],
)
@pytest.mark.asyncio
async def test_play_youtube_says_whether_it_is_really_playing(state, said) -> None:
    snapshot = '- link "아이유 밤편지 4분 14초" [ref=e10]'
    browser = FakeBrowser({
        "browser_snapshot": (snapshot, False),
        "browser_click": ("- Page URL: https://www.youtube.com/watch?v=x", False),
        "browser_evaluate": (f"### Result\n{state}\n", False),
    })
    tools = await _tools(browser)

    result = await tools["browser__play_youtube"].run({"query": "아이유 밤편지"})

    assert result.is_error is False
    assert said in result.content


class ScriptedBrowser(FakeBrowser):
    """browser_evaluate 결과를 차례로 준다(광고 자동 건너뛰기 감시용)."""

    def __init__(self, states, replies=None):
        super().__init__(replies)
        self.states = list(states)

    async def call_tool(self, name, args):
        if name == "browser_evaluate" and "SKIP_ONCE" in args["function"]:
            self.calls.append((name, "once"))
            state = self.states.pop(0) if self.states else "no_player"
            return SimpleNamespace(
                content=[SimpleNamespace(text=f'### Result\n"state:{state}"\n')],
                is_error=False,
            )
        return await super().call_tool(name, args)


@pytest.mark.asyncio
async def test_playing_skips_ads_by_itself_until_the_video_is_gone() -> None:
    # 사용자 요청(2026-10-19): 광고 건너뛰기 버튼이 나오면 말하지 않아도 누른다
    snapshot = '- link "아이유 밤편지 4분 14초" [ref=e10]'
    browser = ScriptedBrowser(
        ["ad_waiting", "ad_waiting", "skipped", "no_ad", "skipped", "no_ad"],
        {
            "browser_snapshot": (snapshot, False),
            "browser_click": ("- Page URL: https://www.youtube.com/watch?v=x", False),
            "browser_evaluate": ('### Result\n"state:ad"\n', False),
        },
    )
    manager = MCPManager([MCPServerConfig(
        name="browser", url="http://x/mcp", trusted=True,
        allowed_tools=["browser_navigate", "browser_snapshot", "browser_click"],
    )])
    server = manager.servers[0]
    server.client, server.stale = browser, False
    server.tools = [
        SimpleNamespace(name=n, description=n, input_schema={}, annotations=None)
        for n in SERVER_TOOLS
    ]
    manager.ad_watch_interval = 0
    tools = {t.name: t for t in await manager.tools()}

    result = await tools["browser__play_youtube"].run({"query": "아이유 밤편지"})
    await manager.ad_watch

    assert "자동으로" in result.content
    checks = [c for c in browser.calls if c == ("browser_evaluate", "once")]
    # 영상이 사라지면(no_player 3번) 그만 본다
    assert len(checks) == 9
    assert manager.ad_watch.done()


@pytest.mark.asyncio
async def test_closing_the_browser_stops_watching_ads() -> None:
    import asyncio

    browser = FakeBrowser({"browser_run_code_unsafe": (CLOSED, True)})
    manager = MCPManager([MCPServerConfig(
        name="browser", url="http://x/mcp", trusted=True,
        allowed_tools=["browser_navigate", "browser_snapshot", "browser_click"],
    )])
    server = manager.servers[0]
    server.client, server.stale = browser, False
    server.tools = [
        SimpleNamespace(name=n, description=n, input_schema={}, annotations=None)
        for n in SERVER_TOOLS
    ]
    watching = asyncio.ensure_future(asyncio.sleep(10))
    manager.ad_watch = watching
    tools = {t.name: t for t in await manager.tools()}

    await tools["browser__close_browser"].run({})
    await asyncio.sleep(0)

    assert watching.cancelled()


def test_manual_skip_finishes_within_the_tool_time_limit() -> None:
    # 실측: 15초를 기다려 도구 시간 제한(15초)에 걸려 끊겼다
    from shared import browser_assist
    from shared.tools import TOOL_TIMEOUT_SECONDS

    wait_ms = int(browser_assist.SKIP_AD_SCRIPT.split("Date.now() + ")[1].split(";")[0])
    assert wait_ms / 1000 <= TOOL_TIMEOUT_SECONDS - 3
