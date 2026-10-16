"""
발화 종료 판정 회귀 테스트

듣기 중에는 VAD 의 짧은 무음(speech_ended, 0.3s)으로 녹음을 끝내지 않고
설정한 end_pause_seconds 무음(process_speech_timeout)으로만 끝낸다.
이전에는 "헤이 자비스" 뒤 잠깐 쉬기만 해도 녹음이 끝나 STT 가 웨이크워드만 받아 적었다.
"""

import os
import sys
from unittest.mock import AsyncMock, patch

import pytest

# 다른 audio_gateway 테스트와 같은 방식으로 서비스 패키지(app)를 불러온다
sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "../../services/audio_gateway")
)


@pytest.mark.asyncio
async def test_should_keep_recording_when_vad_reports_short_pause() -> None:
    from app import main

    main._listening_mode = True
    main._is_recording = True
    main._previous_is_speech = True
    vad_result = {
        "is_speech": False,
        "probability": 0.1,
        "speech_started": False,
        "speech_ended": True,
    }

    with (
        patch.object(main, "on_speech_ended", new_callable=AsyncMock) as ended,
        patch.object(main, "_logger") as logger,
    ):
        logger.info = AsyncMock()
        result = await main.handle_vad_result(vad_result, session_id="s")

    ended.assert_not_called()
    assert result is None
    assert main._is_recording is True
