"""
막을 토큰 고르기 (vLLM 없이 시험할 수 있게 따로 둔다).

한국어 비서는 한자·가나·전각 문장부호를 낼 일이 없다. 이 글자가 든 토큰을 막으면
모델이 중국어·일본어로 흘러가는 길이 처음부터 없다. 한글이 든 토큰은 막지 않는다.
"""

import re
from typing import Callable, Optional

# 한자(확장 A·통합·호환) · 히라가나·가타카나 · CJK 기호/문장부호 · 전각 ASCII·문장부호
# (반각 가타카나·반각 한글 FF61-FFDC 는 한글과 섞여 있어 막지 않는다)
BANNED = re.compile("[　-〿぀-ヿ㐀-䶿一-鿿豈-﫿！-｠]")
HANGUL = re.compile("[가-힣ᄀ-ᇿ㄰-㆏]")


def is_banned_text(piece: str) -> bool:
    return bool(BANNED.search(piece)) and not HANGUL.search(piece)


# 한자·가나의 UTF-8 첫 바이트(U+3000-U+9FFF). 한글 음절은 0xEA-0xED 로 겹치지 않는다
HAN_LEAD_BYTES = frozenset(range(0xE3, 0xEA))


def builds_han(raw: bytes, piece: str) -> bool:
    """
    바이트 조각 토큰이 한자를 만들 수 있으면 True.
    실측: 글자 토큰만 막았더니 바이트 조각(예: '我' 의 첫 바이트 0xE6)을 이어 붙여
    중국어 질문 5/8 이 여전히 한자를 냈다. 한글 자모(0xE3 로 시작)는 막지 않는다.
    """
    return any(b in HAN_LEAD_BYTES for b in raw) and not HANGUL.search(piece)


def banned_token_ids(
    decode: Callable[[int], str],
    vocab_size: int,
    raw_bytes: Optional[Callable[[int], Optional[bytes]]] = None,
) -> list:
    """토큰 id → 글자(decode)·원래 바이트(raw_bytes)로 막을 id 목록."""
    banned = []
    for token_id in range(vocab_size):
        try:
            piece = decode(token_id)
            raw = raw_bytes(token_id) if raw_bytes else None
        except Exception:
            continue
        if is_banned_text(piece) or (raw and builds_han(raw, piece)):
            banned.append(token_id)
    return banned
