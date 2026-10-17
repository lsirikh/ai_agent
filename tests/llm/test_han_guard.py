"""
중국어(한자)·일본어 출력 원천 차단 (사용자 요청 2026-10-17)

로컬 LLM 이 답·도구 인자를 중국어로 내는 일이 반복됐다(실측: 'https://kr金钱兑换器',
'我现在已经在浏览器中打开了百度…'). vLLM 디코딩 단계에서 한자·가나·전각 문장부호 토큰을
고를 수 없게 막는다. Qwen2.5 어휘 151,665 개 중 27,401 개이며 한글이 섞인 토큰은 0 개다.
"""

import pytest

from services.llm.edgevoice_guard.han_tokens import banned_token_ids, is_banned_text

PIECES = {
    0: "안녕",
    1: "我",
    2: "現在",
    3: "の",
    4: "カ",
    5: "Hello",
    6: "，",
    7: "。",
    8: "ﾊﾝ",
    9: "ㄱ",
    10: "1,200",
    11: "😀",
    12: "가나다",
    13: "　",
}


@pytest.mark.parametrize(
    "piece, banned",
    [
        ("我", True),
        ("現在", True),
        ("の", True),
        ("カ", True),
        ("，", True),
        ("。", True),
        ("안녕", False),
        ("Hello", False),
        ("ㄱ", False),
        ("1,200", False),
        ("😀", False),
        ("ﾊﾝ", False),  # 반각 가타카나·반각 한글 영역은 막지 않는다(한글 반각과 섞임)
    ],
)
def test_should_ban_han_kana_and_fullwidth_punctuation_only(piece, banned) -> None:
    assert is_banned_text(piece) is banned


def test_banned_ids_never_include_hangul_tokens() -> None:
    ids = banned_token_ids(lambda i: PIECES[i], len(PIECES))

    assert ids == [1, 2, 3, 4, 6, 7, 13]
    assert all(
        "가" > PIECES[i] or not any("가" <= c <= "힣" for c in PIECES[i]) for i in ids
    )


def test_byte_pieces_that_can_build_han_are_banned_but_not_hangul() -> None:
    # 실측: 글자 단위 토큰만 막았더니 중국어 질문에 5/8 이 여전히 한자를 냈다 —
    # 바이트 조각 토큰(예: '我' 의 첫 바이트 0xE6)을 이어 붙여 한자를 만든다.
    # 한자·가나의 UTF-8 첫 바이트는 0xE3-0xE9, 한글 음절은 0xEA-0xED 라 겹치지 않는다.
    raw = {
        0: "我".encode()[:1],  # 0xE6 조각 → 막는다
        1: "가".encode()[:1],  # 0xEA 조각 → 둔다
        2: b"\x88\x91",  # 이어지는 바이트만 → 둔다(한글도 쓴다)
        3: "ㄱ".encode(),  # 한글 자모(0xE3 로 시작) → 둔다
        4: b"abc",
    }
    texts = {i: b.decode("utf-8", "replace") for i, b in raw.items()}

    ids = banned_token_ids(lambda i: texts[i], len(raw), raw_bytes=lambda i: raw[i])

    assert ids == [0]
