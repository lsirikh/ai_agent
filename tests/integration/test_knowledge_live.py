"""
[live] 지식베이스 — 가상 위키 문서를 넣고, RAG 로 답하는지 확인한 뒤 지운다.
EDGEVOICE_LIVE=1 일 때만 돈다.

    EDGEVOICE_LIVE=1 python -m pytest tests/integration/test_knowledge_live.py

모델이 미리 알 수 없도록 실존하지 않는 연예인·도시 정보를 쓴다.
시험이 끝나면(실패해도) 넣은 문서를 모두 지운다.
주의: 채팅 시험을 위해 "새 대화"(POST /api/sessions)를 만들어 활성 세션이 바뀐다.
"""

import json
import os

import httpx
import pytest

BACKEND = os.getenv("EDGEVOICE_BACKEND_URL", "http://localhost:11000")

pytestmark = pytest.mark.skipif(
    os.getenv("EDGEVOICE_LIVE") != "1", reason="live: EDGEVOICE_LIVE=1 일 때만 실행"
)

WIKI = {
    "가상연예인위키_별빛소나타.md": (
        "# 별빛소나타 (가상 아이돌 그룹)\n\n"
        "별빛소나타는 2031년 3월 14일 데뷔한 5인조 걸그룹이다. 리더는 한서윤이고 "
        "메인 보컬은 도하린이다. 공식 팬덤 이름은 '은하수단'이며 "
        "응원봉 색은 청록색이다. "
        "데뷔곡은 '새벽 궤도'이고, 첫 정규 앨범 '유성우 일기'는 2032년에 나왔다."
    ),
    "가상한국위키_청람시.md": (
        "# 청람시 (가상 도시)\n\n"
        "청람시는 한국 동해안에 있는 가상의 항구 도시로 인구는 약 42만 7천 명이다. "
        "대표 특산물은 '푸른 배'이며 매년 10월에 푸른배 축제가 열린다. "
        "시청은 해오름로 12번지에 있다."
    ),
}


async def _chat(client: httpx.AsyncClient, session_id: str, message: str) -> dict:
    events = []
    async with client.stream(
        "POST",
        f"{BACKEND}/api/chat/message",
        json={"session_id": session_id, "message": message, "use_rag": True},
    ) as response:
        async for line in response.aiter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
    return {e["type"]: e for e in events}


@pytest.mark.asyncio
async def test_live_fictional_wiki_answers_then_is_deleted():
    doc_ids = []
    async with httpx.AsyncClient(timeout=180) as client:
        try:
            for filename, text in WIKI.items():
                response = await client.post(
                    f"{BACKEND}/api/knowledge/upload",
                    files={"file": (filename, text.encode("utf-8"), "text/markdown")},
                )
                assert response.status_code == 200, response.text
                doc_ids.append(response.json()["doc_id"])

            search = await client.post(
                f"{BACKEND}/api/knowledge/search",
                json={"query": "별빛소나타 팬덤 이름", "top_k": 3},
            )
            assert any("은하수단" in r["content"] for r in search.json()["results"])

            session_id = (await client.post(f"{BACKEND}/api/sessions")).json()[
                "session_id"
            ]
            idol = await _chat(
                client, session_id, "별빛소나타의 공식 팬덤 이름이 뭐야?"
            )
            city = await _chat(client, session_id, "청람시의 대표 특산물은 뭐야?")

            assert "은하수단" in idol["complete"]["content"], idol
            assert (
                "푸른 배" in city["complete"]["content"]
                or "푸른배" in city["complete"]["content"]
            ), city
            assert any(
                s.get("filename") == "가상연예인위키_별빛소나타.md"
                for s in idol["complete"]["sources"]
            )
        finally:
            for doc_id in doc_ids:
                await client.delete(f"{BACKEND}/api/knowledge/documents/{doc_id}")

        listed = (await client.get(f"{BACKEND}/api/knowledge/documents")).json()[
            "documents"
        ]
        assert not {d["doc_id"] for d in listed} & set(doc_ids)
        search = await client.post(
            f"{BACKEND}/api/knowledge/search",
            json={"query": "별빛소나타 팬덤 이름", "top_k": 3},
        )
        assert not any("은하수단" in r["content"] for r in search.json()["results"])
