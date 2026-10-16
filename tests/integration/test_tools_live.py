"""
[live] 도구 호출 — 실제 vLLM(--enable-auto-tool-choice --tool-call-parser hermes) 대상.
EDGEVOICE_LIVE=1 일 때만 돈다.

    EDGEVOICE_LIVE=1 python -m pytest tests/integration/test_tools_live.py

- (j) get_time 이 실제 vLLM 에서 왕복된다(음성·채팅 클라이언트 모두),
  `<tool_call>` 텍스트가 답에 없다
- 시험용 stdio MCP 서버의 읽기 전용 도구(status)를 실제 모델이 불러 답한다
- 파괴적 MCP 도구(restart)는 확인 없이 실행되지 않는다
"""

import os
import sys

import pytest

VLLM = os.getenv("EDGEVOICE_VLLM_URL", "http://localhost:11003")
MCP_SERVER = os.path.join(
    os.path.dirname(__file__), "..", "shared", "mcp_test_server.py"
)

pytestmark = pytest.mark.skipif(
    os.getenv("EDGEVOICE_LIVE") != "1", reason="live: EDGEVOICE_LIVE=1 일 때만 실행"
)


async def _run(stream):
    text, events = "", []
    async for item in stream:
        if isinstance(item, str):
            text += item
        else:
            events.append(item)
    return text, events


@pytest.mark.asyncio
async def test_live_get_time_round_trip_voice_client():
    from services.orchestrator.app.llm_client import LLMClient
    from shared.tools import build_registry

    llm = LLMClient(
        base_url=VLLM, system_prompt="당신은 한국어 음성 비서입니다. 짧게 답하세요."
    )

    text, events = await _run(
        llm.generate_stream(
            "지금 정확히 몇 시 몇 분이야? 도구로 확인해서 알려 줘.",
            history=[],
            tools=build_registry({"internet_enabled": False}),
        )
    )

    assert [e["name"] for e in events if e["type"] == "tool_call"] == ["get_time"]
    assert any(ch.isdigit() for ch in text), text
    assert "<tool_call>" not in text


@pytest.mark.asyncio
async def test_live_get_time_round_trip_chat_client():
    from services.backend.app.services.llm_client import SimpleLLMClient
    from shared.tools import build_registry

    llm = SimpleLLMClient(base_url=VLLM)
    try:
        text, events = await _run(
            llm.generate_stream(
                "오늘 날짜와 요일을 도구로 확인해서 알려 줘.",
                tools=build_registry({"internet_enabled": False}),
            )
        )
    finally:
        await llm.close()

    assert "get_time" in [e["name"] for e in events if e["type"] == "tool_call"]
    assert text.strip() and "<tool_call>" not in text


@pytest.mark.asyncio
async def test_live_mcp_tools_with_real_model():
    from services.orchestrator.app.llm_client import LLMClient
    from shared.mcp_client import MCPManager, MCPServerConfig
    from shared.tools import build_registry

    manager = MCPManager(
        [
            MCPServerConfig(
                name="ironwall",
                command=sys.executable,
                args=[MCP_SERVER],
                allowed_tools=["status", "restart"],
                trusted=True,
            )
        ]
    )
    await manager.start()
    try:
        registry = build_registry({"internet_enabled": False}, await manager.tools())
        llm = LLMClient(
            base_url=VLLM,
            system_prompt="당신은 서버 관리 비서입니다. 도구를 써서 짧게 답하세요.",
        )

        status_text, status_events = await _run(
            llm.generate_stream(
                "지금 서비스 상태가 어때? 상태 도구로 확인해 줘.",
                history=[],
                tools=registry,
            )
        )
        asked = []

        async def deny(event):
            asked.append(event["name"])
            return False

        _, restart_events = await _run(
            llm.generate_stream(
                "stt 서비스를 재시작해 줘.",
                history=[],
                tools=registry,
                confirm=deny,
            )
        )
    finally:
        await manager.close()

    results = [e for e in status_events if e["type"] == "tool_result"]
    assert results and results[0]["name"] == "ironwall__status"
    assert "정상" in results[0]["content"]
    assert status_text.strip()
    restart_results = [e for e in restart_events if e["type"] == "tool_result"]
    assert asked == ["ironwall__restart"] * len(asked) and asked
    assert all("재시작 완료" not in e["content"] for e in restart_results)
