"""
TTS 가 숫자를 한국어답게 읽도록 글로 바꾼다 (사용자 요청 2026-10-17).

'1시 20분' → '한 시 이십 분', '20도' → '이십 도'.
- 세는 말(시·시간·개·명·살·마리…) 앞: 고유어(한·두·세·스무…, 99 까지)
- 그 밖(분·초·도·년·일·원·%…): 한자어(일·이·삼…)
- 'N번째' 는 서수(첫·두·세 번째), 6월·10월은 유월·시월, '-15도' 는 영하 십오 도
- 영문과 붙은 숫자(Qwen3.5, e37, mp3)는 그대로 둔다
"""

import re

_SINO_DIGITS = "영일이삼사오육칠팔구"
_SINO_UNITS = ["", "십", "백", "천"]
_SINO_GROUPS = ["", "만", "억", "조", "경"]

_NATIVE_ONES = ["", "한", "두", "세", "네", "다섯", "여섯", "일곱", "여덟", "아홉"]
_NATIVE_TENS = ["", "열", "스물", "서른", "마흔", "쉰", "예순", "일흔", "여든", "아흔"]

# 고유어로 세는 말 (긴 것 먼저). '시' 는 1~12 만 고유어(13시 이상은 이십이 시)
NATIVE_COUNTERS = [
    "시간", "가지", "마리", "군데", "켤레", "송이", "그릇", "개", "명", "살",
    "권", "잔", "병", "대", "곳", "채", "벌", "장", "달", "시",
]
_UNIT_WORDS = {
    "°C": "도", "℃": "도", "%": "퍼센트", "km/h": "킬로미터", "km": "킬로미터",
    "kg": "킬로그램", "cm": "센티미터", "mm": "밀리미터",
}
_MONTHS = {6: "유월", 10: "시월"}

_TIME = re.compile(r"(?<![\d:])([01]?\d|2[0-4]):([0-5]\d)(?![\d:])")
_NUMBER = re.compile(
    # 영문이 바로 붙으면(e37·mp3) 숫자가 아니다 — 단, 단위 기호(km·kg·cm·mm)는 예외
    r"(?<![A-Za-z\d.])(-|−)?(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d+))?"
    r"(?!\d)(?!(?!km|kg|cm|mm)[A-Za-z])"
    r"(\s*)(번째|째|°C|℃|%|km/h|km|kg|cm|mm|[가-힣]+)?"
)


def sino(number: int) -> str:
    """한자어 읽기: 1200000 → 백이십만, 10000 → 만, 100000000 → 일억."""
    if number == 0:
        return "영"
    words, group = [], 0
    while number:
        number, part = divmod(number, 10000)
        if part:
            text = ""
            for position in range(3, -1, -1):
                digit = part // 10**position % 10
                if digit:
                    one = "" if digit == 1 and position else _SINO_DIGITS[digit]
                    text += one + _SINO_UNITS[position]
            if group == 1 and part == 1:
                text = ""  # 만 (일만이 아니라)
            words.append(text + _SINO_GROUPS[group])
        group += 1
    return "".join(reversed(words))


def native(number: int) -> str:
    """세는 말 앞 고유어: 1 한, 20 스무, 21 스물한 (100 이상은 한자어)."""
    if not 1 <= number <= 99:
        return sino(number)
    tens, ones = divmod(number, 10)
    if number == 20:
        return "스무"
    return _NATIVE_TENS[tens] + _NATIVE_ONES[ones]


def _ordinal(number: int) -> str:
    return "첫" if number == 1 else native(number)


def _counter(word: str):
    for counter in NATIVE_COUNTERS:
        if word.startswith(counter):
            return counter
    return None


def _read(match: re.Match) -> str:
    sign, whole, fraction, space, after = match.groups()
    after = after or ""
    number = int(whole.replace(",", ""))
    if after in ("번째", "째"):
        return f"{_ordinal(number)} {after}"
    if after in _UNIT_WORDS:
        after, unit_space = _UNIT_WORDS[after], " "
    else:
        unit_space = " " if after else space
    counter = _counter(after)
    if fraction:
        text = sino(number) + " 점 " + "".join(_SINO_DIGITS[int(d)] for d in fraction)
    elif counter == "시" and after.startswith("시") and not after.startswith("시간"):
        text = native(number) if 1 <= number <= 12 else sino(number)
    elif counter and not after.startswith("시"):
        text = native(number)
    elif counter == "시간":
        text = native(number)
    elif after.startswith("월") and number in _MONTHS:
        return _MONTHS[number] + after[1:]
    else:
        text = sino(number)
    if sign:
        text = ("영하 " if after.startswith("도") else "마이너스 ") + text
    return f"{text}{unit_space}{after}"


def read_numbers(text: str) -> str:
    """TTS 로 보낼 문장의 숫자를 한국어 읽기로."""
    text = _TIME.sub(lambda m: f"{int(m.group(1))}시 {int(m.group(2))}분", text)
    return _NUMBER.sub(_read, text)
