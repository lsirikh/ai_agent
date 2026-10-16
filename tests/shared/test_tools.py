"""
도구 레지스트리 · web_fetch 안전 검사 시나리오

- (b) 인터넷 도구가 꺼져 있거나 제공자가 없으면 web_search/web_fetch 가 노출되지 않는다
- (d) web_fetch 가 메타데이터·localhost·사설 IP·Docker 서비스 이름·
  2MB 초과·비 HTML 을 거부한다
  (리다이렉트로 내부 주소에 가도 거부)
- (g) 시간 초과·잘못된 JSON 인자·없는 도구·예외는 오류 결과로 돌아온다
  (예외로 멈추지 않는다)
"""

import asyncio

import httpx
import pytest

from shared.tools import (
    FETCH_MAX_BYTES,
    GET_TIME,
    Tool,
    ToolRegistry,
    ToolResult,
    UnsafeURLError,
    build_registry,
    check_url,
    fetch_page,
    tool_parser_for,
    web_fetch_tool,
)


async def _public(host, port):
    return ["93.184.216.34"]


def _transport(handler):
    return httpx.MockTransport(handler)


class TestRegistry:
    def test_should_expose_only_get_time_when_internet_tools_off(self):
        calls = []

        class Provider:
            async def search(self, query, count):
                calls.append(query)
                return []

        registry = build_registry(
            {"internet_enabled": False}, search_provider=Provider()
        )

        assert registry.names() == ["get_time"]
        assert calls == []

    def test_should_hide_internet_tools_when_no_provider_configured(self, monkeypatch):
        monkeypatch.delenv("SEARXNG_URL", raising=False)

        registry = build_registry(
            {"internet_enabled": True, "search_provider": "searxng"}
        )

        assert registry.names() == ["get_time"]

    def test_should_expose_web_tools_sorted_when_enabled(self, monkeypatch):
        monkeypatch.setenv("SEARXNG_URL", "http://searxng:8080")

        registry = build_registry(
            {"internet_enabled": True, "search_provider": "searxng"}
        )

        assert registry.names() == ["get_time", "web_fetch", "web_search"]
        assert [s["function"]["name"] for s in registry.schemas()] == registry.names()

    @pytest.mark.asyncio
    async def test_get_time_returns_current_date(self):
        result = await ToolRegistry([GET_TIME]).execute("get_time", "{}")

        assert not result.is_error
        assert "년" in result.content and "시" in result.content

    @pytest.mark.asyncio
    async def test_should_return_error_for_unknown_tool(self):
        result = await ToolRegistry([GET_TIME]).execute("nope", "{}")

        assert result.is_error and "없는 도구" in result.content

    @pytest.mark.asyncio
    async def test_should_return_error_for_invalid_json_arguments(self):
        result = await ToolRegistry([GET_TIME]).execute("get_time", '{"a": ')

        assert result.is_error and "JSON" in result.content

    @pytest.mark.asyncio
    async def test_should_return_error_when_tool_times_out(self):
        async def slow(_):
            await asyncio.sleep(5)
            return ToolResult("늦음")

        registry = ToolRegistry([Tool("slow", "느림", {"type": "object"}, slow)])

        result = await registry.execute("slow", "{}", timeout=0.05)

        assert result.is_error and "시간 초과" in result.content

    @pytest.mark.asyncio
    async def test_should_return_error_when_tool_raises(self):
        async def boom(_):
            raise httpx.HTTPStatusError(
                "503",
                request=httpx.Request("GET", "http://x"),
                response=httpx.Response(503),
            )

        registry = ToolRegistry([Tool("boom", "오류", {"type": "object"}, boom)])

        result = await registry.execute("boom", "{}")

        assert result.is_error and "오류" in result.content


class TestToolParser:
    def test_qwen_uses_hermes(self, monkeypatch):
        monkeypatch.delenv("LLM_TOOL_PARSER", raising=False)
        assert tool_parser_for("Qwen/Qwen2.5-7B-Instruct-AWQ") == "hermes"
        assert tool_parser_for("Qwen/Qwen3-8B") == "hermes"

    def test_unknown_model_disables_tools(self, monkeypatch):
        monkeypatch.delenv("LLM_TOOL_PARSER", raising=False)
        assert tool_parser_for("google/gemma-2-9b-it") is None


