"""
채팅 이미지 첨부 (사용자 요청 2026-10-17: 멀티모달 채팅)

- 첨부 이미지는 비전 모델이 한국어로 설명 → 'image_description' 이벤트로 먼저 보여 준다
  (LLM 이 화면을 어떻게 이해했는지 사용자가 확인)
- 그 설명을 이번 질문의 근거로 붙이고, 대화 기록에도 남긴다(나중에 '학습해' 로 기억)
- 잘못된 첨부(이미지가 아님 · 3장 이상)는 거절한다
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from services.backend.app.services import conversation
from tests.backend.test_chat_tools import db, run_chat, scripted_vllm, text_chunk  # noqa: F401

PNG = "data:image/png;base64,iVBORw0KGgo="


@pytest.mark.asyncio
async def test_image_is_described_shown_and_used_as_reference(db) -> None:  # noqa: F811
    from services.backend.app.services.chat_service import ChatService

    asked = []

    async def describe(image, question):
        asked.append((image, question))
        return "엑셀 창 위에 'Microsoft Office 인증 마법사' 창이 떠 있다"

    llm, requests = scripted_vllm([text_chunk("인증 마법사를 닫아 보세요.")])
    service = ChatService(llm_client=llm, image_describer=describe)
    session_id = await conversation.get_active_session_id()

    events = [
        e
        async for e in service.process_message(
            session_id, "엑셀이 왜 안 닫혀?", use_rag=False, images=[PNG]
        )
    ]

    assert asked == [(PNG, "엑셀이 왜 안 닫혀?")]
    shown = [e for e in events if e["type"] == "image_description"]
    assert shown and "인증 마법사" in shown[0]["content"]
    question = requests[0]["messages"][-1]["content"]
    assert "[첨부 이미지 설명]" in question and "인증 마법사" in question
    assert events[-1]["content"] == "인증 마법사를 닫아 보세요."
    saved_user = [m for m in db.messages if m["role"] == "user"][-1]["content"]
    assert "엑셀이 왜 안 닫혀?" in saved_user and "인증 마법사" in saved_user


@pytest.mark.asyncio
async def test_answer_still_comes_when_image_cannot_be_read(db) -> None:  # noqa: F811
    from services.backend.app.services.chat_service import ChatService

    async def broken(image, question):
        raise OSError("vision down")

    llm, requests = scripted_vllm([text_chunk("이미지를 읽지 못했어요.")])
    service = ChatService(llm_client=llm, image_describer=broken)
    session_id = await conversation.get_active_session_id()

    events = await run_chat_with_image(service, session_id)

    shown = [e for e in events if e["type"] == "image_description"]
    assert shown and "읽지 못했" in shown[0]["content"]
    assert events[-1]["type"] == "complete"


async def run_chat_with_image(service, session_id):
    return [
        e
        async for e in service.process_message(
            session_id, "이거 봐 줘", use_rag=False, images=[PNG]
        )
    ]


@pytest.mark.parametrize(
    "images",
    [["http://example.com/a.png"], ["data:text/html;base64,PGg+"], [PNG, PNG, PNG]],
)
def test_route_rejects_bad_attachments(images) -> None:
    from services.backend.app.routes import chat

    app = FastAPI()
    app.include_router(chat.router)

    response = TestClient(app).post(
        "/api/chat/message", json={"message": "봐 줘", "images": images}
    )

    assert response.status_code == 422
