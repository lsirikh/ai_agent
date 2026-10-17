"""
현재 시각 근거 테스트 (실제 스택에서 확인)

세션 기록에 이전 답("현재 시간은 17시입니다")이 남아 있으면 모델이 get_time 도구를
부르지 않고 그 답을 따라 했다(실측 0/3, 실제 08:52). 매 턴 지금 시각을 이번 질문의
근거로 붙이면 정확히 답했다(3/3). 시각은 프롬프트 뒤쪽(이번 질문)에 붙어
앞쪽 고정 접두사 캐시를 깨지 않는다.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

STALE_HISTORY = [
    {"role": "user", "content": "지금 몇 시야?"},
    {"role": "assistant", "content": "현재 시간은 17시입니다."},
]


def test_should_format_current_time_in_korean() -> None:
    from datetime import datetime, timezone

    import shared.tools as tools

    fixed = datetime(2026, 10, 17, 8, 52, tzinfo=timezone.utc)
    with patch.object(tools, "_now", return_value=fixed):
        assert tools.current_time_text().startswith(
            "2026년 10월 17일 (토요일) 08시 52분"
        )


@pytest.mark.asyncio
async def test_voice_turn_sends_current_time_even_with_stale_history() -> None:
    import shared.tools as tools
    from services.orchestrator.app.orchestrator import Orchestrator

    sent: list = []
    with patch.object(Orchestrator, "_setup_redis", return_value=AsyncMock()):
        orchestrator = Orchestrator(redis_client=AsyncMock())

    async def fake_stream_request(messages, **kwargs):
        sent.append(str(messages))
        yield {"choices": [{"delta": {"content": "네."}, "finish_reason": None}]}
        yield {"choices": [{"delta": {}, "finish_reason": "stop"}]}

    async def stale_context():
        return STALE_HISTORY, None

    orchestrator.llm_client._make_stream_request = fake_stream_request
    orchestrator._load_session_context = stale_context
    orchestrator.publish_tts_request = AsyncMock()
    await orchestrator.handle_wake_word()

    with patch.object(
        tools, "current_time_text", return_value="2026년 10월 17일 08시 52분"
    ):
        await orchestrator.handle_stt_result("지금 몇 시야?")

    assert "2026년 10월 17일 08시 52분" in sent[-1]


@pytest.mark.asyncio
async def test_chat_turn_sends_current_time() -> None:
    import shared.tools as tools
    from services.backend.app.services.chat_service import ChatService

    captured: dict = {}

    async def mock_stream(text, system_prompt=None, **kwargs):
        captured.update(kwargs)
        yield "네."

    llm = MagicMock()
    llm.generate_stream = mock_stream
    service = ChatService(llm_client=llm)

    with patch.object(
        tools, "current_time_text", return_value="2026년 10월 17일 08시 52분"
    ):
        async for _ in service.process_message(
            "00000000-0000-4000-8000-000000000001", "지금 몇 시야?", use_rag=False
        ):
            pass

    assert "2026년 10월 17일 08시 52분" in (captured.get("reference") or "")
