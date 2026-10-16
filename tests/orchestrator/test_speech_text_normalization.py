"""
음성 답변 문장 다듬기 테스트 (실제 음성 E2E 에서 확인)

1. 번호 목록이 문장 나누기에서 "…좋겠네요: 1." / "회의 일정과 목적 2." 처럼 갈라져
   번호가 문장 끝에 붙어 읽혔다 → "첫째, 회의 일정과 목적" 처럼 읽는다.
2. MeloTTS 는 ';' 같은 기호에서 합성에 실패했다(KeyError ';') → 쉼표로 바꾼다.
3. 마크다운 기호(**, #, -)는 읽지 않는다.
"""

from unittest.mock import AsyncMock, patch

import pytest


async def _spoken(tokens: list[str]) -> list[str]:
    from services.orchestrator.app.orchestrator import Orchestrator

    with patch.object(Orchestrator, "_setup_redis", return_value=AsyncMock()):
        orchestrator = Orchestrator(redis_client=AsyncMock())

    async def fake_stream_request(messages, **kwargs):
        for token in tokens:
            yield {"choices": [{"delta": {"content": token}, "finish_reason": None}]}
        yield {"choices": [{"delta": {}, "finish_reason": "stop"}]}

    orchestrator.llm_client._make_stream_request = fake_stream_request
    spoken: list[str] = []

    async def capture(text: str) -> None:
        spoken.append(text)

    orchestrator.publish_tts_request = capture
    await orchestrator.handle_wake_word()
    await orchestrator.handle_stt_result("회의 준비물 알려 줘")
    return spoken


@pytest.mark.asyncio
async def test_should_read_numbered_list_as_ordinals() -> None:
    spoken = await _spoken(
        [
            "다음 자료를 준비하면 좋겠네요:\n1. 회의 일정과 목적\n",
            "2. 팀원들의 업데이트 정보\n3. 논의할 주요 사항",
        ]
    )

    joined = " ".join(spoken)
    assert "첫째, 회의 일정과 목적" in joined
    assert "둘째, 팀원들의 업데이트 정보" in joined
    assert "셋째, 논의할 주요 사항" in joined
    assert not any(s.rstrip().endswith(("1.", "2.", "3.")) for s in spoken)


@pytest.mark.asyncio
async def test_should_replace_symbols_tts_cannot_read() -> None:
    spoken = await _spoken(["맑으면 산책하세요; **비가 오면** 영화를 보세요."])

    joined = " ".join(spoken)
    assert ";" not in joined and "*" not in joined
    assert "산책하세요, 비가 오면 영화를 보세요." in joined
