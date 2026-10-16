"""
LLM 도구 (백엔드 채팅·오케스트레이터 음성이 같이 쓴다)

- 기본 켜짐: get_time (로컬)
- 선택(설정 토글, 기본 꺼짐): web_search, web_fetch
  검색 제공자가 설정돼 있지 않으면 web_search 는 노출되지 않는다.
- web_fetch 는 사설·루프백·링크로컬·메타데이터 주소와 Docker 서비스 이름을 거부한다
  (리다이렉트마다 다시 검사한다).
"""

import asyncio
import ipaddress
import json
import os
import re
import socket
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Awaitable, Callable, Optional
from urllib.parse import urljoin, urlsplit

import httpx

from .context_builder import _truncate_to_tokens

# 백엔드 설정 API 가 쓰고 두 서비스가 턴마다 읽는다 (없으면 환경변수 기본값)
TOOL_SETTINGS_KEY = "edgevoice:settings:tools"

TOOL_TIMEOUT_SECONDS = 15.0
# 도구 결과 하나가 프롬프트에서 차지할 수 있는 최대 토큰
TOOL_RESULT_MAX_TOKENS = 1500

FETCH_MAX_BYTES = 2 * 1024 * 1024
FETCH_TIMEOUT_SECONDS = 10.0
FETCH_MAX_REDIRECTS = 5
FETCH_CONTENT_TYPES = ("text/html", "text/plain")
# User-Agent 가 없으면 거절하는 사이트가 있다(위키백과 403 등)
FETCH_HEADERS = {"User-Agent": "EdgeVoice/1.0 (local voice assistant; web_fetch tool)"}

# compose 서비스·컨테이너 이름 (점 없는 호스트 이름도 모두 거부한다)
BLOCKED_HOSTS = {
    "localhost",
    "metadata.google.internal",
    "host.docker.internal",
    "gateway.docker.internal",
}

SEARCH_RESULT_COUNT = 5


