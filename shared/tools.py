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
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Optional
from urllib.parse import urljoin, urlsplit

import httpx

from .context_builder import _truncate_to_tokens
from .skills import load_skills

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
    # 확인·실행 전에 인자를 고친다 (예: 브라우저 주소 'newtab' → 'about:blank')
    normalize: Optional[Callable[[dict], dict]] = None

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
        # 지역·시간 (설정 화면 "지역 및 시간", 데스크톱이 PC 시간대로 맞출 수 있다)
        "timezone": os.getenv("TOOLS_TIMEZONE", DEFAULT_TIMEZONE),
        "locale": os.getenv("TOOLS_LOCALE", "ko-KR"),
        "location": os.getenv("DEFAULT_LOCATION", "서울"),
        "weather_enabled": os.getenv("WEATHER_ENABLED", "true").lower() == "true",
        "follow_pc_timezone": True,
    }


async def load_tool_settings(redis: Any) -> dict:
    """
    설정 API 로 바꾼 값(Redis) → 없으면 환경변수 기본값.
    설정 화면에서 끈 내장 스킬(disabled_tools)도 함께 싣는다.
    """
    settings = default_tool_settings()
    settings["disabled_tools"] = (await load_skills(redis))["disabled_tools"]
    if redis is None:
        return settings
    try:
        raw = await redis.get(TOOL_SETTINGS_KEY)
        if raw:
            settings.update(json.loads(raw))
    except Exception:
        pass
    return settings


TIME_REFERENCE_RULE = (
    "(참고용: 사용자가 시각·날짜·요일을 물을 때만 쓰고, "
    "그 밖의 답에는 시각·날짜를 말하지 마세요.)"
)


# 시각·날짜가 답에 필요한 질문(지금·오늘·내일·요일·올해·요즘 …)
_TIME_WORDS = re.compile(
    r"몇\s*시|시각|시간|날짜|며칠|요일|오늘|내일|모레|어제|그제|지금|현재|"
    r"올해|작년|내년|이번\s*(주|달|해)|지난\s*(주|달)|다음\s*(주|달)|요즘|최근|최신|"
    r"오전|오후|아침|저녁|밤|주말|몇\s*(년|월|일)"
)


def needs_time_reference(question: str) -> bool:
    """
    이번 질문에 '지금 시각' 근거를 붙일지. 시나리오 시험(2026-10-18): 늘 붙이면
    '반가워'·'농담 해줘' 같은 답에도 시각을 끼워 넣었다(규칙을 붙여도 30개 중 5개).
    """
    return bool(_TIME_WORDS.search(question or ""))


async def current_time_reference(redis: Any) -> str:
    """매 턴 이번 질문에 붙이는 시각 근거 — 설정한 시간대로."""
    settings = await load_tool_settings(redis)
    # 쓸 때를 정해 주지 않으면 묻지 않은 답에도 '현재 시각은 …' 으로 시작했다(실측)
    return (
        f"지금 시각: {current_time_text(settings.get('timezone'))}\n"
        f"{TIME_REFERENCE_RULE}"
    )


