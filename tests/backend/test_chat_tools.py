"""
채팅 경로 도구 호출 시나리오 (Postgres·Redis 는 가짜, vLLM 은 OpenAI 형식 가짜)

- (a) web_search tool_calls → 가짜 검색 → role:tool → 두 번째 호출이 최종 답,
  도구 메시지(role='tool')가 DB 에 저장되고 다음 프롬프트 컨텍스트에는 들어가지 않는다
- 채팅 이벤트: tool_call · tool_result("검색함"·출처), complete 에 웹 출처
- 확인이 필요한 도구: tool_confirm 이벤트 → POST /api/chat/confirm 승인 뒤에만 실행
- (i) vLLM 이 도구 요청을 400 으로 거절하면 도구 없이 다시 요청한다
- 음성 파이프라인이 role='tool' 메시지와 출처를 저장할 수 있다
- 도구 설정 API: 인터넷 도구 토글
"""

import asyncio
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from services.backend.app.services import conversation
from shared.tools import Tool, ToolRegistry, ToolResult, build_registry
from tests.backend.test_unified_conversation import (
    FakeDB,
    FakeMessageRepository,
    FakeSessionRepository,
    _sse,
    _vllm,
)

MODEL = "Qwen/Qwen2.5-7B-Instruct-AWQ"


@pytest.fixture
def db(monkeypatch):
    """가짜 Postgres(세션·메시지) — 발행·요약 예약은 기록만 한다."""
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
    monkeypatch.setattr(conversation, "schedule_summary", lambda *a: None)
    return fake


def tool_call_chunk(name, arguments, call_id="call_1"):
    return {
        "choices": [
            {
                "delta": {
                    "tool_calls": [
                        {
                            "index": 0,
                            "id": call_id,
                            "type": "function",
                            "function": {"name": name, "arguments": arguments},
                        }
                    ]
                },
                "finish_reason": "tool_calls",
            }
        ]
    }


def text_chunk(text):
    return {"choices": [{"delta": {"content": text}, "finish_reason": None}]}


class FakeProvider:
    async def search(self, query, count):
        return [
            {
                "title": "기상청",
                "url": "https://www.weather.go.kr",
                "snippet": "서울 맑음",
            }
        ]


def scripted_vllm(*responses):
    """요청마다 다음 응답 청크 목록을 돌려주는 SimpleLLMClient 와 요청 기록."""
    requests = []
    script = list(responses)

    def handler(request):
        body = json.loads(request.content)
        requests.append(body)
        return _sse(script.pop(0))

    client = _vllm(handler)
    client.model_name = MODEL
    return client, requests


async def run_chat(service, session_id, message):
    return [
        e async for e in service.process_message(session_id, message, use_rag=False)
    ]


class TestChatToolRoundTrip:
    @pytest.mark.asyncio
    async def test_should_search_answer_and_store_tool_message(self, db):
        from services.backend.app.services.chat_service import ChatService

        llm, requests = scripted_vllm(
            [tool_call_chunk("web_search", '{"query": "서울 날씨"}')],
            [text_chunk("서울은 맑아요.")],
        )

        async def tools():
            return build_registry(
                {"internet_enabled": True}, search_provider=FakeProvider()
            )

        service = ChatService(llm_client=llm, tool_provider=tools)
        session_id = await conversation.get_active_session_id()

        events = await run_chat(service, session_id, "서울 날씨 어때?")

        types = [e["type"] for e in events]
        assert types[:2] == ["tool_call", "tool_result"]
        assert events[1]["tool"] == "web_search"
        assert (
            events[-1]["type"] == "complete"
            and events[-1]["content"] == "서울은 맑아요."
        )
        assert events[-1]["sources"] == [
            {"title": "기상청", "url": "https://www.weather.go.kr"}
        ]
        assert sorted(t["function"]["name"] for t in requests[0]["tools"]) == [
            "get_time",
            "web_fetch",
            "web_search",
        ]
        assert requests[1]["messages"][-1]["role"] == "tool"

        rows = [m for m in db.messages if str(m["session_id"]) == session_id]
        assert [m["role"] for m in rows] == ["user", "tool", "assistant"]
        assert rows[1]["rag_sources"][0] == {"tool": "web_search", "is_error": False}
        context = await conversation.get_context(session_id)
        assert [m["role"] for m in context["messages"]] == ["user", "assistant"]

    @pytest.mark.asyncio
    async def test_should_retry_without_tools_when_vllm_rejects_them(self, db):
        import httpx

        from services.backend.app.services.chat_service import ChatService

        requests = []

        def handler(request):
            body = json.loads(request.content)
            requests.append(body)
            if "tools" in body:
                return httpx.Response(
                    400,
                    text='{"error": "requires --enable-auto-tool-choice"}',
                )
            return _sse([text_chunk("도구 없이 답해요.")])

        llm = _vllm(handler)
        llm.model_name = MODEL

        async def tools():
            return build_registry({"internet_enabled": False})

        service = ChatService(llm_client=llm, tool_provider=tools)
        session_id = await conversation.get_active_session_id()

        events = await run_chat(service, session_id, "안녕")

        assert events[-1]["content"] == "도구 없이 답해요."
        assert ["tools" in r for r in requests] == [True, False]
        assert llm.tools_supported is False


