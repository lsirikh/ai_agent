"""
이미지 이해 (llm: Qwen3.5-9B 이미지 입력 / 또는 따로 띄운 vision, vLLM OpenAI 호환)

채팅에 첨부한 사진·화면 캡처를 한국어로 설명한다. 대화 LLM 은 그 설명을 근거로 답한다.
"""

import os
import re
from typing import Optional

import httpx

# 기본은 llm(Qwen3.5, 이미지 입력 내장).
# 따로 띄운 vision 을 쓰려면 VISION_URL·VISION_MODEL 을 바꾼다
VISION_URL = os.getenv("VISION_URL", "http://llm:11003")
VISION_MODEL = os.getenv("VISION_MODEL", "RedHatAI/Qwen3.5-9B-quantized.w4a16")
MAX_IMAGES = 2
MAX_IMAGE_BYTES = 8 * 1024 * 1024
TIMEOUT_SECONDS = 120.0

# 실측(3회씩): '자세히 설명하세요 … 그대로 옮겨 적으세요' 는
# 3/3 '이미지를 볼 수 없다' 고 거절했고, 항목을 짚어 주는 이 문장은 3/3 설명했다
DESCRIBE_PROMPT = (
    "이미지에 보이는 것을 한국어로 설명해 줘. 프로그램 이름, 창 제목, 버튼, "
    "알림이나 오류 문구, 읽을 수 있는 글자를 적어 줘."
)

_DATA_URL = re.compile(
    r"^data:image/(png|jpe?g|gif|webp|bmp);base64,([A-Za-z0-9+/=]+)$"
)


def valid_image(data_url: str) -> bool:
    """data:image/…;base64 형식이고 크기 제한 안이면 True."""
    match = _DATA_URL.match(data_url or "")
    if not match:
        return False
    return len(match.group(2)) * 3 // 4 <= MAX_IMAGE_BYTES


async def describe_image(
    data_url: str,
    question: str = "",
    client: Optional[httpx.AsyncClient] = None,
) -> str:
    """이미지 설명(한국어). 실패하면 예외."""
    prompt = DESCRIBE_PROMPT
    if question:
        prompt += f"\n사용자가 함께 보낸 말: {question}"
    payload = {
        "model": VISION_MODEL,
        "max_tokens": 500,
        "temperature": 0.2,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": data_url}},
                    {"type": "text", "text": prompt},
                ],
            }
        ],
    }
    owned = client is None
    client = client or httpx.AsyncClient(timeout=TIMEOUT_SECONDS)
    try:
        response = await client.post(f"{VISION_URL}/v1/chat/completions", json=payload)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"].strip()
    finally:
        if owned:
            await client.aclose()