# 열기·켜기·접속처럼 무언가를 해 달라는 요청 (질문 끝이나 '…해 줘' 꼴)
_ACTION = re.compile(
    r"(열어|켜|실행해|접속해|들어가)(서\s|\s*(줘|줄래|줄\s*수|주세요|봐))"
    r"|(열어|켜|실행해|접속해|들어가)\s*[.?!~]*$"
)
# '다음' 은 사이트로 쓸 때만('다음 단계' · '다음에 또' 는 아니다)
# — 시나리오 시험에서 '다음'·'깃허브' 를 사이트로 보지 않았다
_BROWSER = re.compile(
    r"크롬|브라우저|사이트|홈페이지|웹\s*페이지|네이버|구글|유튜브|깃허브|github|"
    r"다음(?=\s*(사이트|에서|으로|홈|열|켜|띄워|들어가|접속))",
    re.IGNORECASE,
)
# 브라우저로 하는 일: 어미와 상관없이 본다
# (실측: STT 가 '들어가 줘' 를 '들어가죠', '열어서' 를 '열어가지고' 로 적었다)
_BROWSER_ACTION = re.compile(
    r"열|켜|들어가|접속|이동|띄워|검색|입력|클릭|눌러|틀어|가\s*줘"
)
# 그중 검색 도구로는 대신할 수 없는 일(열기·접속·누르기)
_BROWSER_OPEN = re.compile(r"열|켜|들어가|접속|이동|띄워|클릭|눌러|틀어")
_YOUTUBE = re.compile(r"유튜브|youtube", re.IGNORECASE)
_DRAW = re.compile(r"그려|그리고\s*싶|드로잉|스케치")
_PLAY = re.compile(r"틀어|재생|플레이|들려|틀\s*수")
# MCP 데스크톱(서버__open_app · 서버__write_document)
_PROGRAM = re.compile(r"메모장|노트패드|워드|엑셀|파워\s*포인트|피피티|계산기|그림판")
_WRITE = re.compile(r"저장|작성|써|적어|만들어|기록")
_WEATHER = re.compile(r"날씨|기온|우산|비\s*(와|오|올|가)|눈\s*(와|오|올|이)")
_SEARCH = re.compile(r"검색|인터넷|뉴스|최신")
# 구체적인 사실(장소·가게·시장 등)을 묻는 질문은 검색 뒤 답한다
# (실측: 검색 없이 '원당시장(동작구 원당동)' 이라고 지어냈다)
_PLACE = re.compile(
    r"시장|마트|가게|식당|맛집|카페|병원|학교|회사|공원|아파트|동네|호텔|백화점|상가|"
    r"도서관|박물관|대학|역(?=\s|$|[?.!]|에|근처|앞)|"
    r"월드|랜드|타워|공항|터미널|해수욕장|궁(?=\s|$|[?.!]|은|이|에)"
)
_ASK_INFO = re.compile(
    r"알아|아세요|알고\s*있|알려|어디|뭐야|뭐예요|어때|정보|소개|설명|있어|있나|어떤"
)
# 노래·영화·책·인물처럼 기억으로 답하면 지어내기 쉬운 것
# (실측: '좋은 날' 을 '2008년 5월 8일 발매한 10번째 싱글' 이라고 지어냈다)
_MEDIA = re.compile(r"노래|곡|앨범|가수|영화|드라마|배우|감독|책|작가|멤버|그룹")
_ASK_KNOW = re.compile(r"알아\s*[?]|아세요|알고\s*있어")
_PERSONAL = re.compile(
    r"(^|\s)(내|나|저|제|우리|너|네가|당신)(\s|$|의|가|는|를|한테|랑)"
)


def _asks_specific_fact(question: str) -> bool:
    if _PERSONAL.search(question):
        return False
    return bool(_ASK_INFO.search(question)) and bool(
        _PLACE.search(question)
        or _MEDIA.search(question)
        or _ASK_KNOW.search(question)
    )

# 질문이 이렇다면 그 도구가 분명히 필요하다 (앞쪽이 우선)
_SAVED_FILE = re.compile(r"\.(txt|docx|xlsx|pptx)\b")
_READ = re.compile(r"내용|읽어|열람")
_FILE_LIST = re.compile(r"(파일|폴더).*(목록|뭐|무엇|있어|보여|알려)|저장된\s*파일")

_REMEMBER = re.compile(r"기억해|학습해|학습\s*시켜|외워")

_REQUIRED_TOOLS = [
    ("learn_note", _REMEMBER.search),
    # 그림 그리기(그림판을 열어 마우스로 그린다) — '그림판 열어' 보다 먼저
    ("draw_picture", _DRAW.search),
    ("read_test_file", lambda q: _SAVED_FILE.search(q) and _READ.search(q)),
    ("list_test_files", _FILE_LIST.search),
    ("write_document", lambda q: _PROGRAM.search(q) and _WRITE.search(q)),
    ("open_app", lambda q: _PROGRAM.search(q) and _ACTION.search(q)),
    # 유튜브에서 틀기는 전용 도구로(실측: 동영상 대신 '채널로 이동' 을 눌렀다)
    ("play_youtube", lambda q: _YOUTUBE.search(q) and _PLAY.search(q)),
    # MCP 브라우저(서버__browser_navigate). 크롬·사이트를 직접 말했으면 날씨보다 먼저
    # (실측: '네이버 검색창에 오늘 날씨를 입력해' 가 날씨 도구로 갔다)
    ("browser_navigate", lambda q: _BROWSER.search(q) and _BROWSER_ACTION.search(q)),
    ("get_weather", _WEATHER.search),
    ("web_search", lambda q: _SEARCH.search(q) or _asks_specific_fact(q)),
]

