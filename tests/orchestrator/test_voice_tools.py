"""
음성 경로 도구 호출 시나리오
(백엔드·검색 제공자는 가짜, vLLM 은 OpenAI 형식 가짜 스트림)

- (a) web_search tool_calls → 가짜 검색 → role:tool → 두 번째 호출이 최종 답,
  도구 메시지 저장
- (b) 인터넷 도구가 꺼져 있으면 web_search/web_fetch 스키마를 보내지 않는다
- (c) `<tool_call>` 텍스트는 TTS 로 가지 않고, 도구 실행 전 짧은 안내를 말한다
- (g) 도구 5xx·잘못된 JSON 인자·없는 도구에도 답이 나오고 READY 로 돌아온다
- (h) 끼어들기 시 도구 결과·답이 TTS 로 가지 않는다
- (i) 파서가 없는 모델이면 도구를 보내지 않고,
  vLLM 이 도구 요청을 400 으로 거절하면 도구 없이 다시 요청한다
- 확인이 필요한 도구는 "실행할까요?" 다음 턴의 예/아니오로 실행 여부를 정한다
"""

import asyncio
import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from shared.tools import Tool, ToolRegistry, ToolResult, build_registry

MODEL = "Qwen/Qwen2.5-7B-Instruct-AWQ"
SESSION = "22222222-2222-2222-2222-222222222222"


class FakeBackend:
    def __init__(self):
        self.current_session_id = None
        self.saved: list = []

    async def get_active_session(self) -> str:
        self.current_session_id = SESSION
        return SESSION

    async def get_context(self, session_id: str) -> dict:
        return {"summary": None, "messages": []}

    async def save_message(self, role, content, source="voice", metadata=None, **_):
        self.saved.append(
            {"role": role, "content": content, "source": source, "metadata": metadata}
        )
        return {"message_id": str(len(self.saved))}


def text_chunk(text):
    return {"choices": [{"delta": {"content": text}, "finish_reason": None}]}


def call_chunk(*calls):
    return {
        "choices": [
            {
                "delta": {
                    "tool_calls": [
                        {
                            "index": i,
                            "id": f"call_{i}",
                            "type": "function",
                            "function": {"name": name, "arguments": args},
                        }
                        for i, (name, args) in enumerate(calls)
                    ]
                },
                "finish_reason": "tool_calls",
            }
        ]
    }


class FakeProvider:
    def __init__(self):
        self.queries = []

    async def search(self, query, count):
        self.queries.append(query)
        return [
            {
                "title": "기상청 날씨",
                "url": "https://www.weather.go.kr",
                "snippet": "서울 맑음 18도",
            }
        ]


def make(responses, model=MODEL, registry=None):
    """responses: 요청마다 돌려줄 청크 목록(또는 예외) 의 목록."""
    from services.orchestrator.app.llm_client import LLMClient
    from services.orchestrator.app.orchestrator import Orchestrator

    llm = LLMClient(
        base_url="http://llm.test", model_name=model, system_prompt="음성 비서"
    )
    llm.resolve_model = AsyncMock(return_value=model)
    requests = []
    script = list(responses)

    async def fake_stream_request(messages, **kwargs):
        requests.append(
            {
                "messages": [dict(m) for m in messages],
                "tools": kwargs.get("tools"),
                "tool_choice": kwargs.get("tool_choice"),
            }
        )
        item = script.pop(0)
        if callable(item):
            item = item(kwargs)
        for chunk in item:
            if isinstance(chunk, Exception):
                raise chunk
            if chunk == "wait":
                await asyncio.sleep(10)
                continue
            yield chunk

    llm._make_stream_request = fake_stream_request
    backend = FakeBackend()
    redis = AsyncMock()
    redis.get.return_value = None
    with patch.object(Orchestrator, "_setup_redis", return_value=redis):
        orchestrator = Orchestrator(llm_client=llm, backend_client=backend)
    spoken = []

    async def speak(text):
        spoken.append(text)

    orchestrator.publish_tts_request = speak
    if registry is not None:
        orchestrator._build_tools = AsyncMock(return_value=registry)
    return orchestrator, backend, requests, spoken


async def voice_turn(orchestrator, text):
    await orchestrator.handle_wake_word()
    await orchestrator.handle_stt_result(text)


