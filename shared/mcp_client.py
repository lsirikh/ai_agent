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
        "timeout": 30
    }]}

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
from dataclasses import dataclass, field
from typing import Any, Optional

from . import browser_assist
from .tools import Tool, ToolResult

audit_log = logging.getLogger("edgevoice.mcp.audit")

NAME_PATTERN = re.compile(r"[^a-zA-Z0-9_-]")
NAME_MAX = 64
DEFAULT_TIMEOUT_SECONDS = 30.0
MAX_LIST_PAGES = 50


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
    timeout: float = DEFAULT_TIMEOUT_SECONDS


def load_mcp_config(path: Optional[str] = None) -> list:
    """MCP_CONFIG_PATH 의 서버 목록. 경로가 없으면 빈 목록."""
    path = path or os.getenv("MCP_CONFIG_PATH")
    if not path or not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return [MCPServerConfig(**server) for server in data.get("servers", [])]


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

    async def start(self) -> None:
        for server in self.servers:
            try:
                await server.start()
            except Exception as e:
                audit_log.warning("mcp connect failed: %s", e)

    async def close(self) -> None:
        for server in self.servers:
            await server.stop()

    async def tools(self) -> list:
        """허용 목록 안의 도구들 (list_changed 뒤에는 다시 받는다)."""
        result, taken = [], set()
        self.name_map = {}
        for server in self.servers:
            if server.client is None:
                continue
            if server.stale:
                try:
                    await server.list_tools()
                except Exception as e:
                    audit_log.warning(
                        "mcp list_tools failed (%s): %s", server.config.name, e
                    )
                    continue
            allowed = set(server.config.allowed_tools)
            for tool in server.tools:
                if tool.name not in allowed:
                    continue
                name = sanitize_tool_name(server.config.name, tool.name, taken)
                taken.add(name)
                self.name_map[name] = (server.config.name, tool.name)
                result.append(self._wrap(server, tool, name))
        return result

    def _wrap(self, server: _Server, tool: Any, name: str) -> Tool:
        config = server.config
        hints = tool.annotations
        read_only = bool(hints and hints.read_only_hint)
        destructive = bool(hints and hints.destructive_hint)
        needs_confirm = (
            not (config.trusted and read_only)
            or destructive
            or tool.name in config.always_confirm
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

        normalize = None
        if tool.name == "browser_navigate":
            def normalize(a):
                return {**a, "url": browser_assist.normalize_url(a.get("url", ""))}
        elif tool.name == "browser_type":
            normalize = self.browser.fix_type_target
        elif tool.name == "browser_click":
            normalize = self.browser.fix_click_target

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
        if server.client is None:
            audit_log.info(
                json.dumps({**record, "outcome": "disconnected"}, ensure_ascii=False)
            )
            return ToolResult(
                f"MCP 서버 '{server.config.name}' 에 연결돼 있지 않습니다",
                is_error=True,
            )
        try:
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


async def start_mcp_from_env() -> Optional[MCPManager]:
    """MCP_CONFIG_PATH 가 있으면 연결한 MCPManager, 없으면 None."""
    configs = load_mcp_config()
    if not configs:
        return None
    manager = MCPManager(configs)
    await manager.start()
    return manager