@dataclass
class ToolResult:
    content: str
    is_error: bool = False
    # 채팅에 보여 줄 출처 [{"title", "url"}]
    sources: list = field(default_factory=list)


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict
    run: Callable[[dict], Awaitable[ToolResult]]
    # 음성 경로에서 실행 전에 말할 짧은 안내
    announce: Optional[str] = None
    # 실행 전에 사용자 확인이 필요한 도구 (MCP 의 쓰기·파괴적 도구)
    needs_confirm: bool = False

    def schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ToolRegistry:
    """LLM 에 노출할 도구 묶음. 스키마는 이름순으로 고정해 접두사 캐시를 지킨다."""

    def __init__(self, tools: Optional[list] = None):
        self._tools: dict = {}
        for tool in tools or []:
            self.add(tool)

    def add(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[Tool]:
        return self._tools.get(name)

    def names(self) -> list:
        return sorted(self._tools)

    def schemas(self) -> list:
        return [self._tools[name].schema() for name in self.names()]

    def __bool__(self) -> bool:
        return bool(self._tools)

    async def execute(
        self, name: str, arguments: str, timeout: float = TOOL_TIMEOUT_SECONDS
    ) -> ToolResult:
        """
        도구를 실행한다.
        어떤 실패도 예외 대신 오류 결과로 돌려준다(답이 멈추지 않게).
        """
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(f"없는 도구입니다: {name}", is_error=True)
        try:
            args = parse_arguments(arguments)
        except ValueError as e:
            return ToolResult(
                f"도구 인자가 올바른 JSON 이 아닙니다: {e}", is_error=True
            )
        try:
            return await asyncio.wait_for(tool.run(args), timeout)
        except asyncio.TimeoutError:
            return ToolResult(f"도구 시간 초과({timeout:g}초): {name}", is_error=True)
        except Exception as e:
            return ToolResult(f"도구 실행 오류: {e}", is_error=True)


def parse_arguments(arguments: Any) -> dict:
    """tool_calls 의 arguments(JSON 문자열) → dict. 빈 값은 {}."""
    if isinstance(arguments, dict):
        return arguments
    if not arguments or not str(arguments).strip():
        return {}
    try:
        value = json.loads(arguments)
    except json.JSONDecodeError as e:
        raise ValueError(str(e)) from e
    if not isinstance(value, dict):
        raise ValueError("객체가 아닙니다")
    return value


# ===== 도구 설정 =====


def default_tool_settings() -> dict:
    return {
        "internet_enabled": os.getenv("INTERNET_TOOLS_ENABLED", "false").lower()
        == "true",
        "search_provider": os.getenv("SEARCH_PROVIDER", "searxng"),
    }


async def load_tool_settings(redis: Any) -> dict:
    """설정 API 로 바꾼 값(Redis) → 없으면 환경변수 기본값."""
    settings = default_tool_settings()
    if redis is None:
        return settings
    try:
        raw = await redis.get(TOOL_SETTINGS_KEY)
        if raw:
            settings.update(json.loads(raw))
    except Exception:
        pass
    return settings


def tool_parser_for(model: Optional[str]) -> Optional[str]:
    """
    모델에 맞는 vLLM --tool-call-parser. 모르는 모델이면 None → 도구를 끈다.
    LLM_TOOL_PARSER 로 덮어쓸 수 있다("none" 이면 끈다).
    """
    override = os.getenv("LLM_TOOL_PARSER")
    if override:
        return None if override.lower() == "none" else override
    name = (model or "").lower()
    if "qwen2.5" in name or "qwen3" in name or "hermes" in name:
        return "hermes"
    return None


# ===== get_time =====


def _now() -> datetime:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

    try:
        return datetime.now(ZoneInfo(os.getenv("TOOLS_TIMEZONE", "Asia/Seoul")))
    except ZoneInfoNotFoundError:
        return datetime.now().astimezone()


async def _get_time(_: dict) -> ToolResult:
    now = _now()
    weekday = "월화수목금토일"[now.weekday()]
    return ToolResult(
        now.strftime(f"%Y년 %m월 %d일 ({weekday}요일) %H시 %M분 %Z(UTC%z)")
    )


GET_TIME = Tool(
    name="get_time",
    description="현재 날짜와 시각을 알려 준다. 오늘 날짜·요일·지금 시각 질문에 쓴다.",
    parameters={"type": "object", "properties": {}},
    run=_get_time,
)


# ===== 검색 제공자 =====


def _strip_tags(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "")


class SearxngProvider:
    """로컬 SearXNG (format=json 이 켜져 있어야 한다)."""

    def __init__(self, base_url: str, language: str = "ko"):
        self.base_url = base_url.rstrip("/")
        self.language = language

    async def search(self, query: str, count: int) -> list:
        async with httpx.AsyncClient(timeout=FETCH_TIMEOUT_SECONDS) as client:
            response = await client.get(
                f"{self.base_url}/search",
                params={"q": query, "format": "json", "language": self.language},
            )
            response.raise_for_status()
            results = response.json().get("results", [])
        return [
            {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "snippet": r.get("content", ""),
            }
            for r in results[:count]
        ]


class TavilyProvider:
    def __init__(self, api_key: str):
        self.api_key = api_key

    async def search(self, query: str, count: int) -> list:
        async with httpx.AsyncClient(timeout=FETCH_TIMEOUT_SECONDS) as client:
            response = await client.post(
                "https://api.tavily.com/search",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"query": query, "max_results": count},
            )
            response.raise_for_status()
            results = response.json().get("results", [])
        return [
            {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "snippet": r.get("content", ""),
            }
            for r in results[:count]
        ]


