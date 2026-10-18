"""
MCP 클라이언트 (Python mcp SDK 2.x — stdio · streamable HTTP)

설정 파일(MCP_CONFIG_PATH, JSON)의 서버 목록에 붙어
도구를 LLM 도구(shared.tools.Tool)로 바꾼다.

    {"servers": [{
        "name": "ironwall",
        "command": "python", "args": ["server.py"], "env": {},   # stdio
        "url": "http://host:port/mcp",                           # 또는 streamable HTTP
        "allowed_tools": ["status", "restart"],   # 허용 목록 (밖은 노출 안 함)
        "trusted": true,                          # read-only 도구는 바로 실행
        "always_confirm": ["restart"],            # 항상 확인 (자동 조치 등)
        "no_confirm": ["status_page"],            # 확인 없이 (always_confirm 이 우선)
        "timeout": 30,
        "enabled": true                           # 끄면 연결 안 함 (설정 화면)
    }]}

- 설정 화면에서 저장한 목록(Redis, MCP_SETTINGS_KEY)이 있으면 파일보다 우선한다.
  두 서비스는 턴마다 MCPManager.apply 로 바뀐 서버만 다시 연결한다.

- 이름은 `서버__도구` 를 ^[a-zA-Z0-9_-]{1,64}$ 로 정리하고 역매핑을 둔다.
- 신뢰 서버가 read-only 로 표시한 도구만 확인 없이 실행한다.
  파괴적 표시·always_confirm 은 항상 확인.
- tools/list 는 페이지를 끝까지 받고,
  tools/list_changed 알림이 오면 다음 사용 때 다시 받는다.
- 호출마다 시간 제한을 두고 감사 로그(edgevoice.mcp.audit)를 남긴다.
"""

import asyncio
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Optional
from urllib.parse import quote_plus

from . import browser_assist
from .tools import Tool, ToolResult

audit_log = logging.getLogger("edgevoice.mcp.audit")

NAME_PATTERN = re.compile(r"[^a-zA-Z0-9_-]")
NAME_MAX = 64
DEFAULT_TIMEOUT_SECONDS = 30.0
MAX_LIST_PAGES = 50
# 설정 화면(백엔드 API)이 쓰고 두 서비스가 턴마다 읽는다 (없으면 MCP_CONFIG_PATH)
MCP_SETTINGS_KEY = "edgevoice:settings:mcp"
# 브라우저 서버가 이 도구들을 내주면 play_youtube 도 만든다
RECONNECT_INTERVAL_SECONDS = 30.0
PLAY_YOUTUBE_NEEDS = {"browser_navigate", "browser_snapshot", "browser_click"}
# 크롬 닫기 · 광고 건너뛰기는 허용 목록 밖의 서버 도구를 정해진 코드로만 쓴다
# (모델이 코드를 주지 않는다). 열기(browser_navigate)를 허용했을 때만 만든다
RUN_CODE_TOOLS = ("browser_run_code_unsafe", "browser_run_code")
CLOSE_CONTEXT_CODE = "async (page) => { await page.context().close(); }"
# 유튜브를 틀어 두면 광고 건너뛰기 버튼을 저절로 누른다(사용자 요청 2026-10-19:
# 말하지 않아도) — 1초마다 보고, 동영상이 사라지면(3번 연속) 또는 한 시간 뒤 그만
AD_WATCH_SECONDS = 3600
AD_WATCH_GONE_CHECKS = 3


@dataclass
class MCPServerConfig:
    name: str
    command: Optional[str] = None
    args: list = field(default_factory=list)
    env: Optional[dict] = None
    url: Optional[str] = None
    allowed_tools: list = field(default_factory=list)
    trusted: bool = False
    always_confirm: list = field(default_factory=list)
    # 확인 없이 실행할 도구(사용자가 믿기로 한 것). 서버의 destructive 표시보다 우선한다
    # (Playwright MCP 는 열기·입력에도 destructive 를 붙인다). always_confirm 이 더 우선
    no_confirm: list = field(default_factory=list)
    timeout: float = DEFAULT_TIMEOUT_SECONDS
    enabled: bool = True


