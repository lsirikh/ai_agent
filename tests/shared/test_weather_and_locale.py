"""
지역·시간대 설정과 한국 날씨 도구 테스트 (사용자 요청 2026-10-17)

- 시간대·언어·날씨 기준 지역을 설정으로 바꾼다(기본 Asia/Seoul · ko-KR · 서울).
- 시각 문자열과 get_time 은 설정한 시간대를 쓴다.
- get_weather: 한국 시·도·주요 도시는 내장 좌표(오프라인), 그 밖은 온라인 지명 검색.
  Open-Meteo 지명 검색은 '서울' 은 못 찾고 '서울특별시' 만 찾았다(실측).
"""

from datetime import datetime, timezone

import pytest


def test_defaults_are_korea() -> None:
    from shared.tools import default_tool_settings

    s = default_tool_settings()
    assert s["timezone"] == "Asia/Seoul"
    assert s["locale"] == "ko-KR"
    assert s["location"] == "서울"
    assert s["weather_enabled"] is True
    assert s["follow_pc_timezone"] is True


def test_current_time_follows_configured_timezone() -> None:
    from unittest.mock import patch

    import shared.tools as tools

    utc = datetime(2026, 10, 17, 0, 52, tzinfo=timezone.utc)
    with patch.object(tools, "_utc_now", return_value=utc):
        assert "09시 52분" in tools.current_time_text("Asia/Seoul")
        assert "20시 52분" in tools.current_time_text("America/New_York")


@pytest.mark.parametrize("name", ["서울", "부산", "제주", "대전", "수원", "강릉"])
def test_builtin_korean_places_resolve_offline(name) -> None:
    import asyncio

    from shared.weather import BUILTIN_PLACES, resolve_place

    async def no_network(name):
        raise AssertionError("내장 지명은 온라인 검색을 하지 않는다")

    place = asyncio.run(resolve_place(name, geocode=no_network))
    assert place is not None
    assert 33 < place["latitude"] < 39 and 124 < place["longitude"] < 132
    assert name in BUILTIN_PLACES or place["name"].startswith(name)


@pytest.mark.asyncio
async def test_unknown_place_tries_administrative_suffixes_online() -> None:
    from shared.weather import resolve_place

    asked = []

    async def geocode(query):
        asked.append(query)
        if query == "판교동":
            return {"name": "판교동", "latitude": 37.39, "longitude": 127.11}
        return None

    place = await resolve_place("판교", geocode=geocode)

    assert place["name"] == "판교동"
    assert asked[0] == "판교"


@pytest.mark.asyncio
async def test_weather_tool_reports_korean_summary() -> None:
    from shared.weather import weather_tool

    async def forecast(lat, lon, tz):
        return {
            "current": {
                "temperature_2m": 18.4,
                "weather_code": 61,
                "relative_humidity_2m": 70,
                "wind_speed_10m": 3.2,
            },
            "daily": {
                "temperature_2m_max": [21.0],
                "temperature_2m_min": [12.5],
                "precipitation_probability_max": [80],
            },
        }

    tool = weather_tool(
        default_location="서울", timezone_name="Asia/Seoul", fetch_forecast=forecast
    )
    result = await tool.run({})

    assert not result.is_error
    assert "서울" in result.content
    assert "비" in result.content
    assert "18" in result.content and "21" in result.content and "80%" in result.content


@pytest.mark.asyncio
async def test_weather_tool_reports_failure_without_inventing() -> None:
    from shared.weather import weather_tool

    async def broken(lat, lon, tz):
        raise OSError("network down")

    tool = weather_tool(
        default_location="서울", timezone_name="Asia/Seoul", fetch_forecast=broken
    )
    result = await tool.run({"location": "부산"})

    assert result.is_error
    assert "날씨" in result.content


def test_registry_includes_weather_only_with_internet_and_weather_on() -> None:
    from shared.tools import build_registry, default_tool_settings

    base = default_tool_settings()
    on = {**base, "internet_enabled": True, "weather_enabled": True}

    assert "get_weather" in build_registry(on).names()
    assert "get_weather" not in build_registry({**on, "weather_enabled": False}).names()
    # 인터넷 도구가 꺼져 있으면 인터넷을 쓰는 날씨도 노출하지 않는다(오프라인 원칙)
    assert (
        "get_weather" not in build_registry({**on, "internet_enabled": False}).names()
    )


@pytest.mark.asyncio
async def test_time_reference_uses_saved_timezone() -> None:
    import json
    from unittest.mock import AsyncMock, patch

    import shared.tools as tools

    redis = AsyncMock()
    redis.get.return_value = json.dumps({"timezone": "America/New_York"})
    utc = datetime(2026, 10, 17, 0, 52, tzinfo=timezone.utc)

    with patch.object(tools, "_utc_now", return_value=utc):
        text = await tools.current_time_reference(redis)

    assert text.startswith("지금 시각:") and "20시 52분" in text


@pytest.mark.asyncio
async def test_weather_tool_retries_once_after_temporary_failure() -> None:
    # 실측: Open-Meteo 가 가끔 503 을 돌려줬다 — 바로 다시 부르면 됐다
    from shared.weather import weather_tool

    attempts = []

    async def flaky(lat, lon, tz):
        attempts.append(1)
        if len(attempts) == 1:
            raise OSError("503 Service Unavailable")
        return {"current": {"temperature_2m": 23.0, "weather_code": 0}, "daily": {}}

    tool = weather_tool(
        default_location="서울", timezone_name="Asia/Seoul", fetch_forecast=flaky
    )
    result = await tool.run({"location": "부산"})

    assert not result.is_error
    assert "맑음" in result.content and len(attempts) == 2


@pytest.mark.asyncio
async def test_time_reference_says_to_mention_time_only_when_asked() -> None:
    # 실측(2026-10-18): 시각을 묻지 않은 '말해봐'·'고마워'·'오늘 기분이 안 좋아' 에도
    # 답이 '현재 시각은 …' 으로 시작했다(6종 중 4종) — 사용자: '입 다물어'
    from unittest.mock import AsyncMock

    import shared.tools as tools

    redis = AsyncMock()
    redis.get.return_value = None

    text = await tools.current_time_reference(redis)

    assert text.startswith("지금 시각:")
    assert "물을 때만" in text


@pytest.mark.parametrize(
    "question, needed",
    [
        ("지금 몇 시야?", True), ("오늘 며칠이야?", True), ("무슨 요일이야?", True),
        ("내일 서울 날씨 어때?", True), ("올해 노벨상 수상자는?", True),
        ("요즘 환율 얼마야?", True), ("현재 시각 알려줘", True),
        ("어제 뉴스 알려줘", True),
        # 시나리오 시험(2026-10-18): 규칙을 붙여도 '반가워'·'농담 해줘' 답에 시각을
        # 끼워 넣었다(30개 중 5개) → 시각·날짜와 상관없는 질문에는 붙이지 않는다
        ("반가워", False), ("농담 하나 해줘", False), ("뭐 할 수 있어?", False),
        ("파이썬이 뭐야?", False), ("재미있는 이야기 해 줘", False),
    ],
)
def test_time_reference_only_for_time_related_questions(question, needed) -> None:
    from shared.tools import needs_time_reference

    assert needs_time_reference(question) is needed