class NaverProvider:
    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret

    async def search(self, query: str, count: int) -> list:
        async with httpx.AsyncClient(timeout=FETCH_TIMEOUT_SECONDS) as client:
            response = await client.get(
                "https://openapi.naver.com/v1/search/webkr.json",
                params={"query": query, "display": count},
                headers={
                    "X-Naver-Client-Id": self.client_id,
                    "X-Naver-Client-Secret": self.client_secret,
                },
            )
            response.raise_for_status()
            items = response.json().get("items", [])
        return [
            {
                "title": _strip_tags(r.get("title")),
                "url": r.get("link", ""),
                "snippet": _strip_tags(r.get("description")),
            }
            for r in items[:count]
        ]


def search_provider_from_env(name: str) -> Optional[Any]:
    """
    설정의 제공자 이름 → 제공자.
    주소·키가 env 에 없으면 None(도구를 노출하지 않는다).
    """
    if name == "searxng" and os.getenv("SEARXNG_URL"):
        return SearxngProvider(os.environ["SEARXNG_URL"])
    if name == "tavily" and os.getenv("TAVILY_API_KEY"):
        return TavilyProvider(os.environ["TAVILY_API_KEY"])
    if (
        name == "naver"
        and os.getenv("NAVER_CLIENT_ID")
        and os.getenv("NAVER_CLIENT_SECRET")
    ):
        return NaverProvider(
            os.environ["NAVER_CLIENT_ID"], os.environ["NAVER_CLIENT_SECRET"]
        )
    return None


def web_search_tool(provider: Any) -> Tool:
    async def run(args: dict) -> ToolResult:
        query = str(args.get("query", "")).strip()
        if not query:
            return ToolResult("검색어(query)가 비어 있습니다", is_error=True)
        results = await provider.search(query, SEARCH_RESULT_COUNT)
        if not results:
            return ToolResult(f"'{query}' 검색 결과가 없습니다")
        lines = [
            f"{i}. {r['title']}\n   {r['url']}\n   {r['snippet']}"
            for i, r in enumerate(results, 1)
        ]
        return ToolResult(
            "\n".join(lines),
            sources=[{"title": r["title"], "url": r["url"]} for r in results],
        )

    return Tool(
        name="web_search",
        description=(
            "인터넷에서 최신 정보를 검색한다. "
            "뉴스·날씨·최근 사건처럼 모르는 사실에 쓴다."
        ),
        parameters={
            "type": "object",
            "properties": {"query": {"type": "string", "description": "검색어"}},
            "required": ["query"],
        },
        run=run,
        announce="검색해 볼게요.",
    )


# ===== web_fetch =====


class UnsafeURLError(ValueError):
    """web_fetch 가 열지 않는 주소·응답."""


Resolver = Callable[[str, int], Awaitable[list]]


async def _resolve(host: str, port: int) -> list:
    infos = await asyncio.get_running_loop().getaddrinfo(
        host, port, type=socket.SOCK_STREAM
    )
    return [info[4][0] for info in infos]


def _is_public(address: str) -> bool:
    ip = ipaddress.ip_address(address.split("%")[0])
    mapped = getattr(ip, "ipv4_mapped", None)
    if mapped is not None:
        ip = mapped
    return ip.is_global and not ip.is_multicast


