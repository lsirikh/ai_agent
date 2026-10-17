"""
한국 날씨 도구 (get_weather).

- 지명 → 좌표: 한국 시·도와 주요 도시는 내장 표(오프라인). 그 밖은 Open-Meteo 지명 검색.
  Open-Meteo 는 '서울' 은 못 찾고 '서울특별시' 만 찾으므로
  행정구역 접미사를 붙여 다시 찾는다.
- 예보: Open-Meteo(키 없음, 인터넷 필요). 실패하면 지어내지 않고 오류로 돌려준다.
"""

from typing import Awaitable, Callable, Optional

from .tools import Tool, ToolResult

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
HTTP_TIMEOUT_SECONDS = 10.0

# 시·도와 주요 도시 (위도, 경도)
BUILTIN_PLACES: dict = {
    "서울": (37.5665, 126.9780),
    "부산": (35.1796, 129.0756),
    "대구": (35.8714, 128.6014),
    "인천": (37.4563, 126.7052),
    "광주": (35.1595, 126.8526),
    "대전": (36.3504, 127.3845),
    "울산": (35.5384, 129.3114),
    "세종": (36.4800, 127.2890),
    "수원": (37.2636, 127.0286),
    "성남": (37.4200, 127.1265),
    "고양": (37.6584, 126.8320),
    "용인": (37.2411, 127.1776),
    "창원": (35.2280, 128.6811),
    "청주": (36.6424, 127.4890),
    "전주": (35.8242, 127.1480),
    "천안": (36.8151, 127.1139),
    "포항": (36.0190, 129.3435),
    "제주": (33.4996, 126.5312),
    "서귀포": (33.2541, 126.5601),
    "강릉": (37.7519, 128.8761),
    "춘천": (37.8813, 127.7298),
    "원주": (37.3422, 127.9202),
    "여수": (34.7604, 127.6622),
    "목포": (34.8118, 126.3922),
    "안동": (36.5684, 128.7294),
    "경주": (35.8562, 129.2247),
    "김해": (35.2285, 128.8894),
    "평택": (36.9921, 127.1129),
    "속초": (38.2070, 128.5918),
}
_ALIASES = {
    "서울특별시": "서울",
    "서울시": "서울",
    "부산광역시": "부산",
    "대구광역시": "대구",
    "인천광역시": "인천",
    "광주광역시": "광주",
    "대전광역시": "대전",
    "울산광역시": "울산",
    "세종특별자치시": "세종",
    "제주도": "제주",
    "제주특별자치도": "제주",
    "제주시": "제주",
}
_SUFFIXES = ["", "시", "군", "구", "동", "특별시", "광역시"]

# WMO 날씨 코드 → 한국어
_WEATHER_CODES = {
    0: "맑음",
    1: "대체로 맑음",
    2: "구름 조금",
    3: "흐림",
    45: "안개",
    48: "안개",
    51: "약한 이슬비",
    53: "이슬비",
    55: "강한 이슬비",
    56: "어는 이슬비",
    57: "어는 이슬비",
    61: "약한 비",
    63: "비",
    65: "강한 비",
    66: "어는 비",
    67: "어는 비",
    71: "약한 눈",
    73: "눈",
    75: "강한 눈",
    77: "싸락눈",
    80: "약한 소나기",
    81: "소나기",
    82: "강한 소나기",
    85: "눈 소나기",
    86: "강한 눈 소나기",
    95: "뇌우",
    96: "우박을 동반한 뇌우",
    99: "강한 우박을 동반한 뇌우",
}

_CURRENT_FIELDS = [
    "temperature_2m",
    "weather_code",
    "relative_humidity_2m",
    "wind_speed_10m",
]
_DAILY_FIELDS = [
    "temperature_2m_max",
    "temperature_2m_min",
    "precipitation_probability_max",
]

Geocode = Callable[[str], Awaitable[Optional[dict]]]
Forecast = Callable[[float, float, str], Awaitable[dict]]


