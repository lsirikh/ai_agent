"""
통합 대화(음성 + 텍스트 한 세션) 백엔드 시나리오

Postgres 는 가짜 저장소, Redis 는 가짜 발행/구독,
vLLM 은 OpenAI 형식 가짜(httpx.MockTransport).

1. 음성 턴 저장 → 활성 세션에 source='voice' 두 행 + 채팅 스트림 message 이벤트
2. 음성 "내 이름은 민수야" → 텍스트 "내 이름 뭐야?" 의 LLM 요청에 음성 턴이 들어감
3. 재시작 후에도 같은 활성 세션
4. 새 세션 뒤 저장은 새 ID, 이전 메시지는 그대로
5. 비 UUID·None session_id 가 흩어지지 않음, /api/chat/stream init 에 기존 히스토리
6. 예산: 긴 메시지 200개에도 프롬프트 + max_tokens ≤ max_model_len
7. 요약: 임계값을 넘으면 요약 행, 다음 컨텍스트는 요약 + 덮이지 않은 턴.
   실패하면 잘라내기
9. vLLM 400·500 → 빈 답 저장 없음, 사용자에게 오류 이벤트
"""

import itertools
import json
import uuid
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from services.backend.app.services import conversation
from shared.context_builder import prompt_tokens

_clock = itertools.count()


class FakeDB:
    def __init__(self):
        self.sessions: dict = {}
        self.messages: list = []
        self.summaries: list = []
        self.active = None
        self.published: list = []


class FakeSessionRepository:
    def __init__(self, db: FakeDB):
        self.db = db

    async def create(self, session_type="web", source="web", **_):
        sid = uuid.uuid4()
        self.db.sessions[sid] = {
            "id": sid,
            "session_type": session_type,
            "source": source,
            "created_at": datetime.now(timezone.utc),
        }
        return sid

    async def get_by_id(self, session_id):
        return self.db.sessions.get(session_id)

    async def get_active(self):
        return self.db.active if self.db.active in self.db.sessions else None

    async def set_active(self, session_id):
        self.db.active = session_id

    async def get_summary(self, session_id):
        rows = [s for s in self.db.summaries if s["session_id"] == session_id]
        return rows[-1] if rows else None

    async def add_summary(
        self, session_id, summary, covered_until_message_id, token_count
    ):
        self.db.summaries.append(
            {
                "session_id": session_id,
                "summary": summary,
                "covered_until_message_id": covered_until_message_id,
                "token_count": token_count,
            }
        )


class FakeMessageRepository:
    def __init__(self, db: FakeDB):
        self.db = db

    async def create(
        self,
        session_id,
        role,
        content,
        rag_context=None,
        rag_sources=None,
        source="web",
    ):
        if session_id not in self.db.sessions:
            raise ValueError("FK violation: unknown session")
        mid = uuid.uuid4()
        self.db.messages.append(
            {
                "id": mid,
                "session_id": session_id,
                "role": role,
                "content": content,
                "rag_sources": rag_sources or [],
                "source": source,
                "created_at": datetime(2026, 10, 17, tzinfo=timezone.utc)
                + timedelta(seconds=next(_clock)),
            }
        )
        return mid

    async def get_by_session(self, session_id, include_system=True):
        return [
            m
            for m in self.db.messages
            if m["session_id"] == session_id
            and (include_system or m["role"] != "system")
        ]


class FakePubSub:
    def __init__(self, db: FakeDB):
        self.db = db
        self.read = 0

    async def subscribe(self, channel):
        self.channel = channel

    async def get_message(self, ignore_subscribe_messages=True, timeout=1.0):
        if self.read < len(self.db.published):
            self.read += 1
            data = json.dumps(self.db.published[self.read - 1], ensure_ascii=False)
            return {"type": "message", "data": data}
        return None

    async def unsubscribe(self):
        pass

    async def aclose(self):
        pass


