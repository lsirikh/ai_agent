"""
MCP 클라이언트 시나리오 — 시험용 stdio MCP 서버(tests/shared/mcp_test_server.py)

- (e) 도구 나열·이름 변환(서버__도구)·허용 목록 적용·호출(is_error 참/거짓)
- (f) 파괴적 도구는 확인이 필요하고 확인 전에는 실행되지 않는다
- 설정 파일·이름 규칙·연결 실패
"""

import json
import os
import sys

import pytest
import pytest_asyncio

from shared.mcp_client import (
    MCPManager,
    MCPServerConfig,
    load_mcp_config,
    sanitize_tool_name,
)
from shared.tool_calling import stream_with_tools
from shared.tools import ToolRegistry

# shared.mcp_client 는 mcp 를 쓸 때 불러온다 — 설치돼 있지 않으면 건너뛴다
pytest.importorskip("mcp")

SERVER = os.path.join(os.path.dirname(__file__), "mcp_test_server.py")


def config(**overrides):
    values = dict(
        name="ironwall",
        command=sys.executable,
        args=[SERVER],
        allowed_tools=["status", "restart"],
        trusted=True,
        timeout=30,
    )
    values.update(overrides)
    return MCPServerConfig(**values)


@pytest_asyncio.fixture
async def manager():
    mcp = MCPManager([config()])
    await mcp.start()
    yield mcp
    await mcp.close()


class TestNames:
    def test_should_join_server_and_tool(self):
        assert sanitize_tool_name("ironwall", "status") == "ironwall__status"

    def test_should_replace_invalid_characters_and_limit_length(self):
        name = sanitize_tool_name("아이언월 서버", "restart.service/" + "x" * 80)

        assert len(name) <= 64
        assert all(c.isascii() and (c.isalnum() or c in "_-") for c in name)

    def test_should_disambiguate_collisions(self):
        taken = {"a_b__c"}

        assert sanitize_tool_name("a.b", "c", taken) == "a_b__c_2"


def test_load_config(tmp_path):
    path = tmp_path / "mcp.json"
    path.write_text(
        json.dumps(
            {"servers": [{"name": "s", "url": "http://h/mcp", "allowed_tools": ["t"]}]}
        )
    )

    servers = load_mcp_config(str(path))

    assert servers[0].url == "http://h/mcp" and servers[0].allowed_tools == ["t"]
    assert load_mcp_config(str(tmp_path / "none.json")) == []


class TestStdioServer:
    @pytest.mark.asyncio
    async def test_should_list_only_allowed_tools_with_prefixed_names(self, manager):
        tools = {t.name: t for t in await manager.tools()}

        assert sorted(tools) == ["ironwall__restart", "ironwall__status"]
        assert manager.name_map["ironwall__status"] == ("ironwall", "status")
        assert tools["ironwall__restart"].parameters["required"] == ["service"]

    @pytest.mark.asyncio
    async def test_should_confirm_only_non_read_only_tools(self, manager):
        tools = {t.name: t for t in await manager.tools()}

        assert tools["ironwall__status"].needs_confirm is False
        assert tools["ironwall__restart"].needs_confirm is True

    @pytest.mark.asyncio
    async def test_untrusted_server_confirms_read_only_tools_too(self):
        mcp = MCPManager([config(trusted=False)])
        await mcp.start()
        try:
            tools = {t.name: t for t in await mcp.tools()}
        finally:
            await mcp.close()

        assert tools["ironwall__status"].needs_confirm is True

    @pytest.mark.asyncio
    async def test_no_confirm_overrides_hints_but_not_always_confirm(self):
        # 음성은 승인한 다음 턴에 도구가 없어 '열기' 뒤 '입력' 으로 못 넘어갔다.
        # 브라우저 열기·입력처럼 사용자가 믿기로 한 도구는 묻지 않는다
        # Playwright MCP 는 열기·입력에도 destructive 표시를 붙여,
        # 명시한 no_confirm 이 이긴다.
        # always_confirm 은 그보다 우선한다.
        mcp = MCPManager(
            [
                config(
                    allowed_tools=["status", "restart", "hidden"],
                    no_confirm=["hidden", "restart", "status"],
                    always_confirm=["status"],
                )
            ]
        )
        await mcp.start()
        try:
            tools = {t.name: t for t in await mcp.tools()}
        finally:
            await mcp.close()

        assert tools["ironwall__hidden"].needs_confirm is False
        assert tools["ironwall__restart"].needs_confirm is False  # destructive 표시
        assert tools["ironwall__status"].needs_confirm is True

    @pytest.mark.asyncio
    async def test_should_call_tools_and_report_is_error(self, manager):
        registry = ToolRegistry(await manager.tools())

        ok = await registry.execute("ironwall__status", "{}")
        failed = await registry.execute("ironwall__restart", '{"service": "unknown"}')

        assert ok.is_error is False and "정상" in ok.content
        assert failed.is_error is True

    @pytest.mark.asyncio
    async def test_destructive_tool_not_run_before_confirmation(self, manager):
        registry = ToolRegistry(await manager.tools())
        call = {
            "choices": [
                {
                    "delta": {
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "c1",
                                "function": {
                                    "name": "ironwall__restart",
                                    "arguments": '{"service": "stt"}',
                                },
                            }
                        ]
                    }
                }
            ]
        }
        responses = [[call], [{"choices": [{"delta": {"content": "재시작할까요?"}}]}]]

        async def llm(messages, tools):
            for item in responses.pop(0):
                yield item

        asked = []

        async def deny(event):
            asked.append(event["name"])
            return False

        events = [
            e
            async for e in stream_with_tools(
                llm, [{"role": "user", "content": "stt 재시작"}], registry, confirm=deny
            )
            if isinstance(e, dict)
        ]

        assert asked == ["ironwall__restart"]
        assert events[-1]["is_error"] and "승인" in events[-1]["content"]
        # 실행됐다면 "재시작 완료" 가 결과에 있어야 한다
        assert "재시작 완료" not in events[-1]["content"]

    @pytest.mark.asyncio
    async def test_should_relist_after_tools_list_changed(self, manager):
        from mcp.types import ToolListChangedNotification

        server = manager.servers[0]
        listed = []
        original = server.list_tools

        async def counting_list_tools():
            listed.append(1)
            return await original()

        server.list_tools = counting_list_tools
        await manager.tools()
        await manager.tools()
        assert len(listed) == 1

        await server._on_message(ToolListChangedNotification())
        assert server.stale is True
        await manager.tools()

        assert len(listed) == 2 and server.stale is False

    @pytest.mark.asyncio
    async def test_should_skip_server_that_fails_to_connect(self):
        mcp = MCPManager(
            [
                config(
                    command=sys.executable,
                    args=["-c", "raise SystemExit(1)"],
                    timeout=10,
                )
            ]
        )
        await mcp.start()
        try:
            assert await mcp.tools() == []
        finally:
            await mcp.close()


