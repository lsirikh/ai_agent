"""
실제 스택에 붙는 페이지별 점검 (스택이 없으면 skip).

데스크톱 각 페이지가 쓰는 백엔드 API 가
실행 중인 서비스의 실제 값을 돌려주는지 확인한다.
  EDGEVOICE_BACKEND_URL  (기본 http://127.0.0.1:11000)
  EDGEVOICE_LLM_URL / _STT_URL / _TTS_URL / _WAKE_WORD_URL / _RAG_URL
    (기본: compose 의 호스트 포트)

실행: python -m pytest tests/scenarios/test_pages_live.py -v
"""

import json
import os
import uuid

import httpx
import pytest

BACKEND = os.getenv("EDGEVOICE_BACKEND_URL", "http://127.0.0.1:11000")
LLM = os.getenv("EDGEVOICE_LLM_URL", "http://127.0.0.1:11003")
STT = os.getenv("EDGEVOICE_STT_URL", "http://127.0.0.1:11001")
TTS = os.getenv("EDGEVOICE_TTS_URL", "http://127.0.0.1:11002")
WAKE_WORD = os.getenv("EDGEVOICE_WAKE_WORD_URL", "http://127.0.0.1:11005")
RAG = os.getenv("EDGEVOICE_RAG_URL", "http://127.0.0.1:11006")


def _alive(url: str) -> bool:
    try:
        return httpx.get(f"{url}/health", timeout=2).status_code == 200
    except httpx.HTTPError:
        return False


pytestmark = pytest.mark.skipif(
    not _alive(BACKEND), reason=f"실행 중인 스택이 없음 ({BACKEND})"
)


@pytest.fixture(scope="module")
def api():
    with httpx.Client(base_url=BACKEND, timeout=30) as client:
        yield client


@pytest.fixture(scope="module")
def options(api):
    response = api.get("/api/settings/options")
    assert response.status_code == 200
    return response.json()


def _info(url: str, path: str = "/info") -> dict:
    return httpx.get(f"{url}{path}", timeout=5).json()


# ===== Settings =====


def test_settings_llm_current_is_served_model(options):
    served = _info(LLM, "/v1/models")["data"][0]["id"]
    catalog = {m["id"]: m for m in options["llm_models"]}
    current = options["current"]["llm_model"]

    # 옵션 id 의 HF 경로 끝이름이 서비스 중인 id 와 같다 (대소문자·경로 접두사 무시)
    assert current in catalog, f"서비스 중인 모델 {served} 이 받아 둔 목록에 없음"
    assert (
        catalog[current]["hf_path"].split("/")[-1].lower()
        == served.split("/")[-1].lower()
    )


def test_settings_stt_current_is_service_model(options):
    assert options["current"]["stt_model"] == _info(STT)["model"]["size"]


def test_settings_tts_engine_current_is_service_engine(options):
    assert options["current"]["tts_engine"] == _info(TTS)["engine"]["name"]


def test_settings_tts_voice_current_is_effective_voice(options):
    info = _info(TTS)
    voices = options["tts_voices"][info["engine"]["name"]]
    # 엔진에 없는 음성 설정은 무시되고 엔진 기본 음성(첫 항목)으로 말한다
    # (melo 는 KR 하나)
    expected = (
        info["settings"]["voice"] if info["settings"]["voice"] in voices else voices[0]
    )
    assert options["current"]["tts_voice"] == expected


def test_settings_wake_word_threshold_is_service_value(options):
    assert (
        options["current"]["wake_word_threshold"]
        == _info(WAKE_WORD)["settings"]["threshold"]
    )


def test_settings_voices_follow_engine(options):
    voices = options["tts_voices"]
    assert voices["melo"] == ["KR"]
    assert voices["kokoro"] != voices["melo"]
    assert all(v.startswith("ko-KR-") for v in voices["edge_tts"])


def test_settings_llm_restart_no_false_success(api):
    response = api.post("/api/services/llm/restart", timeout=90)
    if response.status_code == 200:
        # 실제로 재생성을 시작한 환경에서만 200
        assert response.json()["status"] == "restarting"
    else:
        assert response.status_code == 503
        assert "docker compose up -d llm" in response.json()["message"]


# ===== Knowledge =====


def test_knowledge_chunk_count_matches_db(api):
    listed = {
        d["doc_id"]: d for d in api.get("/api/knowledge/documents").json()["documents"]
    }
    stored = {
        d["doc_id"]: d
        for d in httpx.get(f"{RAG}/documents", timeout=10).json()["documents"]
    }

    assert listed.keys() == stored.keys()
    for doc_id, doc in listed.items():
        assert doc["chunk_count"] == stored[doc_id]["chunk_count"], doc["filename"]


def test_knowledge_upload_search_delete_roundtrip(api):
    token = f"EV-LIVE-{uuid.uuid4().hex[:8]}"
    text = (
        f"{token} 는 페이지 점검용 임시 문서입니다. "
        "사내 회의실 예약은 매주 월요일 오전에 엽니다."
    )
    uploaded = api.post(
        "/api/knowledge/upload",
        files={"file": (f"{token}.txt", text.encode("utf-8"), "text/plain")},
    )
    assert uploaded.status_code == 200, uploaded.text
    doc_id = uploaded.json()["doc_id"]
    try:
        assert uploaded.json()["chunk_count"] >= 1
        found = api.post(
            "/api/knowledge/search", json={"query": f"{token} 회의실 예약", "top_k": 5}
        ).json()
        assert any(r["doc_id"] == doc_id for r in found["results"]), found
    finally:
        assert api.delete(f"/api/knowledge/documents/{doc_id}").status_code == 200
    assert doc_id not in {
        d["doc_id"] for d in api.get("/api/knowledge/documents").json()["documents"]
    }


# ===== Logs =====


def test_logs_default_query_is_mostly_not_debug(api):
    logs = api.get("/api/logs", params={"limit": 100, "min_level": "INFO"}).json()
    debug = sum(1 for log in logs if log["level"] == "DEBUG")
    assert not logs or debug / len(logs) < 0.5


def test_logs_level_filter(api):
    for level in ("DEBUG", "INFO", "WARNING", "ERROR"):
        logs = api.get("/api/logs", params={"limit": 50, "level": level}).json()
        assert all(log["level"] == level for log in logs), level


# ===== Dashboard · Chat · History 회귀 =====


def test_dashboard_init(api):
    data = api.get("/api/dashboard/init").json()
    assert data["services"]
    assert "system" in data


def test_history_messages(api):
    data = api.get("/api/history", params={"limit": 5}).json()
    assert isinstance(data["messages"], list)


def test_chat_streams_tokens(api):
    events = []
    with api.stream(
        "POST",
        "/api/chat/message",
        json={"message": "한 단어로만 답해 주세요: 안녕", "use_rag": False},
        timeout=120,
    ) as response:
        assert response.status_code == 200
        for line in response.iter_lines():
            if line.startswith("data:"):
                events.append(json.loads(line[5:]))
                if events[-1].get("type") in ("complete", "error"):
                    break

    assert any(e.get("type") == "token" and e.get("content") for e in events), events
    assert events[-1]["type"] == "complete", events