class TestChatConfirmation:
    def _service(self, ran, *responses):
        from services.backend.app.services.chat_service import ChatService

        async def restart(args):
            ran.append(args)
            return ToolResult("재시작 완료")

        registry = ToolRegistry(
            [
                Tool(
                    "ironwall__restart",
                    "재시작",
                    {"type": "object"},
                    restart,
                    needs_confirm=True,
                )
            ]
        )
        llm, _ = scripted_vllm(*responses)

        async def tools():
            return registry

        return ChatService(llm_client=llm, tool_provider=tools)

    @pytest.mark.asyncio
    async def test_should_run_only_after_user_approves(self, db):
        from services.backend.app.routes import chat

        ran = []
        service = self._service(
            ran,
            [
                tool_call_chunk(
                    "ironwall__restart", '{"service": "stt"}', "call_confirm_1"
                )
            ],
            [text_chunk("재시작했어요.")],
        )
        session_id = await conversation.get_active_session_id()
        app = FastAPI()
        app.include_router(chat.router)
        client = TestClient(app)

        events = []
        async for event in service.process_message(
            session_id, "stt 재시작", use_rag=False
        ):
            events.append(event)
            if event["type"] == "tool_confirm":
                assert ran == []
                assert (
                    await asyncio.to_thread(
                        lambda: (
                            client.post(
                                "/api/chat/confirm",
                                json={"confirm_id": event["id"], "approved": True},
                            ).status_code
                        )
                    )
                    == 200
                )

        assert ran == [{"service": "stt"}]
        assert events[-1]["content"] == "재시작했어요."

    @pytest.mark.asyncio
    async def test_should_not_run_when_user_rejects(self, db):
        from services.backend.app.services.chat_service import resolve_confirm

        ran = []
        service = self._service(
            ran,
            [
                tool_call_chunk(
                    "ironwall__restart", '{"service": "stt"}', "call_confirm_2"
                )
            ],
            [text_chunk("실행하지 않았어요.")],
        )
        session_id = await conversation.get_active_session_id()

        async for event in service.process_message(
            session_id, "stt 재시작", use_rag=False
        ):
            if event["type"] == "tool_confirm":
                assert resolve_confirm(event["id"], False)

        assert ran == []

    def test_confirm_endpoint_returns_404_without_pending(self):
        from services.backend.app.routes import chat

        app = FastAPI()
        app.include_router(chat.router)

        response = TestClient(app).post(
            "/api/chat/confirm", json={"confirm_id": "none", "approved": True}
        )

        assert response.status_code == 404


class TestPipelineToolMessage:
    def test_should_store_voice_tool_message_with_sources(self, db):
        from services.backend.app.routes import sessions

        app = FastAPI()
        app.include_router(sessions.router)
        client = TestClient(app)

        response = client.post(
            "/api/sessions/pipeline/messages",
            json={
                "role": "tool",
                "content": "1. 기상청",
                "source": "voice",
                "metadata": {
                    "sources": [
                        {"tool": "web_search", "is_error": False},
                        {"title": "기상청", "url": "https://www.weather.go.kr"},
                    ]
                },
            },
        )

        assert response.status_code == 200
        row = db.messages[-1]
        assert row["role"] == "tool" and row["source"] == "voice"
        assert row["rag_sources"][1]["url"] == "https://www.weather.go.kr"


class FakeRedis:
    def __init__(self):
        self.values = {}

    async def get(self, key):
        return self.values.get(key)

    async def set(self, key, value):
        self.values[key] = value


class TestToolSettingsApi:
    def test_should_toggle_internet_tools(self, monkeypatch):
        from services.backend.app.routes import settings

        monkeypatch.delenv("INTERNET_TOOLS_ENABLED", raising=False)
        monkeypatch.setenv("SEARXNG_URL", "http://searxng:8080")
        redis = FakeRedis()
        monkeypatch.setattr(conversation, "_get_redis", lambda: redis)
        app = FastAPI()
        app.include_router(settings.router)
        client = TestClient(app)

        before = client.get("/api/settings/tools").json()
        after = client.put(
            "/api/settings/tools",
            json={"internet_enabled": True, "search_provider": "searxng"},
        ).json()

        assert before["internet_enabled"] is False and before["tools"] == ["get_time"]
        assert after["internet_enabled"] is True
        # 인터넷을 켜면 날씨(get_weather, 기본 켜짐)도 함께 노출된다
        assert after["tools"] == ["get_time", "get_weather", "web_fetch", "web_search"]
        assert client.get("/api/settings/tools").json()["internet_enabled"] is True


def _weather_tool(asked):
    async def weather(args):
        asked.append(args)
        return ToolResult("부산 현재 날씨: 약한 비")

    return Tool("get_weather", "날씨", {"type": "object"}, weather)


class TestRequiredTool:
    @pytest.mark.asyncio
    async def test_weather_question_forces_weather_tool_on_first_request(self, db):
        # 같은 질문에 도구 없이 답한 기록이 있으면 auto 에서는 옛 답을 베꼈다(실측)
        from services.backend.app.services.chat_service import ChatService

        llm, requests = scripted_vllm(
            [tool_call_chunk("get_weather", '{"location": "부산"}')],
            [text_chunk("부산은 지금 약한 비가 와요.")],
        )
        asked = []

        async def tools():
            return ToolRegistry([_weather_tool(asked)])

        service = ChatService(llm_client=llm, tool_provider=tools)
        session_id = await conversation.get_active_session_id()

        events = await run_chat(service, session_id, "부산은 지금 비 와?")

        assert asked == [{"location": "부산"}]
        assert requests[0]["tool_choice"] == {
            "type": "function",
            "function": {"name": "get_weather"},
        }
        assert requests[1]["tool_choice"] == "auto"
        assert events[-1]["content"] == "부산은 지금 약한 비가 와요."