def load_mcp_config(path: Optional[str] = None) -> list:
    """MCP_CONFIG_PATH 의 서버 목록. 경로가 없으면 빈 목록."""
    path = path or os.getenv("MCP_CONFIG_PATH")
    if not path or not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return [MCPServerConfig(**server) for server in data.get("servers", [])]


async def load_mcp_servers(redis: Any) -> list:
    """설정 화면에서 저장한 서버 목록(Redis) → 없으면 MCP_CONFIG_PATH 파일."""
    if redis is not None:
        try:
            raw = await redis.get(MCP_SETTINGS_KEY)
        except Exception:
            raw = None
        if raw:
            return [MCPServerConfig(**server) for server in json.loads(raw)]
    return load_mcp_config()


def sanitize_tool_name(server: str, tool: str, taken: Optional[set] = None) -> str:
    """
    `서버__도구` → OpenAI 함수 이름 규칙(^[a-zA-Z0-9_-]{1,64}$).
    겹치면 번호를 붙인다.
    """
    base = NAME_PATTERN.sub("_", f"{server}__{tool}")[:NAME_MAX]
    name, number = base, 2
    while taken is not None and name in taken:
        suffix = f"_{number}"
        name = base[: NAME_MAX - len(suffix)] + suffix
        number += 1
    return name


def result_text(result: Any) -> str:
    """CallToolResult → 텍스트 (텍스트 블록을 잇고, 없으면 구조화 결과)."""
    parts = [block.text for block in result.content if getattr(block, "text", None)]
    if not parts and getattr(result, "structured_content", None):
        parts.append(json.dumps(result.structured_content, ensure_ascii=False))
    return "\n".join(parts)


def parse_json_arguments(args: dict, schema: Optional[dict]) -> dict:
    """
    목록·객체여야 할 인자가 JSON 글로 오면 풀어 준다.
    실측: 로컬 LLM 이 shapes 를 '[{"type": ...}]' 글로 넘겨 검증 오류가 났다.
    """
    properties = (schema or {}).get("properties") or {}
    fixed = dict(args)
    for key, value in args.items():
        expected = (properties.get(key) or {}).get("type")
        if expected in ("array", "object") and isinstance(value, str):
            try:
                parsed = json.loads(value)
            except ValueError:
                continue
            if isinstance(parsed, list if expected == "array" else dict):
                fixed[key] = parsed
    return fixed


class _Server:
    """한 MCP 서버 연결. 연결은 전용 태스크 안에서 열고 닫는다(anyio 취소 범위 규칙)."""

    def __init__(self, config: MCPServerConfig):
        self.config = config
        self.client: Any = None
        self.tools: list = []
        self.stale = True
        self._ready = asyncio.Event()
        self._stop = asyncio.Event()
        self._task: Optional[asyncio.Task] = None
        self.error: Optional[BaseException] = None
        self.retry_after = 0.0  # 이 시각(monotonic) 전에는 다시 연결해 보지 않는다

    def _target(self) -> Any:
        from mcp import StdioServerParameters

        if self.config.url:
            return self.config.url
        return StdioServerParameters(
            command=self.config.command, args=self.config.args, env=self.config.env
        )

    async def _on_message(self, message: Any) -> None:
        from mcp.types import ToolListChangedNotification

        if isinstance(message, ToolListChangedNotification):
            self.stale = True

    async def _run(self) -> None:
        from mcp import Client

        try:
            async with Client(
                self._target(),
                message_handler=self._on_message,
                read_timeout_seconds=self.config.timeout,
            ) as client:
                self.client = client
                self._ready.set()
                await self._stop.wait()
        except Exception as e:  # 연결 실패도 다른 서버를 막지 않는다
            self.error = e
        finally:
            self.client = None
            self._ready.set()

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run())
        await asyncio.wait_for(self._ready.wait(), self.config.timeout)
        if self.client is None:
            raise ConnectionError(
                f"MCP 서버 '{self.config.name}' 연결 실패: {self.error}"
            )

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            await asyncio.wait({self._task}, timeout=self.config.timeout)

    async def reconnect(self) -> bool:
        """연결을 새로 연다(세션이 끊겼거나 서버가 늦게 떴을 때). 되면 True."""
        await self.stop()
        self._ready, self._stop = asyncio.Event(), asyncio.Event()
        self.error, self.stale = None, True
        try:
            await self.start()
        except Exception as e:
            audit_log.warning("mcp reconnect failed (%s): %s", self.config.name, e)
            return False
        return True

    async def list_tools(self) -> list:
        """페이지를 끝까지 받는다."""
        tools, cursor = [], None
        for _ in range(MAX_LIST_PAGES):
            page = await self.client.list_tools(cursor=cursor, cache_mode="refresh")
            tools.extend(page.tools)
            cursor = page.next_cursor
            if not cursor:
                break
        self.tools = tools
        self.stale = False
        return tools


