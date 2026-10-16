"""
음성 경로 지식 베이스(RAG) 테스트

텍스트 채팅만 RAG 를 쓰고 음성 턴은 RAG 를 부르지 않아, 지식 베이스에 올린 문서를
음성으로 물으면 모델이 지어낸 답을 했다. 음성 턴도 검색하고, 점수가 기준(RAG_MIN_SCORE)
이상인 근거만 이번 질문에 붙인다(인사말에 무관한 문서가 붙지 않게).
"""

from unittest.mock import AsyncMock, patch

import pytest


def _orchestrator(results: list[dict], sent: list):
    from services.orchestrator.app.orchestrator import Orchestrator

    with patch.object(Orchestrator, "_setup_redis", return_value=AsyncMock()):
        orchestrator = Orchestrator(redis_client=AsyncMock())

    async def fake_stream_request(messages, **kwargs):
        sent.append([dict(m) for m in messages])
        yield {"choices": [{"delta": {"content": "네."}, "finish_reason": None}]}
        yield {"choices": [{"delta": {}, "finish_reason": "stop"}]}

    async def fake_search(query: str) -> list[dict]:
        return results

    orchestrator.llm_client._make_stream_request = fake_stream_request
    orchestrator._search_knowledge = fake_search
    orchestrator.publish_tts_request = AsyncMock()
    return orchestrator


@pytest.mark.asyncio
async def test_should_attach_relevant_knowledge_to_voice_question() -> None:
    sent: list = []
    orchestrator = _orchestrator(
        [{"content": "윤하람의 소속사는 파란별엔터테인먼트이다.", "score": 0.63,
          "metadata": {"filename": "윤하람.md"}}],
        sent,
    )
    await orchestrator.handle_wake_word()

    await orchestrator.handle_stt_result("윤하람 소속사가 어디야?")

    assert "파란별엔터테인먼트" in str(sent[0])


@pytest.mark.asyncio
async def test_should_not_attach_low_score_results() -> None:
    sent: list = []
    orchestrator = _orchestrator(
        [{"content": "POST /api/users 요청 본문", "score": 0.49, "metadata": {}}],
        sent,
    )
    await orchestrator.handle_wake_word()

    await orchestrator.handle_stt_result("안녕하세요")

    assert "/api/users" not in str(sent[0])