async def _http_json(url: str, params: dict) -> dict:
    import httpx

    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as client:
        response = await client.get(url, params=params)
        response.raise_for_status()
        return response.json()


async def open_meteo_geocode(name: str) -> Optional[dict]:
    data = await _http_json(
        GEOCODE_URL, {"name": name, "count": 1, "language": "ko", "countryCode": "KR"}
    )
    results = data.get("results") or []
    if not results:
        return None
    r = results[0]
    return {"name": r["name"], "latitude": r["latitude"], "longitude": r["longitude"]}


async def open_meteo_forecast(latitude: float, longitude: float, tz: str) -> dict:
    return await _http_json(
        FORECAST_URL,
        {
            "latitude": latitude,
            "longitude": longitude,
            "current": ",".join(_CURRENT_FIELDS),
            "daily": ",".join(_DAILY_FIELDS),
            "timezone": tz,
            "forecast_days": 1,
        },
    )


async def resolve_place(
    name: str, geocode: Geocode = open_meteo_geocode
) -> Optional[dict]:
    key = _ALIASES.get(name.strip(), name.strip())
    if key in BUILTIN_PLACES:
        lat, lon = BUILTIN_PLACES[key]
        return {"name": key, "latitude": lat, "longitude": lon}
    for suffix in _SUFFIXES:
        place = await geocode(key + suffix)
        if place:
            return place
    return None


def _summary(place: str, data: dict) -> str:
    now = data.get("current", {})
    daily = data.get("daily", {})

    def first(key):
        values = daily.get(key) or [None]
        return values[0]

    condition = _WEATHER_CODES.get(now.get("weather_code"), "알 수 없음")
    parts = [f"{place} 현재 날씨: {condition}"]
    if now.get("temperature_2m") is not None:
        parts.append(f"기온 {now['temperature_2m']:.0f}도")
    high, low = first("temperature_2m_max"), first("temperature_2m_min")
    if high is not None and low is not None:
        parts.append(f"오늘 최고 {high:.0f}도·최저 {low:.0f}도")
    if first("precipitation_probability_max") is not None:
        parts.append(f"강수 확률 {first('precipitation_probability_max'):.0f}%")
    if now.get("relative_humidity_2m") is not None:
        parts.append(f"습도 {now['relative_humidity_2m']:.0f}%")
    if now.get("wind_speed_10m") is not None:
        parts.append(f"바람 {now['wind_speed_10m']:.0f}km/h")
    return ", ".join(parts) + " (출처: Open-Meteo)"


def weather_tool(
    default_location: str,
    timezone_name: str,
    fetch_forecast: Forecast = open_meteo_forecast,
    geocode: Geocode = open_meteo_geocode,
) -> Tool:
    async def run(args: dict) -> ToolResult:
        name = str(args.get("location") or default_location).strip()
        try:
            place = await resolve_place(name, geocode=geocode)
            if place is None:
                return ToolResult(f"'{name}' 지역을 찾지 못했습니다", is_error=True)
            where = (place["latitude"], place["longitude"], timezone_name)
            try:
                data = await fetch_forecast(*where)
            except Exception:  # Open-Meteo 가 가끔 503 — 한 번 더 부른다(실측)
                data = await fetch_forecast(*where)
        except Exception as error:  # 네트워크 실패 등 — 지어내지 않는다
            return ToolResult(
                f"날씨 정보를 가져오지 못했습니다: {error}", is_error=True
            )
        return ToolResult(
            _summary(place["name"], data),
            sources=[{"title": "Open-Meteo", "url": "https://open-meteo.com"}],
        )

    return Tool(
        name="get_weather",
        description=(
            "한국 지역의 현재 날씨와 오늘 최고·최저 기온, 강수 확률을 알려 준다. "
            f"지역을 말하지 않으면 {default_location} 기준."
        ),
        parameters={
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "지역 이름 (예: 서울, 부산)",
                }
            },
        },
        run=run,
        announce="날씨를 확인해 볼게요.",
    )
