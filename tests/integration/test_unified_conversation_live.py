"""
[live] 통합 대화 — 실제 스택(docker compose dev) 대상.
EDGEVOICE_LIVE=1 일 때만 돈다.

    EDGEVOICE_LIVE=1 python -m pytest \
        tests/integration/test_unified_conversation_live.py

주의: 시험마다 "새 대화"(POST /api/sessions)를 만들어 활성 세션이 바뀐다.
"""

import asyncio
import json
import os

import httpx
import pytest

BACKEND = os.getenv("EDGEVOICE_BACKEND_URL", "http://localhost:11000")
REDIS_HOST = os.getenv("EDGEVOICE_REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("EDGEVOICE_REDIS_PORT", "6379"))

pytestmark = pytest.mark.skipif(
    os.getenv("EDGEVOICE_LIVE") != "1", reason="live: EDGEVOICE_LIVE=1 일 때만 실행"
)


async def _new_session(client: httpx.AsyncClient) -> str:
    response = await client.post(f"{BACKEND}/api/sessions")
    response.raise_for_status()
    return response.json()["session_id"]


async def _collect_messages(client, session_id: str, events: list) -> None:
    url = f"{BACKEND}/api/chat/stream?session_id={session_id}"
    async with client.stream("GET", url) as response:
        event = None
        async for line in response.aiter_lines():
            if line.startswith("event:"):
                event = line[6:].strip()
            elif line.startswith("data:") and event == "message":
                events.append(json.loads(line[5:]))


@pytest.mark.asyncio
async def test_live_voice_turn_reaches_chat_stream_and_db():
    import redis.asyncio as redis

    async with httpx.AsyncClient(timeout=None) as client:
        session_id = await _new_session(client)
        events: list = []
        listener = asyncio.create_task(_collect_messages(client, session_id, events))
        await asyncio.sleep(1)

        r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
        await r.publish("edgevoice:wake_word:detected", "{}")
        await asyncio.sleep(1)
        await r.publish(
            "edgevoice:stt:result",
            json.dumps({"text": "라이브 시험이야. 짧게 답해 줘."}),
        )
        await r.aclose()

        for _ in range(180):
            if len(events) >= 2:
                break
            await asyncio.sleep(0.5)
        listener.cancel()

        assert [(e["role"], e["source"]) for e in events[:2]] == [
            ("user", "voice"),
            ("assistant", "voice"),
        ]
        rows = (
            await client.get(f"{BACKEND}/api/sessions/{session_id}/messages")
        ).json()["messages"]
        assert [(m["role"], m["source"]) for m in rows] == [
            ("user", "voice"),
            ("assistant", "voice"),
        ]


@pytest.mark.asyncio
async def test_live_200_long_messages_do_not_cause_vllm_400():
    async with httpx.AsyncClient(timeout=None) as client:
        session_id = await _new_session(client)
        for i in range(200):
            role = "user" if i % 2 == 0 else "assistant"
            response = await client.post(
                f"{BACKEND}/api/history/messages",
                json={"session_id": session_id, "role": role, "content": "가" * 400},
            )
            response.raise_for_status()

        response = await client.post(
            f"{BACKEND}/api/chat/message",
            json={
                "session_id": session_id,
                "message": "한 문장으로 답해 줘.",
                "use_rag": False,
            },
        )
        events = [
            json.loads(line[6:])
            for line in response.text.splitlines()
            if line.startswith("data: ")
        ]

        assert not [e for e in events if e["type"] == "error"], events
        assert events[-1]["type"] == "complete"
        assert events[-1]["content"].strip()
