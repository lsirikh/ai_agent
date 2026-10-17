"""
멀티모달 채팅 · 학습 노트 (사용자 요청 2026-10-17)

- 채팅에 첨부한 이미지는 비전 모델(vision 서비스)이 한국어로 설명하고,
  대화 LLM 은 그 설명을 근거로 답한다.
- "기억해/학습해" 라고 하면 learn_note 가 그 상황을 지식 베이스에 학습 노트로 저장해
  다음부터 채팅·음성이 찾아 쓴다(모델 가중치를 바꾸는 학습이 아니라 기억).
"""

import json

import httpx
import pytest

PNG = "data:image/png;base64,iVBORw0KGgo="


@pytest.mark.asyncio
async def test_describe_image_sends_image_and_korean_instruction() -> None:
    from shared import vision

    sent = []

    def handler(request):
        sent.append(json.loads(request.content))
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "엑셀 창이 떠 있다"}}]}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        text = await vision.describe_image(PNG, "왜 안 닫혀?", client=client)

    assert text == "엑셀 창이 떠 있다"
    parts = sent[0]["messages"][-1]["content"]
    assert {"type": "image_url", "image_url": {"url": PNG}} in parts
    prompt = next(p["text"] for p in parts if p["type"] == "text")
    assert "한국어" in prompt and "왜 안 닫혀?" in prompt


def test_should_accept_only_image_data_urls() -> None:
    from shared import vision

    assert vision.valid_image(PNG)
    assert not vision.valid_image("http://example.com/a.png")
    assert not vision.valid_image("data:text/html;base64,PGh0bWw+")
    big = "data:image/png;base64," + "A" * (vision.MAX_IMAGE_BYTES * 2)
    assert not vision.valid_image(big)


@pytest.mark.asyncio
async def test_learn_note_saves_markdown_note_to_knowledge_base() -> None:
    from shared.tools import learn_note_tool

    uploads = []

    def handler(request):
        uploads.append(request.content.decode("utf-8", "replace"))
        return httpx.Response(200, json={"document_id": "d1", "chunks": 1})

    tool = learn_note_tool(
        "http://backend:8000/api/knowledge/upload",
        transport=httpx.MockTransport(handler),
    )
    result = await tool.run(
        {"title": "엑셀이 안 닫힘", "content": "인증 마법사 창이 떠서 닫히지 않는다"}
    )

    assert not result.is_error
    body = uploads[0]
    assert "학습노트" in body and "엑셀이 안 닫힘" in body
    assert "인증 마법사 창이 떠서 닫히지 않는다" in body


def test_registry_always_offers_learn_note() -> None:
    from shared.tools import build_registry, default_tool_settings

    assert "learn_note" in build_registry(default_tool_settings()).names()


@pytest.mark.parametrize(
    "question", ["이 상황 기억해 줘", "이거 학습해", "앞으로 이렇게 하라고 외워 둬"]
)
def test_remember_requests_force_learn_note(question) -> None:
    from shared.tools import required_tool

    assert required_tool(question, ["get_time", "learn_note"]) == "learn_note"