@pytest.fixture
def db(monkeypatch):
    fake = FakeDB()

    async def publish(message):
        fake.published.append(message)

    monkeypatch.setattr(
        conversation, "SessionRepository", lambda: FakeSessionRepository(fake)
    )
    monkeypatch.setattr(
        conversation, "MessageRepository", lambda: FakeMessageRepository(fake)
    )
    monkeypatch.setattr(conversation, "is_available", lambda: True)
    monkeypatch.setattr(conversation, "publish_message", publish)
    monkeypatch.setattr(conversation, "subscribe_messages", lambda: FakePubSub(fake))
    monkeypatch.setattr(
        conversation,
        "schedule_summary",
        lambda *a: fake.published.append({"scheduled_summary": a[0]}),
    )
    return fake


def _question(content: str) -> str:
    """'지금 시각: …\n\n질문' 에서 질문만."""
    if content.startswith("지금 시각:"):
        return content.split("\n\n", 1)[1]
    return content


def _sessions_client() -> TestClient:
    from services.backend.app.routes import sessions

    app = FastAPI()
    app.include_router(sessions.router)
    return TestClient(app)


def _vllm(handler) -> "object":
    """httpx.MockTransport 로 OpenAI 형식 vLLM 을 흉내 내는 SimpleLLMClient."""
    from services.backend.app.services.llm_client import SimpleLLMClient

    client = SimpleLLMClient(base_url="http://vllm.test", model_name="test-model")
    client._http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return client


def _sse(chunks: list) -> httpx.Response:
    body = "".join(f"data: {json.dumps(c, ensure_ascii=False)}\n\n" for c in chunks)
    return httpx.Response(200, text=body + "data: [DONE]\n\n")


class TestActiveSession:
    @pytest.mark.asyncio
    async def test_should_keep_same_active_session_after_restart(self, db):
        first = await conversation.get_active_session_id()
        # 재시작: 모듈 상태가 아닌 DB(settings)에서 다시 읽는다
        again = await conversation.get_active_session_id()

        assert first == again
        assert db.sessions[uuid.UUID(first)]["session_type"] == "unified"

    @pytest.mark.asyncio
    async def test_should_switch_to_new_session_and_keep_old_messages(self, db):
        old = await conversation.get_active_session_id()
        await conversation.save_message(old, "user", "이전 질문", source="voice")

        client = _sessions_client()
        new = client.post("/api/sessions").json()["session_id"]

        assert new != old
        assert client.get("/api/sessions/active").json()["session_id"] == new
        client.post(
            "/api/sessions/pipeline/messages",
            json={"role": "user", "content": "새 질문", "source": "voice"},
        )
        assert [
            m["content"]
            for m in client.get(f"/api/sessions/{new}/messages").json()["messages"]
        ] == ["새 질문"]
        assert [
            m["content"]
            for m in client.get(f"/api/sessions/{old}/messages").json()["messages"]
        ] == ["이전 질문"]

    @pytest.mark.asyncio
    async def test_should_use_active_session_when_id_is_none_non_uuid_or_unknown(
        self, db
    ):
        active = await conversation.get_active_session_id()

        for given in (None, "", "session-1a2b3c4d5e6f", str(uuid.uuid4())):
            assert await conversation.resolve_session_id(given) == active

    def test_should_map_same_non_uuid_to_same_session_in_persistent_history(self):
        from services.backend.app.services.persistent_history import to_session_uuid

        assert to_session_uuid("session-abc") == to_session_uuid("session-abc")
        assert to_session_uuid("session-abc") != to_session_uuid("session-xyz")
        valid = str(uuid.uuid4())
        assert str(to_session_uuid(valid)) == valid


