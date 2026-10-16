"""
STT 이벤트 루프 막힘 회귀 테스트

모델 로드(첫 요청 때)와 전사가 이벤트 루프에서 동기로 돌아
/health 가 응답하지 못했고,
unhealthy 컨테이너를 재시작하는 감시자(autoheal)가 STT 를 죽여
음성 인식이 시간 초과됐다.
→ 시작 시 모델을 스레드에서 미리 불러오고, 전사도 스레드에서 돈다.
"""

import asyncio
import io
import time
import wave
from unittest.mock import AsyncMock, patch

import numpy as np
import pytest


class SlowTranscriber:
    def transcribe(self, audio, language=None):
        time.sleep(0.3)
        return {"text": "안녕", "confidence": 0.9, "language": "ko", "segments": []}


def _wav() -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(np.zeros(16000, dtype=np.int16).tobytes())
    return buf.getvalue()


@pytest.mark.asyncio
async def test_should_keep_event_loop_alive_while_transcribing() -> None:
    from fastapi import UploadFile

    from services.stt.app import main

    ticks = 0

    async def ticker() -> None:
        nonlocal ticks
        while True:
            await asyncio.sleep(0.02)
            ticks += 1

    with (
        patch.object(main, "get_transcriber", return_value=SlowTranscriber()),
        patch.object(main, "_logger") as logger,
    ):
        logger.info = AsyncMock()
        logger.error = AsyncMock()
        task = asyncio.create_task(ticker())
        audio = UploadFile(filename="a.wav", file=io.BytesIO(_wav()))
        result = await main.transcribe_audio(audio=audio, language="ko")
        task.cancel()

    assert result.text == "안녕"
    assert ticks >= 5


@pytest.mark.asyncio
async def test_should_load_model_in_background_at_startup() -> None:
    from services.stt.app import main

    loaded = []

    with (
        patch.object(main, "get_transcriber", side_effect=lambda: loaded.append(1)),
        patch.object(main, "heartbeat_task", new=AsyncMock()),
        patch.object(main, "_logger") as logger,
    ):
        logger.info = AsyncMock()
        logger.close = AsyncMock()
        async with main.lifespan(main.app):
            for _ in range(50):
                if loaded:
                    break
                await asyncio.sleep(0.01)

    assert loaded == [1]
