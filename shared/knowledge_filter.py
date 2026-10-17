"""
지식 베이스(RAG) 근거 거르기 — 음성·채팅 공용.

점수만으로는 무관한 질문(실측 0.49~0.56)과 관련 질문(0.53~0.70)이 겹친다.
- 점수가 충분히 높으면(STRONG_SCORE) 그대로 쓴다.
- 애매한 구간(MIN_SCORE~STRONG_SCORE)은 질문의 핵심 단어가 조각에 실제로 있을 때만 쓴다.
"""

import os
import re

MIN_SCORE = float(os.getenv("RAG_MIN_SCORE", "0.52"))
STRONG_SCORE = float(os.getenv("RAG_STRONG_SCORE", "0.62"))

_WORD = re.compile(r"[가-힣A-Za-z0-9]{2,}")
# 단어 끝의 조사·어미(긴 것부터)
_SUFFIXES = sorted(
    [
        "에서",
        "으로",
        "에게",
        "까지",
        "부터",
        "이야",
        "이에요",
        "인가요",
        "은",
        "는",
        "이",
        "가",
        "을",
        "를",
        "의",
        "에",
        "로",
        "와",
        "과",
        "도",
        "만",
        "야",
    ],
    key=len,
    reverse=True,
)
# 질문에 흔하지만 내용을 가리지 않는 말
_STOPWORDS = {
    "오늘",
    "지금",
    "알려줘",
    "알려",
    "알려달라고",
    "뭐야",
    "어디",
    "누구",
    "어때",
    "해줘",
    "있어",
    "언제",
    "누가",
    "어떻게",
    "무엇",
    "무슨",
    "얼마",
    "정도",
    "그리고",
    "그런데",
    "방법",
    "추천해줘",
    "설명해",
    "말해",
    "궁금해",
}


def _stems(text: str) -> set:
    stems = set()
    for word in _WORD.findall(text):
        for suffix in _SUFFIXES:
            if word.endswith(suffix) and len(word) - len(suffix) >= 2:
                word = word[: -len(suffix)]
                break
        if word not in _STOPWORDS:
            stems.add(word)
    return stems


def is_relevant(query: str, content: str, score: float) -> bool:
    if score < MIN_SCORE:
        return False
    if score >= STRONG_SCORE:
        return True
    return any(stem in content for stem in _stems(query))


def relevant_results(query: str, results: list) -> list:
    return [
        r
        for r in results
        if is_relevant(query, r.get("content", ""), r.get("score", 0))
    ]