class TestWebSearchRoundTrip:
    @pytest.mark.asyncio
    async def test_should_search_then_answer_and_save_tool_message(self):
        from services.orchestrator.app.state_machine import State

        provider = FakeProvider()
        registry = build_registry({"internet_enabled": True}, search_provider=provider)
        orchestrator, backend, requests, spoken = make(
            [
                [call_chunk(("web_search", '{"query": "서울 날씨"}'))],
                [text_chunk("서울은 맑고 18도예요.")],
            ],
            registry=registry,
        )

        await voice_turn(orchestrator, "서울 날씨 어때?")

        assert provider.queries == ["서울 날씨"]
        assert spoken == ["검색해 볼게요.", "서울은 맑고 18도예요."]
        second = requests[1]["messages"]
        assert second[-1]["role"] == "tool" and "서울 맑음" in second[-1]["content"]
        assert second[-2]["tool_calls"][0]["function"]["name"] == "web_search"
        assert [m["role"] for m in backend.saved] == ["user", "tool", "assistant"]
        tool_row = backend.saved[1]
        assert tool_row["source"] == "voice"
        assert tool_row["metadata"]["sources"][0] == {
            "tool": "web_search",
            "is_error": False,
        }
        assert (
            backend.saved[2]["metadata"]["sources"][0]["url"]
            == "https://www.weather.go.kr"
        )
        assert orchestrator.state_machine.current_state == State.READY


class TestInternetOff:
    @pytest.mark.asyncio
    async def test_should_send_only_local_tools_when_internet_off(self, monkeypatch):
        monkeypatch.delenv("INTERNET_TOOLS_ENABLED", raising=False)
        monkeypatch.setenv("SEARXNG_URL", "http://searxng:8080")
        orchestrator, _, requests, spoken = make([[text_chunk("안녕하세요.")]])

        with patch("httpx.AsyncClient.get") as http_get:
            await voice_turn(orchestrator, "안녕")

        names = [t["function"]["name"] for t in requests[0]["tools"]]
        assert names == ["get_time"]
        http_get.assert_not_called()
        assert spoken == ["안녕하세요."]


class TestToolTextNotSpoken:
    @pytest.mark.asyncio
    async def test_tool_call_text_never_reaches_tts(self):
        orchestrator, backend, _, spoken = make(
            [
                [
                    text_chunk("알려 드릴게요. <tool"),
                    text_chunk('_call>{"name": "get_time"}</tool_call>'),
                ]
            ]
        )

        await voice_turn(orchestrator, "몇 시야?")

        assert spoken == ["알려 드릴게요."]
        assert all("tool_call" not in s for s in spoken)

    @pytest.mark.asyncio
    async def test_get_time_runs_without_announcement(self):
        orchestrator, backend, requests, spoken = make(
            [[call_chunk(("get_time", "{}"))], [text_chunk("지금은 오후 세 시예요.")]]
        )

        await voice_turn(orchestrator, "몇 시야?")

        assert spoken == ["지금은 오후 세 시예요."]
        assert "년" in requests[1]["messages"][-1]["content"]


class TestToolFailures:
    @pytest.mark.asyncio
    async def test_should_answer_and_return_ready_when_tools_fail(self):
        from services.orchestrator.app.state_machine import State

        async def server_error(_):
            raise httpx.HTTPStatusError(
                "503",
                request=httpx.Request("GET", "http://x"),
                response=httpx.Response(503),
            )

        registry = ToolRegistry(
            [Tool("web_search", "검색", {"type": "object"}, server_error)]
        )
        orchestrator, backend, requests, spoken = make(
            [
                [
                    call_chunk(
                        ("web_search", '{"query": "a"}'),
                        ("get_time", '{"x":'),
                        ("nope", "{}"),
                    )
                ],
                [text_chunk("지금은 확인할 수 없어요.")],
            ],
            registry=registry,
        )

        await voice_turn(orchestrator, "검색해 줘")

        tool_messages = [m for m in requests[1]["messages"] if m["role"] == "tool"]
        assert len(tool_messages) == 3
        assert spoken[-1] == "지금은 확인할 수 없어요."
        assert orchestrator.state_machine.current_state == State.READY


class TestBargeIn:
    @pytest.mark.asyncio
    async def test_tool_result_not_spoken_after_barge_in(self):
        started = asyncio.Event()

        async def slow_search(_):
            started.set()
            await asyncio.sleep(10)
            return ToolResult("늦은 결과")

        registry = ToolRegistry(
            [
                Tool(
                    "web_search",
                    "검색",
                    {"type": "object"},
                    slow_search,
                    announce="검색해 볼게요.",
                )
            ]
        )
        orchestrator, backend, _, spoken = make(
            [
                [call_chunk(("web_search", '{"query": "a"}'))],
                [text_chunk("늦은 답이에요.")],
            ],
            registry=registry,
        )

        await orchestrator.handle_wake_word()
        turn = asyncio.create_task(orchestrator.handle_stt_result("검색해 줘"))
        await started.wait()
        await orchestrator.handle_barge_in()
        await turn

        assert spoken == ["검색해 볼게요."]
        assert [m["role"] for m in backend.saved] == ["user"]