async def check_url(url: str, resolve: Resolver = _resolve) -> None:
    """http(s) 이고 공인 주소로만 풀리는 URL 인지 확인한다. 아니면 UnsafeURLError."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise UnsafeURLError(f"http(s) 주소만 열 수 있습니다: {parts.scheme or url}")
    host = (parts.hostname or "").rstrip(".").lower()
    if not host:
        raise UnsafeURLError("호스트가 없습니다")
    try:
        ipaddress.ip_address(host)
        is_ip = True
    except ValueError:
        is_ip = False
    if not is_ip and (host in BLOCKED_HOSTS or "." not in host):
        raise UnsafeURLError(f"내부 호스트는 열 수 없습니다: {host}")
    port = parts.port or (443 if parts.scheme == "https" else 80)
    try:
        addresses = [host] if is_ip else await resolve(host, port)
    except OSError as e:
        raise UnsafeURLError(f"주소를 찾을 수 없습니다: {host}") from e
    if not addresses or not all(_is_public(a) for a in addresses):
        raise UnsafeURLError(f"사설·내부 주소는 열 수 없습니다: {host}")


def extract_text(html: str) -> str:
    """HTML 본문 추출 (trafilatura, 없으면 태그만 걷어 낸다)."""
    try:
        import trafilatura

        text = trafilatura.extract(html)
        if text:
            return text
    except ImportError:
        pass
    html = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html)
    return re.sub(r"\s+", " ", _strip_tags(html)).strip()


async def fetch_page(
    url: str,
    *,
    transport: Optional[httpx.AsyncBaseTransport] = None,
    resolve: Resolver = _resolve,
) -> tuple:
    """안전 검사 후 페이지를 받아 (최종 URL, 본문 텍스트)를 돌려준다."""
    async with httpx.AsyncClient(
        timeout=FETCH_TIMEOUT_SECONDS,
        follow_redirects=False,
        transport=transport,
        headers=FETCH_HEADERS,
    ) as client:
        for _ in range(FETCH_MAX_REDIRECTS + 1):
            await check_url(url, resolve)
            async with client.stream("GET", url) as response:
                if response.is_redirect:
                    url = urljoin(url, response.headers.get("location", ""))
                    continue
                response.raise_for_status()
                content_type = response.headers.get("content-type", "").lower()
                if not content_type.startswith(FETCH_CONTENT_TYPES):
                    raise UnsafeURLError(
                        f"HTML·텍스트만 읽습니다: {content_type or '알 수 없음'}"
                    )
                if int(response.headers.get("content-length") or 0) > FETCH_MAX_BYTES:
                    raise UnsafeURLError("페이지가 2MB 를 넘습니다")
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > FETCH_MAX_BYTES:
                        raise UnsafeURLError("페이지가 2MB 를 넘습니다")
                text = body.decode(response.encoding or "utf-8", errors="ignore")
                if content_type.startswith("text/html"):
                    text = extract_text(text)
                return url, text
    raise UnsafeURLError("리다이렉트가 너무 많습니다")


def web_fetch_tool(
    transport: Optional[httpx.AsyncBaseTransport] = None, resolve: Resolver = _resolve
) -> Tool:
    async def run(args: dict) -> ToolResult:
        url = str(args.get("url", "")).strip()
        try:
            final_url, text = await asyncio.wait_for(
                fetch_page(url, transport=transport, resolve=resolve),
                FETCH_TIMEOUT_SECONDS,
            )
        except UnsafeURLError as e:
            return ToolResult(str(e), is_error=True)
        except asyncio.TimeoutError:
            return ToolResult("페이지 읽기 시간 초과(10초)", is_error=True)
        return ToolResult(
            _truncate_to_tokens(text, TOOL_RESULT_MAX_TOKENS),
            sources=[{"title": final_url, "url": final_url}],
        )

    return Tool(
        name="web_fetch",
        description=(
            "웹 페이지 주소(http/https)의 본문을 읽는다. "
            "검색 결과 링크를 자세히 볼 때 쓴다."
        ),
        parameters={
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "읽을 페이지 주소"}
            },
            "required": ["url"],
        },
        run=run,
        announce="페이지를 읽어 볼게요.",
    )


def build_registry(
    settings: dict, extra_tools: Optional[list] = None, search_provider: Any = None
) -> ToolRegistry:
    """
    이번 턴에 쓸 도구. 인터넷 도구는 설정이 켜져 있고 검색 제공자가 있을 때만 넣는다.
    """
    registry = ToolRegistry([GET_TIME])
    if settings.get("internet_enabled"):
        provider = search_provider or search_provider_from_env(
            settings.get("search_provider", "searxng")
        )
        if provider is not None:
            registry.add(web_search_tool(provider))
            registry.add(web_fetch_tool())
    for tool in extra_tools or []:
        registry.add(tool)
    return registry