CANNOT_DO_REPLY = (
    "죄송해요, 지금은 프로그램을 열거나 사이트에 접속할 수 없어요. "
    "그런 일을 하는 도구가 연결되어 있지 않아요."
)


def _offered_tool(name: str, offered) -> Optional[str]:
    """제공된 도구 중 name 인 것 (MCP 도구는 '서버__도구' 이름으로 온다)."""
    for candidate in offered:
        if candidate == name or candidate.endswith("__" + name):
            return candidate
    return None


def required_tool(question: str, offered) -> Optional[str]:
    """
    분명히 도구가 필요한 질문이면 그 도구 이름. 같은 질문에 도구 없이 답한 기록이
    있으면 Qwen2.5-7B 는 auto 에서 도구를 부르지 않고 옛 답을 베낀다(실측).
    """
    question = question or ""
    for name, needs in _REQUIRED_TOOLS:
        tool = _offered_tool(name, offered)
        if tool and needs(question):
            return tool
    return None


# 브라우저 작업 단계: 열기 다음에 입력·클릭을 해야 하는 요청
_TYPE_INTENT = re.compile(r"입력|검색|써\s*줘|적어")
_CLICK_INTENT = re.compile(r"클릭|눌러")


def required_tools(question: str, offered) -> list:
    """
    라운드마다 지정할 도구(첫 라운드부터). 브라우저는 열기 → 입력 → 클릭 순서.
    열기만 지정하면 모델이 입력하지 않고 '입력하고 검색했습니다' 라고 지어냈다(실측).
    """
    first = required_tool(question, offered)
    if not first:
        return []
    plan = [first]
    if first.endswith("browser_navigate"):
        steps = (("browser_type", _TYPE_INTENT), ("browser_click", _CLICK_INTENT))
        for name, intent in steps:
            tool = _offered_tool(name, offered)
            if tool and intent.search(question or ""):
                plan.append(tool)
    return plan


def unavailable_action_reply(question: str, offered) -> Optional[str]:
    """
    열기·접속을 해 달라는데 그걸 할 도구가 없으면 모델 대신 할 답.
    도구 없이 맡기면 "크롬을 열었습니다" 라고 지어냈다(프롬프트로 막아도 8/12, 실측).
    """
    question = question or ""
    if _PROGRAM.search(question) and (
        _ACTION.search(question) or _WRITE.search(question)
    ):
        return None if required_tool(question, offered) else CANNOT_DO_REPLY
    if _BROWSER.search(question) and _BROWSER_OPEN.search(question):
        return None if _offered_tool("browser_navigate", offered) else CANNOT_DO_REPLY
    if not _ACTION.search(question):
        return None
    return None if required_tool(question, offered) else CANNOT_DO_REPLY


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


DEFAULT_TIMEZONE = "Asia/Seoul"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _now(tz: Optional[str] = None) -> datetime:
    """설정한 시간대(없으면 TOOLS_TIMEZONE, 기본 Asia/Seoul)의 지금 시각."""
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

    name = tz or os.getenv("TOOLS_TIMEZONE", DEFAULT_TIMEZONE)
    try:
        return _utc_now().astimezone(ZoneInfo(name))
    except (ZoneInfoNotFoundError, ValueError):
        return _utc_now().astimezone(ZoneInfo(DEFAULT_TIMEZONE))


def current_time_text(tz: Optional[str] = None) -> str:
    """지금 날짜·요일·시각(한국어). get_time 도구와 매 턴 시각 근거가 같이 쓴다."""
    now = _now(tz)
    weekday = "월화수목금토일"[now.weekday()]
    return now.strftime(f"%Y년 %m월 %d일 ({weekday}요일) %H시 %M분 %Z(UTC%z)")