class TestVoiceTurnToChat:
    def test_should_store_voice_turn_and_publish_two_messages(self, db):
        client = _sessions_client()

        for role, content in (("user", "내 이름은 민수야"), ("assistant", "반가워요")):
            response = client.post(
                "/api/sessions/pipeline/messages",
                json={
                    "session_id": None,
                    "role": role,
                    "content": content,
                    "source": "voice",
                },
            )
            assert response.status_code == 200

        active = db.active
        rows = [m for m in db.messages if m["session_id"] == active]
        assert [(m["role"], m["source"]) for m in rows] == [
            ("user", "voice"),
            ("assistant", "voice"),
        ]
        events = [p for p in db.published if "role" in p]
        assert [(e["role"], e["source"], e["session_id"]) for e in events] == [
            ("user", "voice", str(active)),
            ("assistant", "voice", str(active)),
        ]
        # 답이 저장되면 요약 검사를 예약한다
        assert {"scheduled_summary": str(active)} in db.published

    @pytest.mark.asyncio
    async def test_should_send_history_in_init_and_forward_session_messages(self, db):
        from services.backend.app.routes.chat import stream_chat

        active = await conversation.get_active_session_id()
        await conversation.save_message(active, "user", "이전 질문")
        db.published.clear()
        db.published.append(
            {
                "session_id": str(uuid.uuid4()),
                "role": "user",
                "content": "다른 세션",
                "source": "voice",
            }
        )
        db.published.append(
            {
                "session_id": active,
                "role": "user",
                "content": "음성 질문",
                "source": "voice",
            }
        )

        response = await stream_chat(session_id=None)
        chunks = response.body_iterator
        init = await chunks.__anext__()
        forwarded = await chunks.__anext__()
        await chunks.aclose()

        assert init.startswith("event: init")
        init_data = json.loads(init.split("data: ", 1)[1])
        assert init_data["session_id"] == active
        assert [m["content"] for m in init_data["messages"]] == ["이전 질문"]
        assert forwarded.startswith("event: message")
        assert "음성 질문" in forwarded and "다른 세션" not in forwarded


class TestSharedContext:
    @pytest.mark.asyncio
    async def test_should_include_voice_turn_when_text_asks_follow_up(self, db):
        from services.backend.app.services.chat_service import ChatService

        active = await conversation.get_active_session_id()
        await conversation.save_message(
            active, "user", "내 이름은 민수야", source="voice"
        )
        await conversation.save_message(
            active, "assistant", "반가워요, 민수님.", source="voice"
        )
        captured = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured.append(json.loads(request.content))
            return _sse([{"choices": [{"delta": {"content": "민수님이에요."}}]}])

        service = ChatService(llm_client=_vllm(handler))
        events = [
            e
            async for e in service.process_message(
                active, "내 이름 뭐야?", use_rag=False
            )
        ]

        assert events[-1]["content"] == "민수님이에요."
        # 이번 질문 앞에는 매 턴 '지금 시각' 근거가 붙는다 — 질문만 비교한다
        sent = [(m["role"], _question(m["content"])) for m in captured[0]["messages"]]
        assert sent[1:] == [
            ("user", "내 이름은 민수야"),
            ("assistant", "반가워요, 민수님."),
            ("user", "내 이름 뭐야?"),
        ]
        assert [(m["source"], m["content"]) for m in db.messages[-2:]] == [
            ("web", "내 이름 뭐야?"),
            ("web", "민수님이에요."),
        ]

    @pytest.mark.asyncio
    async def test_should_fit_model_len_with_200_long_messages(self, db):
        from services.backend.app.services.chat_service import ChatService

        active = await conversation.get_active_session_id()
        for i in range(200):
            await conversation.save_message(
                active, "user" if i % 2 == 0 else "assistant", f"{i} " + "가" * 500
            )
        captured = []

        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            if request.url.path == "/tokenize":
                # 실제 토크나이저 대신 추정치를 그대로 센다
                return httpx.Response(
                    200,
                    json={
                        "count": prompt_tokens(body["messages"]),
                        "max_model_len": 4096,
                    },
                )
            captured.append(body)
            return _sse([{"choices": [{"delta": {"content": "답"}}]}])

        llm = _vllm(handler)
        llm.max_model_len = 4096
        events = [
            e
            async for e in ChatService(llm_client=llm).process_message(
                active, "마지막 질문", use_rag=False
            )
        ]

        assert events[-1]["type"] == "complete"
        payload = captured[0]
        assert prompt_tokens(payload["messages"]) + payload["max_tokens"] <= 4096
        last = payload["messages"][-1]
        assert last["role"] == "user" and _question(last["content"]) == "마지막 질문"
        assert payload["messages"][0]["role"] == "system"


