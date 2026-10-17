"""
브라우저(Playwright MCP) 조작 보조 — 로컬 LLM 이 크롬으로 사이트를 열고 작업하게 돕는다.

실측(2026-10-17, 네이버 첫 화면):
- 페이지 구조(스냅샷)는 75,599자 · 27,518토큰으로 문맥(16k)보다 커서
  1,500토큰에서 잘렸다.
- browser_navigate 결과에는 구조가 없어(파일로 빠짐) 모델이 페이지를 보지 못한 채
  '입력하고 검색했습니다' 라고 지어냈다.
- 모델은 'newtab' 처럼 열 수 없는 주소를 주기도 했다.
→ 주소를 정리하고, 입력칸·버튼·링크만 [ref] 와 함께 짧게 추려 결과에 붙인다.
"""

import re
from urllib.parse import quote

# 열 사이트를 말하지 않거나 새 탭을 뜻하는 값 → 빈 창
_BLANK = {"", "newtab", "new tab", "about:newtab", "chrome://newtab", "chrome://newtab/",
          "about:blank", "새 탭", "새탭", "빈 페이지", "크롬"}
# 한국어로 부르는 사이트 이름 (긴 이름 먼저)
SITE_NAMES = {
    "네이버 카페": "https://section.cafe.naver.com",
    "네이버 블로그": "https://section.blog.naver.com",
    "네이버 지도": "https://map.naver.com",
    "네이버 뉴스": "https://news.naver.com",
    "네이버": "https://www.naver.com",
    "다음": "https://www.daum.net",
    "구글": "https://www.google.com",
    "유튜브": "https://www.youtube.com",
    "깃허브": "https://github.com",
}
_DOMAIN = re.compile(r"^[\w.-]+\.[a-z]{2,}(/\S*)?$", re.IGNORECASE)

# 다룰 수 있는 요소: 입력칸 → 버튼 → 그 밖 순서로 보인다
_INPUT_ROLES = ("combobox", "searchbox", "textbox", "checkbox", "radio")
_ACTION_ROLES = ("button", "tab", "menuitem", "option")
_OTHER_ROLES = ("link",)
_ELEMENT = re.compile(r'^\s*-\s+(\w+)\s+"([^"]*)"(?:\s+\[[^\]]*\])*?.*?\[ref=(e\d+)\]')
MAX_ELEMENTS = 70

REF_HINT = (
    "요소를 다룰 때(browser_type · browser_click) target 에는 아래 [ref=…] 값"
    "(예: e60)을 그대로 쓰세요. 페이지가 바뀌면 ref 도 바뀝니다."
)


def normalize_url(url: str) -> str:
    """모델이 준 주소를 열 수 있는 주소로."""
    text = (url or "").strip()
    if text.lower() in _BLANK:
        return "about:blank"
    if re.match(r"^[a-z][a-z0-9+.-]*://", text, re.IGNORECASE) or text.startswith(
        "about:"
    ):
        return text
    for name, site in SITE_NAMES.items():
        if text.replace(" ", "") == name.replace(" ", ""):
            return site
    if _DOMAIN.match(text):
        return f"https://{text}"
    return "https://search.naver.com/search.naver?query=" + quote(text)


def compact_snapshot(content: str) -> str:
    """스냅샷에서 페이지 주소·제목과 다룰 수 있는 요소만 짧게."""
    header = [
        line.strip()
        for line in content.splitlines()
        if line.strip().startswith(("- Page URL:", "- Page Title:"))
    ]
    groups = {"input": [], "action": [], "other": []}
    for line in content.splitlines():
        match = _ELEMENT.match(line)
        if not match:
            continue
        role, name, ref = match.groups()
        if not name.strip():
            continue
        item = f'- {role} "{name}" [ref={ref}]'
        if role in _INPUT_ROLES:
            groups["input"].append(item)
        elif role in _ACTION_ROLES:
            groups["action"].append(item)
        elif role in _OTHER_ROLES:
            groups["other"].append(item)
    elements = (groups["input"] + groups["action"] + groups["other"])[:MAX_ELEMENTS]
    return "\n".join(header + elements)


# 페이지가 바뀌는 도구: 결과에 새 페이지의 요소를 붙인다
PAGE_CHANGING_TOOLS = (
    "browser_navigate", "browser_navigate_back", "browser_click", "browser_type"
)


async def with_page_elements(tool_name: str, result, take_snapshot):
    """
    브라우저 도구 결과에 다룰 수 있는 요소(ref)를 붙인다.
    - browser_snapshot: 거대한 구조를 요약으로 바꾼다
    - 페이지가 바뀌는 도구: 새로 찍은 구조의 요약을 덧붙인다
    """
    if result.is_error:
        return result
    if tool_name == "browser_snapshot":
        body = compact_snapshot(result.content)
    elif tool_name in PAGE_CHANGING_TOOLS:
        try:
            snapshot = await take_snapshot()
        except Exception:
            return result
        if snapshot.is_error:
            return result
        body = f"{result.content.strip()}\n\n{compact_snapshot(snapshot.content)}"
    else:
        return result
    return type(result)(
        f"{body}\n\n{REF_HINT}", is_error=False, sources=result.sources
    )


_SEARCH_INTENT = re.compile(r"검색")


def _named_site(question: str):
    """질문에서 부른 사이트(긴 이름 먼저)."""
    compact = (question or "").replace(" ", "")
    for name, site in SITE_NAMES.items():
        if name.replace(" ", "") in compact:
            return site
    return None


def _base_domain(host: str) -> str:
    return ".".join(host.split(".")[-2:])


def adapt_to_question(registry, question: str):
    """
    이번 질문에 맞춰 브라우저 도구 인자를 바로잡는 레지스트리.
    - 질문에서 부른 사이트와 다른 곳(실측: 'https://kr金钱兑换器')을 열려 하면
      그 사이트로
    - '검색' 요청이면 입력 뒤 제출(실측: submit=false 로 입력만 하고 끝남)
    """
    from dataclasses import replace
    from urllib.parse import urlsplit

    from .tools import ToolRegistry

    site = _named_site(question)
    submit = bool(_SEARCH_INTENT.search(question or ""))
    adapted = ToolRegistry()
    for name in registry.names():
        tool = registry.get(name)
        if name.endswith("browser_navigate") and site:
            base = tool.normalize or (lambda a: a)

            def navigate(args, base=base):
                args = base(args)
                host = urlsplit(args.get("url", "")).hostname or ""
                wrong = not host.isascii() or _base_domain(host) != _base_domain(
                    urlsplit(site).hostname
                )
                return {**args, "url": site} if wrong else args

            tool = replace(tool, normalize=navigate)
        elif name.endswith("browser_type") and submit:
            tool = replace(tool, normalize=lambda a: {**a, "submit": True})
        adapted.add(tool)
    return adapted
