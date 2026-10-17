"""
언어 섞임 방지 테스트

Qwen2.5-7B 가 한국어 프롬프트에도 답 중간에 중국어로 넘어갔다(E2E: "再加上一些细节…").
한국어 TTS 가 한자 문장을 읽지 않도록 한자가 섞인 문장은 TTS 로 보내지 않는다.
"""

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_should_not_send_chinese_sentence_to_tts() -> None:
    from services.orchestrator.app.orchestrator import Orchestrator

    with patch.object(Orchestrator, "_setup_redis", return_value=AsyncMock()):
        orchestrator = Orchestrator(redis_client=AsyncMock())

    async def fake_stream_request(messages, **kwargs):
        for token in [
            "얇은 재킷을 입으세요. ",
            "再加上一些细节。",
            " 즐거운 하루 되세요.",
        ]:
            yield {"choices": [{"delta": {"content": token}, "finish_reason": None}]}
        yield {"choices": [{"delta": {}, "finish_reason": "stop"}]}

    orchestrator.llm_client._make_stream_request = fake_stream_request
    spoken: list[str] = []

    async def capture(text: str) -> None:
        spoken.append(text)

    orchestrator.publish_tts_request = capture
    await orchestrator.handle_wake_word()

    await orchestrator.handle_stt_result("옷차림 추천해 줘")

    assert spoken
    assert all("再" not in s and "细" not in s for s in spoken)
    assert any("재킷" in s for s in spoken)


def test_should_ask_korean_and_tool_use_in_voice_prompt() -> None:
    # 프롬프트에 '중국어 금지' 같은 형식 제한을 넣으면 도구 호출이 사라져(실측)
    # 한자 문장은 위 테스트의 TTS 직전 필터로 막는다.
    from services.orchestrator.app.orchestrator import DEFAULT_VOICE_SYSTEM_PROMPT

    assert "한국어" in DEFAULT_VOICE_SYSTEM_PROMPT
    assert "도구" in DEFAULT_VOICE_SYSTEM_PROMPT