class TestRollingSummary:
    @pytest.mark.asyncio
    async def test_should_fold_old_turns_into_summary_over_threshold(self, db):
        active = await conversation.get_active_session_id()
        for i in range(200):
            await conversation.save_message(
                active, "user" if i % 2 == 0 else "assistant", f"{i} " + "가" * 300
            )

        class SummaryLLM:
            async def complete(self, messages, max_tokens, temperature):
                assert temperature <= 0.3
                assert "0 가" in messages[1]["content"]
                return "사용자는 긴 대화를 나눴다."

        assert await conversation.maybe_summarize(active, SummaryLLM()) is True

        context = await conversation.get_context(active)
        assert context["summary"] == "사용자는 긴 대화를 나눴다."
        covered = db.summaries[-1]["covered_until_message_id"]
        contents = [m["content"] for m in context["messages"]]
        assert not any(c.startswith("0 ") for c in contents)
        assert contents[-1].startswith("199 ")
        assert len(contents) < 200
        # 원문은 지우지 않는다
        assert any(m["id"] == covered for m in db.messages)
        assert len(db.messages) == 200

    @pytest.mark.asyncio
    async def test_should_fall_back_to_truncation_when_summary_fails(self, db):
        active = await conversation.get_active_session_id()
        for i in range(200):
            await conversation.save_message(active, "user", "가" * 300)

        class BrokenLLM:
            async def complete(self, *args, **kwargs):
                raise RuntimeError("LLM down")

        assert await conversation.maybe_summarize(active, BrokenLLM()) is False
        assert db.summaries == []
        assert len((await conversation.get_context(active))["messages"]) == 200

    @pytest.mark.asyncio
    async def test_should_not_summarize_short_conversation(self, db):
        active = await conversation.get_active_session_id()
        await conversation.save_message(active, "user", "안녕")

        class NeverCalled:
            async def complete(self, *args, **kwargs):
                raise AssertionError("요약하지 않아야 한다")

        assert await conversation.maybe_summarize(active, NeverCalled()) is False


class TestLLMErrors:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("status", [400, 500])
    async def test_should_not_save_empty_answer_when_vllm_fails(self, db, status):
        from services.backend.app.services.chat_service import ChatService
        from services.backend.app.services.llm_client import LLMError

        active = await conversation.get_active_session_id()
        service = ChatService(
            llm_client=_vllm(
                lambda request: httpx.Response(status, text="max_model_len exceeded")
            )
        )

        with pytest.raises(LLMError, match=str(status)):
            [e async for e in service.process_message(active, "질문", use_rag=False)]

        assert db.messages == []

    @pytest.mark.parametrize("status", [400, 500])
    def test_should_tell_user_about_llm_error(self, db, monkeypatch, status):
        from services.backend.app.routes import chat
        from services.backend.app.services.chat_service import ChatService

        service = ChatService(llm_client=_vllm(lambda request: httpx.Response(status)))

        async def get_service():
            return service

        monkeypatch.setattr(chat, "get_chat_service", get_service)
        app = FastAPI()
        app.include_router(chat.router)

        body = (
            TestClient(app)
            .post("/api/chat/message", json={"message": "질문", "use_rag": False})
            .text
        )

        events = [
            json.loads(line[6:])
            for line in body.splitlines()
            if line.startswith("data: ")
        ]
        assert events[-1]["type"] == "error"
        assert str(status) in events[-1]["content"]
        assert db.messages == []
