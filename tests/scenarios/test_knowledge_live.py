"""
지식 베이스 실제 스택 시나리오 (스택이 없으면 skip).

가상 위키 문서(가수·도시·드라마)를 올리고 → 목록·조각 수·업로드 시각 → 검색 →
채팅 답에 문서에만 있는 사실이 나오는지 → 삭제 → 삭제 후 검색되지 않는지 확인한다.
가상 인물·지명이라 모델이 원래 알 수 없으므로, 답에 사실이 나오면 RAG 가 동작한 것이다.
문서는 끝에 반드시 지운다(실패해도).
"""

import json
import os
from pathlib import Path

import httpx
import pytest

BACKEND = os.getenv("EDGEVOICE_BACKEND_URL", "http://127.0.0.1:11000")
RAG = os.getenv("EDGEVOICE_RAG_URL", "http://127.0.0.1:11006")
FIXTURES = Path(__file__).parent / "fixtures" / "knowledge"

# (질문, 답에 있어야 할 사실)
QUESTIONS = [
    ("윤하람의 소속사는 어디야?", "파란별"),
    ("윤하람의 데뷔곡 제목이 뭐야?", "새벽 정류장"),
    ("해솔시의 시장은 누구야?", "박도윤"),
    ("해솔 등불 축제는 언제 열려?", "8월"),
    ("드라마 달빛 수선집의 최고 시청률은?", "14.2"),
    ("달빛 수선집 주제곡은 누가 불렀어?", "윤하람"),
]


def _alive(url: str) -> bool:
    try:
        return httpx.get(f"{url}/health", timeout=2).status_code == 200
    except httpx.HTTPError:
        return False


pytestmark = pytest.mark.skipif(
    not (_alive(BACKEND) and _alive(RAG)), reason="실행 중인 스택이 없음"
)


def _top(query: str) -> str:
    response = httpx.post(
        f"{RAG}/retrieve", json={"query": query, "top_k": 3}, timeout=30
    )
    results = response.json().get("results") or []
    return results[0]["content"] if results else ""


def _chat(question: str) -> str:
    text = ""
    with httpx.stream(
        "POST",
        f"{BACKEND}/api/chat/message",
        json={"message": question, "use_rag": True},
        timeout=120,
    ) as response:
        for line in response.iter_lines():
            if line.startswith("data:"):
                try:
                    event = json.loads(line[5:])
                except ValueError:
                    continue
                if event.get("type") == "token":
                    text += event.get("content") or ""
    return text


@pytest.fixture(scope="module")
def uploaded():
    ids: dict[str, str] = {}
    with httpx.Client(base_url=BACKEND, timeout=60) as api:
        try:
            for doc in sorted(FIXTURES.glob("*.md")):
                response = api.post(
                    "/api/knowledge/upload",
                    files={"file": (doc.name, doc.read_bytes(), "text/markdown")},
                )
                assert response.status_code == 200, response.text
                ids[doc.name] = response.json()["doc_id"]
            yield api, ids
        finally:
            for doc_id in ids.values():
                api.delete(f"/api/knowledge/documents/{doc_id}")


def test_should_list_uploaded_documents_with_chunks_and_time(uploaded) -> None:
    api, ids = uploaded
    listed = {
        d["filename"]: d
        for d in api.get("/api/knowledge/documents").json()["documents"]
    }

    for name in ids:
        assert listed[name]["chunk_count"] > 0
        assert listed[name]["uploaded_at"]


@pytest.mark.parametrize("question, fact", QUESTIONS)
def test_should_answer_from_uploaded_documents(
    uploaded, question: str, fact: str
) -> None:
    assert fact in _chat(question)


def test_should_not_find_documents_after_delete(uploaded) -> None:
    api, ids = uploaded
    for doc_id in ids.values():
        assert api.delete(f"/api/knowledge/documents/{doc_id}").status_code == 200

    names = {
        d["filename"] for d in api.get("/api/knowledge/documents").json()["documents"]
    }
    assert not set(ids) & names
    for question, fact in QUESTIONS[:3]:
        assert fact not in _top(question)
    ids.clear()