class TestParserMissing:
    @pytest.mark.asyncio
    async def test_unknown_model_sends_no_tools(self, monkeypatch):
        monkeypatch.delenv("LLM_TOOL_PARSER", raising=False)
        orchestrator, _, requests, spoken = make(
            [[text_chunk("네.")]], model="google/gemma-2-9b-it"
        )

        await voice_turn(orchestrator, "안녕")

        assert requests[0]["tools"] is None
        assert spoken == ["네."]

    @pytest.mark.asyncio
    async def test_should_retry_without_tools_when_vllm_rejects_them(self):
        def reject_tools(kwargs):
            if kwargs.get("tools"):
                response = httpx.Response(
                    400, request=httpx.Request("POST", "http://llm.test")
                )
                return [
                    httpx.HTTPStatusError(
                        "400", request=response.request, response=response
                    )
                ]
            return [text_chunk("도구 없이 답해요.")]

        orchestrator, _, requests, spoken = make(
            [reject_tools, reject_tools, reject_tools]
        )

        await voice_turn(orchestrator, "안녕")
        await voice_turn(orchestrator, "또 안녕")

        assert spoken == ["도구 없이 답해요.", "도구 없이 답해요."]
        assert [r["tools"] is not None for r in requests] == [True, False, False]
        assert orchestrator.llm_client.tools_supported is False


class TestVoiceConfirmation:
    def _registry(self, ran):
        async def restart(args):
            ran.append(args)
            return ToolResult(f"{args['service']} 재시작 완료")

        return ToolRegistry(
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

    @pytest.mark.asyncio
    async def test_should_ask_then_run_after_yes(self):
        ran = []
        orchestrator, backend, requests, spoken = make(
            [
                [call_chunk(("ironwall__restart", '{"service": "stt"}'))],
                [text_chunk("STT 서비스를 재시작할까요?")],
                [text_chunk("재시작했어요.")],
            ],
            registry=self._registry(ran),
        )

        await voice_turn(orchestrator, "STT 재시작해 줘")
        assert ran == []
        assert spoken == ["STT 서비스를 재시작할까요?"]

        await voice_turn(orchestrator, "네")

        assert ran == [{"service": "stt"}]
        assert spoken[-1] == "재시작했어요."
        assert "stt 재시작 완료" in requests[2]["messages"][-1]["content"]
        assert requests[2]["tools"] is None

    @pytest.mark.asyncio
    async def test_should_not_run_after_no(self):
        from services.orchestrator.app.orchestrator import CANCELLED_REPLY

        ran = []
        orchestrator, backend, requests, spoken = make(
            [
                [call_chunk(("ironwall__restart", '{"service": "stt"}'))],
                [text_chunk("재시작할까요?")],
            ],
            registry=self._registry(ran),
        )

        await voice_turn(orchestrator, "STT 재시작해 줘")
        await voice_turn(orchestrator, "아니 하지 마")

        assert ran == []
        assert spoken[-1] == CANCELLED_REPLY
        assert len(requests) == 2
        assert (
            json.dumps(backend.saved[-1]["content"], ensure_ascii=False).find(
                CANCELLED_REPLY
            )
            >= 0
        )


class TestRequiredTool:
    @pytest.mark.asyncio
    async def test_news_question_forces_web_search_on_first_request(self):
        # 같은 질문에 도구 없이 답한 기록이 있으면 auto 에서는 뉴스를 지어냈다(실측)
        provider = FakeProvider()
        registry = build_registry({"internet_enabled": True}, search_provider=provider)
        orchestrator, _, requests, spoken = make(
            [
                [call_chunk(("web_search", '{"query": "오늘 주요 뉴스"}'))],
                [text_chunk("오늘 주요 뉴스는 이렇습니다.")],
            ],
            registry=registry,
        )

        await voice_turn(orchestrator, "인터넷에서 오늘 주요 뉴스 찾아 줘")

        assert provider.queries == ["오늘 주요 뉴스"]
        assert requests[0]["tool_choice"] == {
            "type": "function",
            "function": {"name": "web_search"},
        }
        assert requests[1]["tool_choice"] == "auto"


class TestCannotDoWithoutTool:
    @pytest.mark.asyncio
    async def test_open_request_without_tool_is_admitted_without_llm(self):
        # 실측: 도구 없이 "크롬을 열었습니다" 라고 말했다
        from shared.tools import CANNOT_DO_REPLY

        orchestrator, _, requests, spoken = make(
            [[text_chunk("크롬을 열었습니다.")]],
            registry=build_registry({"internet_enabled": False}),
        )

        await voice_turn(orchestrator, "크롬 켜줘.")

        assert requests == []
        assert " ".join(spoken) == CANNOT_DO_REPLY
