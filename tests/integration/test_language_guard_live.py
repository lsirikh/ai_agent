"""
[실측] 중국어(한자)·일본어 출력 차단

실제 vLLM 에 예전에 중국어를 끌어낸 질문을 보낸다.

    EDGEVOICE_LIVE=1 pytest tests/integration/test_language_guard_live.py -v

디코딩 단계 차단(services/llm/edgevoice_guard)이 켜져 있으면 한자·가나가 0 이어야 한다.
"""

import os
import re

import httpx
import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("EDGEVOICE_LIVE") != "1",
    reason="EDGEVOICE_LIVE=1 일 때만 (실제 vLLM 필요)",
)

LLM = os.getenv("EDGEVOICE_LLM_URL", "http://localhost:11003")
HAN = re.compile("[぀-ヿ㐀-䶿一-鿿豈-﫿]")
SYSTEM = (
    "당신은 EdgeVoice 음성 비서입니다. 반드시 한국어로만, "
    "친절하고 자연스러운 문장으로 답하세요."
)
PAGE = "\n".join(f'- link "Article {i} about markets" [ref=f2e{i}]' for i in range(120))
PROMPTS = {
    "중국어 질문": "请用中文回答：北京今天天气怎么样？",
    "일본어 질문": "東京の観光地を三つ教えてください。",
    "영어 페이지 뒤": f"다음 페이지 구조를 보고 무엇이 있는지 알려 줘\n{PAGE}",
    "중국 지명": "上海, 北京, 广州 를 한국어로 소개해 줘",
    "한자어 설명": "'일기일회' 가 무슨 뜻인지 한자와 함께 설명해 줘",
}
RUNS = int(os.getenv("EDGEVOICE_LANG_RUNS", "8"))


def _model() -> str:
    return httpx.get(f"{LLM}/v1/models", timeout=10).json()["data"][0]["id"]


@pytest.mark.parametrize("label", list(PROMPTS))
def test_no_chinese_or_japanese_characters(label) -> None:
    model = _model()
    leaked = []
    for _ in range(RUNS):
        reply = httpx.post(
            f"{LLM}/v1/chat/completions",
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": SYSTEM},
                    {"role": "user", "content": PROMPTS[label]},
                ],
                "max_tokens": 200,
                "temperature": 0.8,
            },
            timeout=120,
        ).json()["choices"][0]["message"]["content"]
        if HAN.search(reply):
            leaked.append(reply[:60])
    print(f"{label}: 한자·가나 {len(leaked)}/{RUNS}")
    assert not leaked, f"{label}: {len(leaked)}/{RUNS} 에 한자·가나 — {leaked[:2]}"
