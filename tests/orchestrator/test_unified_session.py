"""
음성 턴 ↔ 통합 세션 시나리오 (백엔드는 가짜, vLLM 은 OpenAI 형식 가짜)

- 음성 턴은 활성 세션에 user·assistant 두 메시지(source='voice')로 저장된다
- LLM 요청에는 활성 세션의 DB 히스토리(채팅에서 나눈 대화 포함)와 요약이 들어간다
- 오케스트레이터를 다시 만들어도(재시작) 같은 세션·이전 턴이 이어진다
- "새 대화" 뒤에는 새 세션에 저장된다
- 끼어들기로 잘린 답은 저장하지 않는다
- 백엔드가 죽어 있어도 음성 답(TTS)은 나온다
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from tests.orchestrator.message_helpers import roles_and_questions


class FakeBackend:
    """활성 세션과 메시지를 메모리에 두는 BackendClient 대역."""

    def __init__(self):
        self.active = "11111111-1111-1111-1111-111111111111"
        self.messages: dict = {}
        self.summaries: dict = {}
        self.current_session_id = None
        self.fail = False

    async def get_active_session(self) -> str:
        if self.fail:
            raise ConnectionError("backend down")
        self.current_session_id = self.active
        return self.active

    async def get_context(self, session_id: str) -> dict:
        return {
            "summary": self.summaries.get(session_id),
            "messages": [
                {"role": m["role"], "content": m["content"]}
                for m in self.messages.get(session_id, [])
            ],
        }

    async def save_message(
        self, role: str, content: str, source: str = "voice", **_
    ) -> dict:
        self.messages.setdefault(self.current_session_id, []).append(
            {"role": role, "content": content, "source": source}
        )
        return {"message_id": str(len(self.messages[self.current_session_id]))}


def _make(backend: FakeBackend, sent: list, reply: str = "네, 기억할게요."):
    from services.orchestrator.app.llm_client import LLMClient
    from services.orchestrator.app.orchestrator import Orchestrator

    llm = LLMClient(
        base_url="http://llm.test", model_name="test-model", system_prompt="음성 비서"
    )

    async def fake_stream_request(messages, **kwargs):
        sent.append([dict(m) for m in messages])
        yield {"choices": [{"delta": {"content": reply}, "finish_reason": None}]}
        yield {"choices": [{"delta": {}, "finish_reason": "stop"}]}

    llm._make_stream_request = fake_stream_request

    with patch.object(Orchestrator, "_setup_redis", return_value=AsyncMock()):
        orchestrator = Orchestrator(llm_client=llm, backend_client=backend)
    orchestrator.publish_tts_request = AsyncMock()
    return orchestrator


class TestVoiceTurnSaved:
    @pytest.mark.asyncio
    async def test_should_save_user_and_assistant_as_voice_when_turn_finishes(self):
        backend = FakeBackend()
        orchestrator = _make(backend, [])

        await orchestrator.process_user_input("내 이름은 민수야")

        assert backend.messages[backend.active] == [
            {"role": "user", "content": "내 이름은 민수야", "source": "voice"},
            {"role": "assistant", "content": "네, 기억할게요.", "source": "voice"},
        ]
        assert orchestrator._current_session_id == backend.active
        orchestrator.publish_tts_request.assert_awaited()

    @pytest.mark.asyncio
    async def test_should_not_save_answer_when_barge_in_cuts_it(self):
        from services.orchestrator.app.llm_client import LLMClient
        from services.orchestrator.app.orchestrator import Orchestrator

        backend = FakeBackend()
        llm = LLMClient(base_url="http://llm.test", model_name="test-model")
        started = asyncio.Event()

        async def slow_stream(messages, **kwargs):
            yield {
                "choices": [
                    {"delta": {"content": "첫 문장입니다."}, "finish_reason": None}
                ]
            }
            started.set()
            await asyncio.sleep(10)
            yield {
                "choices": [{"delta": {"content": "안 들림"}, "finish_reason": None}]
            }

        llm._make_stream_request = slow_stream
        with patch.object(Orchestrator, "_setup_redis", return_value=AsyncMock()):
            orchestrator = Orchestrator(llm_client=llm, backend_client=backend)
        orchestrator.publish_tts_request = AsyncMock()

        turn = asyncio.create_task(orchestrator.process_user_input("긴 얘기 해 줘"))
        await started.wait()
        await orchestrator.handle_barge_in()
        await turn

        assert [m["role"] for m in backend.messages[backend.active]] == ["user"]


class TestSharedHistory:
    @pytest.mark.asyncio
    async def test_should_send_session_history_from_chat_when_voice_asks(self):
        backend = FakeBackend()
        backend.messages[backend.active] = [
            {"role": "user", "content": "내 이름은 민수야", "source": "web"},
            {"role": "assistant", "content": "반가워요, 민수님.", "source": "web"},
        ]
        sent: list = []
        orchestrator = _make(backend, sent)

        await orchestrator.process_user_input("내 이름 뭐야?")

        assert roles_and_questions(sent[0]) == [
            ("system", "음성 비서"),
            ("user", "내 이름은 민수야"),
            ("assistant", "반가워요, 민수님."),
            ("user", "내 이름 뭐야?"),
        ]

    @pytest.mark.asyncio
    async def test_should_put_session_summary_in_system_message(self):
        backend = FakeBackend()
        backend.summaries[backend.active] = "사용자 이름은 민수다."
        sent: list = []
        orchestrator = _make(backend, sent)

        await orchestrator.process_user_input("안녕")

        assert sent[0][0]["role"] == "system"
        assert sent[0][0]["content"].endswith("사용자 이름은 민수다.")

    @pytest.mark.asyncio
    async def test_should_continue_same_session_after_restart(self):
        backend = FakeBackend()
        await _make(backend, []).process_user_input("첫 질문")

        sent: list = []
        restarted = _make(backend, sent)
        await restarted.process_user_input("두 번째 질문")

        assert restarted._current_session_id == backend.active
        assert ("user", "첫 질문") in [(m["role"], m["content"]) for m in sent[0]]

    @pytest.mark.asyncio
    async def test_should_save_to_new_session_after_new_conversation(self):
        backend = FakeBackend()
        orchestrator = _make(backend, [])
        await orchestrator.process_user_input("이전 세션 질문")
        old = backend.active

        backend.active = "22222222-2222-2222-2222-222222222222"
        sent: list = []
        orchestrator.llm_client._make_stream_request = _make(
            backend, sent
        ).llm_client._make_stream_request
        await orchestrator.process_user_input("새 세션 질문")

        assert [m["content"] for m in backend.messages[backend.active]] == [
            "새 세션 질문",
            "네, 기억할게요.",
        ]
        assert len(backend.messages[old]) == 2
        assert ("user", "이전 세션 질문") not in [
            (m["role"], m["content"]) for m in sent[0]
        ]


class TestBackendDown:
    @pytest.mark.asyncio
    async def test_should_still_speak_with_memory_context_when_backend_fails(self):
        backend = FakeBackend()
        backend.fail = True
        sent: list = []
        orchestrator = _make(backend, sent)

        await orchestrator.process_user_input("첫 질문")
        await orchestrator.process_user_input("두 번째 질문")

        orchestrator.publish_tts_request.assert_awaited()
        assert ("user", "첫 질문") in [(m["role"], m["content"]) for m in sent[1]]
        assert backend.messages == {}
