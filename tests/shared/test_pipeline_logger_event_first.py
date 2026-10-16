"""
PipelineLogger 이벤트 우선 호출 형식 테스트

서비스 코드 78곳이 info/warning/error(event, message, session_id=...) 형식으로 부른다.
이전에는 두 번째 위치 인자가 session_id 자리에 들어가
"got multiple values for argument 'session_id'" 로 실패했다(TTS 가 합성 전에 중단됨).
"""

from unittest.mock import AsyncMock

import pytest


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method, level", [("info", "info"), ("warning", "warning"), ("error", "error")]
)
async def test_should_record_event_name_when_called_event_first(
    method: str, level: str
) -> None:
    from shared.pipeline_logger import PipelineLogger

    logger = PipelineLogger(service_name="tts", redis_client=AsyncMock())

    entry = await getattr(logger, method)(
        "tts_request_received",
        "TTS request received",
        session_id="sess-1",
        metadata={"voice": "af_heart"},
    )

    assert entry["event"] == "tts_request_received"
    assert entry["session_id"] == "sess-1"
    assert entry["level"] == level
    assert entry["data"]["message"] == "TTS request received"
    assert entry["data"]["metadata"] == {"voice": "af_heart"}


@pytest.mark.asyncio
async def test_should_keep_message_only_call_when_single_argument() -> None:
    from shared.pipeline_logger import PipelineLogger

    logger = PipelineLogger(service_name="tts", redis_client=AsyncMock())

    entry = await logger.info("plain message", session_id="sess-2")

    assert entry["event"] == "info"
    assert entry["session_id"] == "sess-2"
    assert entry["data"]["message"] == "plain message"