class TestReconnect:
    """
    실측(2026-10-18): 브라우저 MCP 세션이 한 번 끊기면('Session terminated')
    그 뒤 모든 호출이 실패해 '유튜브 열어 줘' 도 못 했다 → 다시 연결해 한 번 더 부른다.
    """

    @pytest.mark.asyncio
    async def test_should_reconnect_and_retry_when_session_is_terminated(self, manager):
        from mcp.shared.exceptions import MCPError

        registry = ToolRegistry(await manager.tools())
        server = manager.servers[0]
        old_client = server.client
        original = old_client.call_tool

        async def terminated(*args, **kwargs):
            raise MCPError(-32600, "Session terminated")

        old_client.call_tool = terminated
        try:
            result = await registry.execute("ironwall__status", "{}")
        finally:
            old_client.call_tool = original

        assert result.is_error is False and "정상" in result.content
        assert server.client is not None and server.client is not old_client

    @pytest.mark.asyncio
    async def test_should_reconnect_when_server_was_disconnected(self, manager):
        registry = ToolRegistry(await manager.tools())
        server = manager.servers[0]
        await server.stop()
        assert server.client is None

        result = await registry.execute("ironwall__status", "{}")

        assert result.is_error is False and "정상" in result.content


class TestReconnectOnListing:
    """
    실측(2026-10-18): 브라우저 MCP 를 다시 띄운 뒤 연결이 끊긴 서버를 도구 목록에서
    빼 버려 '네이버 열어 줘' 에 '도구가 연결되어 있지 않다' 고 답했다.
    """

    @pytest.mark.asyncio
    async def test_disconnected_server_is_reconnected_when_listing(self, manager):
        server = manager.servers[0]
        await server.stop()
        assert server.client is None

        names = [t.name for t in await manager.tools()]

        assert "ironwall__status" in names

    @pytest.mark.asyncio
    async def test_dead_server_is_not_retried_on_every_request(self):
        dead = config(
            command=sys.executable, args=["-c", "raise SystemExit(1)"], timeout=10
        )
        mcp = MCPManager([dead])
        await mcp.start()
        server = mcp.servers[0]
        attempts = []
        original = server.reconnect

        async def counted(*args, **kwargs):
            attempts.append(1)
            return await original(*args, **kwargs)

        server.reconnect = counted
        try:
            await mcp.tools()
            await mcp.tools()
        finally:
            await mcp.close()

        assert len(attempts) == 1


@pytest.mark.asyncio
async def test_listing_reconnects_when_session_is_terminated(manager):
    # 실측: 서버를 다시 띄운 뒤 'mcp list_tools failed (browser): Session terminated'
    from mcp.shared.exceptions import MCPError

    server = manager.servers[0]
    old_client = server.client
    server.stale = True

    async def terminated(*args, **kwargs):
        raise MCPError(-32600, "Session terminated")

    old_client.list_tools = terminated

    names = [t.name for t in await manager.tools()]

    assert "ironwall__status" in names
    assert server.client is not old_client