def get_time_tool(tz: Optional[str] = None) -> Tool:
    async def run(_: dict) -> ToolResult:
        return ToolResult(current_time_text(tz))

    return Tool(
        name="get_time",
        description=(
            "현재 날짜와 시각을 알려 준다. 오늘 날짜·요일·지금 시각 질문에 쓴다."
        ),
        parameters={"type": "object", "properties": {}},
        run=run,
    )


GET_TIME = get_time_tool()


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


# ===== learn_note (학습 노트: 지식 베이스에 기억해 둔다) =====

KNOWLEDGE_UPLOAD_URL = os.getenv(
    "KNOWLEDGE_UPLOAD_URL", "http://backend:8000/api/knowledge/upload"
)
LEARN_NOTE_CATEGORY = "학습노트"


def learn_note_tool(
    upload_url: str = KNOWLEDGE_UPLOAD_URL, transport: Any = None
) -> Tool:
    """
    사용자가 "기억해/학습해" 라고 한 상황을 지식 베이스에 학습 노트로 저장한다.
    다음부터 채팅·음성이 관련 질문에서 이 노트를 찾아 쓴다
    (모델 가중치를 바꾸는 학습이 아니라 기억).
    """

    async def run(args: dict) -> ToolResult:
        title = str(args.get("title") or "학습 노트").strip()[:80]
        content = str(args.get("content") or "").strip()
        if not content:
            return ToolResult("기억할 내용이 비어 있습니다", is_error=True)
        note = (
            f"# 학습 노트: {title}\n\n{content}\n\n"
            "(EdgeVoice 대화에서 사용자가 기억해 달라고 한 내용 · "
            f"{current_time_text()})\n"
        )
        note_file = (f"학습노트-{title}.md", note.encode("utf-8"), "text/markdown")
        files = {"file": note_file}
        data = {"title": f"학습노트: {title}", "category": LEARN_NOTE_CATEGORY}
        try:
            async with httpx.AsyncClient(timeout=60.0, transport=transport) as client:
                response = await client.post(upload_url, files=files, data=data)
                response.raise_for_status()
        except Exception as error:
            message = f"학습 노트를 저장하지 못했습니다: {error}"
            return ToolResult(message, is_error=True)
        return ToolResult(f"학습 노트 '{title}' 를 지식 베이스에 저장했습니다.")

    return Tool(
        name="learn_note",
        description=(
            "사용자가 기억하거나 학습하라고 한 내용을 지식 베이스에 저장한다. "
            "상황(첨부 이미지 설명 포함)·원인·해결 방법을 나중에 읽어도 알 수 있게 "
            "구체적으로 적는다."
        ),
        parameters={
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "짧은 제목"},
                "content": {"type": "string", "description": "기억할 내용"},
            },
            "required": ["title", "content"],
        },
        run=run,
        announce="기억해 둘게요.",
    )


def build_registry(
    settings: dict, extra_tools: Optional[list] = None, search_provider: Any = None
) -> ToolRegistry:
    """
    이번 턴에 쓸 도구. 인터넷 도구는 설정이 켜져 있고 검색 제공자가 있을 때만 넣는다.
    설정 화면에서 끈 내장 스킬(disabled_tools)은 넣지 않는다.
    """
    registry = ToolRegistry()
    disabled = set(settings.get("disabled_tools") or [])

    def add(tool: Tool) -> None:
        if tool.name not in disabled:
            registry.add(tool)

    # learn_note(학습 노트)는 지식 베이스에 쓰는 오프라인 로컬 도구라
    # (스킬에서 끄지 않았으면) 항상 넣는다
    add(get_time_tool(settings.get("timezone")))
    add(learn_note_tool())
    # 날씨는 인터넷(Open-Meteo)을 쓰므로 인터넷 도구가 켜져 있을 때만 (오프라인 원칙)
    if settings.get("internet_enabled") and settings.get("weather_enabled"):
        from .weather import weather_tool

        add(
            weather_tool(
                default_location=settings.get("location") or "서울",
                timezone_name=settings.get("timezone") or DEFAULT_TIMEZONE,
            )
        )
    if settings.get("internet_enabled"):
        provider = search_provider or search_provider_from_env(
            settings.get("search_provider", "searxng")
        )
        if provider is not None:
            add(web_search_tool(provider))
            add(web_fetch_tool())
    for tool in extra_tools or []:
        registry.add(tool)
    return registry