class TestCheckUrl:
    @pytest.mark.parametrize(
        "url",
        [
            "http://169.254.169.254/latest/meta-data/",
            "http://localhost:8000/",
            "http://127.0.0.1/",
            "http://10.0.0.5/",
            "http://192.168.1.1/",
            "http://172.17.0.2/",
            "http://[::1]/",
            "http://[::ffff:127.0.0.1]/",
            "http://redis:6379/",
            "http://backend/api",
            "http://ev-postgres/",
            "file:///etc/passwd",
            "ftp://example.com/",
        ],
    )
    @pytest.mark.asyncio
    async def test_should_reject_internal_or_non_http_urls(self, url):
        with pytest.raises(UnsafeURLError):
            await check_url(url, _public)

    @pytest.mark.asyncio
    async def test_should_reject_host_resolving_to_private_ip(self):
        async def private(host, port):
            return ["10.1.2.3"]

        with pytest.raises(UnsafeURLError):
            await check_url("http://intranet.example.com/", private)

    @pytest.mark.asyncio
    async def test_should_allow_public_host(self):
        await check_url("https://example.com/page", _public)


class TestFetch:
    @pytest.mark.asyncio
    async def test_should_extract_html_text(self):
        def handler(request):
            return httpx.Response(
                200,
                headers={"content-type": "text/html; charset=utf-8"},
                text=(
                    "<html><body><script>x()</script>"
                    "<p>안녕하세요 본문</p></body></html>"
                ),
            )

        url, text = await fetch_page(
            "https://example.com/", transport=_transport(handler), resolve=_public
        )

        assert url == "https://example.com/"
        assert "안녕하세요 본문" in text and "x()" not in text

    @pytest.mark.asyncio
    async def test_should_reject_non_html(self):
        def handler(request):
            return httpx.Response(
                200, headers={"content-type": "application/pdf"}, content=b"%PDF"
            )

        with pytest.raises(UnsafeURLError):
            await fetch_page(
                "https://example.com/a.pdf",
                transport=_transport(handler),
                resolve=_public,
            )

    @pytest.mark.asyncio
    async def test_should_reject_body_over_2mb_without_content_length(self):
        def handler(request):
            async def body():
                for _ in range(3):
                    yield b"a" * (FETCH_MAX_BYTES // 2 + 1)

            return httpx.Response(
                200, headers={"content-type": "text/plain"}, content=body()
            )

        with pytest.raises(UnsafeURLError, match="2MB"):
            await fetch_page(
                "https://example.com/big",
                transport=_transport(handler),
                resolve=_public,
            )

    @pytest.mark.asyncio
    async def test_should_reject_declared_size_over_2mb(self):
        def handler(request):
            return httpx.Response(
                200,
                headers={
                    "content-type": "text/html",
                    "content-length": str(FETCH_MAX_BYTES + 1),
                },
                content=b"",
            )

        with pytest.raises(UnsafeURLError, match="2MB"):
            await fetch_page(
                "https://example.com/big",
                transport=_transport(handler),
                resolve=_public,
            )

    @pytest.mark.asyncio
    async def test_should_recheck_redirect_target(self):
        requested = []

        def handler(request):
            requested.append(str(request.url))
            return httpx.Response(302, headers={"location": "http://169.254.169.254/"})

        with pytest.raises(UnsafeURLError):
            await fetch_page(
                "https://example.com/", transport=_transport(handler), resolve=_public
            )
        assert requested == ["https://example.com/"]

    @pytest.mark.asyncio
    async def test_tool_returns_error_result_instead_of_raising(self):
        tool = web_fetch_tool(resolve=_public)

        result = await ToolRegistry([tool]).execute(
            "web_fetch", '{"url": "http://169.254.169.254/"}'
        )

        assert result.is_error