class MCPManager:
    """설정한 MCP 서버들의 도구를 LLM 도구로 내준다."""

    def __init__(self, configs: list):
        self.servers = [_Server(config) for config in configs]
        # 브라우저 MCP 의 지금 페이지 ref (입력·클릭 대상을 바로잡는다)
        self.browser = browser_assist.BrowserState()
        # LLM 에 보인 이름 → (서버 이름, 원래 도구 이름)
        self.name_map: dict = {}
        self._apply_lock = asyncio.Lock()
        # 틀어 둔 유튜브의 광고 자동 건너뛰기
        self.ad_watch: Optional[asyncio.Task] = None
        self.ad_watch_interval = 1.0

    async def start(self) -> None:
        for server in self.servers:
            try:
                await server.start()
            except Exception as e:
                audit_log.warning("mcp connect failed: %s", e)

    async def close(self) -> None:
        for server in self.servers:
            await server.stop()

    async def apply(self, configs: list) -> None:
        """
        설정에 연결을 맞춘다: 켜진 서버 중 새것·바뀐 것만 연결하고
        꺼지거나 빠진 서버는 닫는다(그대로인 서버의 세션은 유지).
        """
        async with self._apply_lock:
            current = {server.config.name: server for server in self.servers}
            servers = []
            for config in configs:
                if not config.enabled:
                    continue
                server = current.pop(config.name, None)
                if server is None or server.config != config:
                    if server is not None:
                        await server.stop()
                    server = _Server(config)
                    try:
                        await server.start()
                    except Exception as e:
                        audit_log.warning("mcp connect failed: %s", e)
                servers.append(server)
            for server in current.values():
                await server.stop()
            self.servers = servers

    async def tools(self) -> list:
        """허용 목록 안의 도구들 (list_changed 뒤에는 다시 받는다)."""
        result, taken = [], set()
        self.name_map = {}
        for server in self.servers:
            if server.client is None and not await self._retry_connect(server):
                continue
            if server.stale:
                try:
                    await server.list_tools()
                except Exception as e:
                    audit_log.warning(
                        "mcp list_tools failed (%s): %s", server.config.name, e
                    )
                    # 세션이 끊겼으면(서버를 다시 띄움) 다시 연결해 한 번 더 받는다
                    try:
                        if not await self._retry_connect(server):
                            continue
                        await server.list_tools()
                    except Exception:
                        continue
            allowed = set(server.config.allowed_tools)
            for tool in server.tools:
                if tool.name not in allowed:
                    continue
                name = sanitize_tool_name(server.config.name, tool.name, taken)
                taken.add(name)
                self.name_map[name] = (server.config.name, tool.name)
                result.append(self._wrap(server, tool, name))
            on_server = {t.name for t in server.tools}
            if PLAY_YOUTUBE_NEEDS <= allowed & on_server:
                name = sanitize_tool_name(server.config.name, "play_youtube", taken)
                taken.add(name)
                result.append(self._play_youtube_tool(server, name))
            if "browser_navigate" not in allowed:
                continue
            run_code = next((t for t in RUN_CODE_TOOLS if t in on_server), None)
            if run_code:
                name = sanitize_tool_name(server.config.name, "close_browser", taken)
                taken.add(name)
                result.append(self._close_browser_tool(server, name, run_code))
            if "browser_evaluate" in on_server:
                name = sanitize_tool_name(server.config.name, "skip_youtube_ad", taken)
                taken.add(name)
                result.append(self._skip_youtube_ad_tool(server, name))
        return result

    def _close_browser_tool(self, server: "_Server", name: str, run_code: str) -> Tool:
        """
        EdgeVoice 크롬 창을 닫는다(사용자 보고 2026-10-19: '크롬 꺼' 를 못 했다).
        공유 브라우저라 browser_close 는 실패하고, 마지막 탭을 닫아도 창이 남는다 →
        소리부터 멈추고(빈 페이지) 브라우저 컨텍스트를 닫는다.
        다음 요청에서 다시 열린다.
        """

        async def run(args: dict) -> ToolResult:
            self.stop_ad_watch()
            await self.call(server, "browser_navigate", {"url": "about:blank"})
            closed = await self.call(server, run_code, {"code": CLOSE_CONTEXT_CODE})
            # 닫히는 도중이라 성공해도 '…has been closed' 오류로 온다(실측)
            if closed.is_error and "has been closed" not in closed.content:
                return ToolResult(
                    "크롬 창을 닫지 못했습니다(재생은 멈추고 빈 페이지로 바꿨습니다): "
                    + closed.content[:200],
                    is_error=True,
                )
            return ToolResult("EdgeVoice 크롬 창을 닫았습니다.")

        return Tool(
            name=name,
            description=(
                "EdgeVoice 가 쓰는 크롬 창을 닫는다(재생 중인 유튜브도 멈춘다). "
                "'크롬 꺼 줘'·'유튜브 꺼'·'브라우저 종료해' 같은 요청에 쓴다."
            ),
            parameters={"type": "object", "properties": {}},
            run=run,
            announce="크롬을 닫을게요.",
        )

    def _skip_youtube_ad_tool(self, server: "_Server", name: str) -> Tool:
        """유튜브 광고의 '건너뛰기' 버튼이 나오면 누른다(10초까지 기다린다)."""

        async def run(args: dict) -> ToolResult:
            result = await self.call(
                server, "browser_evaluate",
                {"function": browser_assist.SKIP_AD_SCRIPT},
            )
            if result.is_error:
                return result
            state = browser_assist.page_state(result.content)
            if state == "skipped":
                return ToolResult("유튜브 광고를 건너뛰었습니다. 동영상이 재생됩니다.")
            if state == "no_ad":
                return ToolResult("지금은 광고가 나오지 않습니다(동영상 재생 중).")
            if state == "ad_unskippable":
                return ToolResult(
                    "10초 동안 광고에 건너뛰기 버튼이 나오지 않았습니다"
                    "(건너뛸 수 없는 광고입니다)."
                )
            return ToolResult(
                "지금 크롬 화면이 유튜브 동영상이 아니라 광고를 건너뛸 수 없습니다.",
                is_error=True,
            )

        return Tool(
            name=name,
            description=(
                "크롬에서 재생 중인 유튜브 광고의 '건너뛰기' 버튼이 나오면 누른다. "
                "'광고 건너뛰어 줘' 같은 요청에 쓴다."
            ),
            parameters={"type": "object", "properties": {}},
            run=run,
            announce="광고 건너뛰기 버튼을 기다려 볼게요.",
        )

    def _play_youtube_tool(self, server: "_Server", name: str) -> Tool:
        """
        유튜브 검색 결과의 첫 동영상을 연다. 실측: 로컬 LLM 이 동영상 대신 바로 뒤의
        '채널로 이동' 링크를 눌렀다 → LLM 은 검색어만 고르고 고르기·누르기는 여기서.
        """

        async def run(args: dict) -> ToolResult:
            query = str(args.get("query") or "").strip()
            if not query:
                return ToolResult("무엇을 틀지 query 로 알려 주세요", is_error=True)
            url = "https://www.youtube.com/results?search_query=" + quote_plus(query)
            opened = await self.call(server, "browser_navigate", {"url": url})
            if opened.is_error:
                return opened
            ref = title = None
            for _ in range(3):  # 결과가 늦게 그려질 수 있다
                snapshot = await self.call(server, "browser_snapshot", {})
                ref, title = browser_assist.first_video(snapshot.content)
                if ref:
                    break
                await asyncio.sleep(1.0)
            if not ref:
                return ToolResult(
                    f"유튜브에서 '{query}' 검색 결과의 동영상을 찾지 못했습니다",
                    is_error=True,
                )
            clicked = await self.call(
                server, "browser_click", {"element": title, "target": ref}
            )
            if clicked.is_error:
                return clicked
            if "watch" not in clicked.content and "/shorts/" not in clicked.content:
                return ToolResult(
                    f"'{title}' 을(를) 눌렀지만 동영상이 열리지 않았습니다",
                    is_error=True,
                )
            played = f"유튜브에서 '{title}' 을(를) 틀었습니다"
            note = await self._playback_note(server)
            if "browser_evaluate" in {t.name for t in server.tools}:
                self._start_ad_watch(server)
                note += " 광고가 나오면 건너뛰기 버튼을 자동으로 누릅니다."
            return ToolResult(played + note)

        return Tool(
            name=name,
            description=(
                "유튜브에서 노래·영상을 검색해 첫 번째 동영상을 크롬에서 재생한다. "
                "'유튜브에서 ○○ 틀어 줘' 같은 요청에 쓴다."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string", "description": "검색어 (예: 아이유 좋은 날)"
                    }
                },
                "required": ["query"],
            },
            run=run,
            announce="유튜브에서 찾아 틀어 볼게요.",
        )

    def stop_ad_watch(self) -> None:
        if self.ad_watch is not None and not self.ad_watch.done():
            self.ad_watch.cancel()

    def _start_ad_watch(self, server: "_Server") -> None:
        self.stop_ad_watch()
        self.ad_watch = asyncio.create_task(self._skip_ads_while_watching(server))

    async def _skip_ads_while_watching(self, server: "_Server") -> None:
        """틀어 둔 동안 광고 건너뛰기 버튼이 보이면 누른다(중간 광고까지)."""
        loop = asyncio.get_running_loop()
        end, gone = loop.time() + AD_WATCH_SECONDS, 0
        while loop.time() < end and gone < AD_WATCH_GONE_CHECKS:
            checked = await self.call(
                server, "browser_evaluate",
                {"function": browser_assist.SKIP_AD_ONCE_SCRIPT},
            )
            state = "" if checked.is_error else browser_assist.page_state(
                checked.content
            )
            if state == "skipped":
                audit_log.info("youtube ad skipped automatically")
            gone = gone + 1 if state in ("", "no_player") else 0
            await asyncio.sleep(self.ad_watch_interval)

    async def _playback_note(self, server: "_Server") -> str:
        """
        튼 뒤 실제로 나오는지 덧붙인다(사용자 보고 2026-10-19: 광고가 나오는데
        '재생되고 있습니다' 라고 해 '안 나온다' 고 했다). 볼 수 없으면 마침표만.
        """
        if "browser_evaluate" not in {t.name for t in server.tools}:
            return "."
        checked = await self.call(
            server, "browser_evaluate", {"function": browser_assist.PLAYBACK_SCRIPT}
        )
        state = "" if checked.is_error else browser_assist.page_state(checked.content)
        return {
            "playing": "(재생 중).",
            "ad": (
                ". 지금은 광고가 나오는 중입니다"
                "(건너뛰기 버튼은 몇 초 뒤에 나옵니다)."
            ),
            "paused": ". 그런데 동영상이 멈춰 있습니다.",
        }.get(state, ".")

    async def _retry_connect(self, server: "_Server") -> bool:
        """
        끊긴 서버를 다시 연결해 본다(서버를 다시 띄운 뒤 도구가 사라졌다 — 실측).
        죽은 서버로 요청마다 기다리지 않게 RECONNECT_INTERVAL 초에 한 번만.
        """
        now = time.monotonic()
        if now < server.retry_after:
            return False
        server.retry_after = now + RECONNECT_INTERVAL_SECONDS
        return await server.reconnect()

    def _wrap(self, server: _Server, tool: Any, name: str) -> Tool:
        config = server.config
        hints = tool.annotations
        read_only = bool(hints and hints.read_only_hint)
        destructive = bool(hints and hints.destructive_hint)
        needs_confirm = tool.name in config.always_confirm or (
            tool.name not in config.no_confirm
            and (not (config.trusted and read_only) or destructive)
        )

        async def run(args: dict) -> ToolResult:
            result = await self.call(server, tool.name, args)
            if tool.name.startswith("browser_"):
                # 페이지 구조가 문맥보다 커서 잘리므로 다룰 요소(ref)만 추려 붙인다
                result = await browser_assist.with_page_elements(
                    tool.name, result,
                    lambda: self.call(server, "browser_snapshot", {}),
                    self.browser,
                )
            return result

        fix = None
        if tool.name == "browser_navigate":
            def fix(a):
                return {**a, "url": browser_assist.normalize_url(a.get("url", ""))}
        elif tool.name == "browser_type":
            fix = self.browser.fix_type_target
        elif tool.name == "browser_click":
            fix = self.browser.fix_click_target

        def normalize(a, fix=fix, schema=tool.input_schema):
            a = parse_json_arguments(a, schema)
            return fix(a) if fix else a

        return Tool(
            name=name,
            description=tool.description or tool.name,
            parameters=tool.input_schema or {"type": "object", "properties": {}},
            run=run,
            announce="확인해 볼게요.",
            needs_confirm=needs_confirm,
            normalize=normalize,
        )

    async def call(self, server: _Server, tool_name: str, args: dict) -> ToolResult:
        record = {"server": server.config.name, "tool": tool_name, "arguments": args}
        if server.client is None and not await server.reconnect():
            audit_log.info(
                json.dumps({**record, "outcome": "disconnected"}, ensure_ascii=False)
            )
            return ToolResult(
                f"MCP 서버 '{server.config.name}' 에 연결돼 있지 않습니다",
                is_error=True,
            )
        try:
            try:
                result = await asyncio.wait_for(
                    server.client.call_tool(tool_name, args), server.config.timeout
                )
            except asyncio.TimeoutError:
                raise
            except Exception as e:
                # 세션이 끊기면('Session terminated') 그 뒤 호출이 모두 실패했다(실측)
                # → 다시 연결해 한 번 더 부른다
                audit_log.info(
                    json.dumps({**record, "outcome": f"retry: {e}"}, ensure_ascii=False)
                )
                if not await server.reconnect():
                    raise
                result = await asyncio.wait_for(
                    server.client.call_tool(tool_name, args), server.config.timeout
                )
        except asyncio.TimeoutError:
            audit_log.info(
                json.dumps({**record, "outcome": "timeout"}, ensure_ascii=False)
            )
            return ToolResult(f"MCP 도구 시간 초과: {tool_name}", is_error=True)
        except Exception as e:
            audit_log.info(
                json.dumps({**record, "outcome": f"error: {e}"}, ensure_ascii=False)
            )
            return ToolResult(f"MCP 도구 오류: {e}", is_error=True)
        text = result_text(result)
        audit_log.info(
            json.dumps(
                {
                    **record,
                    "outcome": "error" if result.is_error else "ok",
                    "result": text[:200],
                },
                ensure_ascii=False,
            )
        )
        return ToolResult(text or "(빈 결과)", is_error=bool(result.is_error))


async def start_mcp_from_env(redis: Any = None) -> MCPManager:
    """저장한 서버 목록(없으면 MCP_CONFIG_PATH)의 켜진 서버에 연결한 MCPManager."""
    manager = MCPManager([])
    await manager.apply(await load_mcp_servers(redis))
    return manager
