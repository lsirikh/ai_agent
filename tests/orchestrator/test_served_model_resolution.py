"""
서비스 중인 모델 자동 선택 테스트

설정 화면에서 다른 모델을 '적용'하면 .env 의 LLM_MODEL 만 바뀌고 vLLM 은 그대로라,
오케스트레이터가 서비스되지 않는 모델을 요청해 404 → 빈 응답 → TTS 없음이 됐다.
요청 전에 vLLM 이 실제 서비스하는 모델 목록을 확인해,
설정 모델이 없으면 서비스 중인 모델을 쓴다.
"""

import pytest


@pytest.mark.asyncio
async def test_should_use_served_model_when_configured_one_is_not_served() -> None:
    from services.orchestrator.app.llm_client import LLMClient

    client = LLMClient(base_url="http://llm.test", model_name="deepseek-ai/Not-Served")

    async def served() -> list[str]:
        return ["Qwen/Qwen2.5-7B-Instruct-AWQ"]

    client._fetch_served_models = served

    assert await client.resolve_model() == "Qwen/Qwen2.5-7B-Instruct-AWQ"


@pytest.mark.asyncio
async def test_should_keep_configured_model_when_it_is_served() -> None:
    from services.orchestrator.app.llm_client import LLMClient

    client = LLMClient(base_url="http://llm.test", model_name="A")

    async def served() -> list[str]:
        return ["B", "A"]

    client._fetch_served_models = served

    assert await client.resolve_model() == "A"


@pytest.mark.asyncio
async def test_should_keep_configured_model_when_server_list_is_unavailable() -> None:
    from services.orchestrator.app.llm_client import LLMClient

    client = LLMClient(base_url="http://llm.test", model_name="A")

    async def unavailable() -> list[str]:
        raise OSError("connection refused")

    client._fetch_served_models = unavailable

    assert await client.resolve_model() == "A"
