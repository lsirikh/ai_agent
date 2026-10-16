"""
TTS 첫 응답 지연 회귀 테스트

MeloTTS 는 프로세스마다 첫 합성에서 한국어 BERT 를 준비하느라 약 60초가 걸렸고,
그 동기 호출이 이벤트 루프를 막아 다른 요청·헬스체크까지 멈췄다(첫 음성 답변이 오지 않음).
→ 시작 시 워밍업하고, 합성은 스레드로 넘겨 루프를 막지 않는다.
"""

import asyncio
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest


class SlowSynthesizer:
    def __init__(self) -> None:
        self.texts: list[str] = []

    def synthesize(self, text: str) -> np.ndarray:
        self.texts.append(text)
        time.sleep(0.3)  # 동기·무거운 합성
        return np.zeros(240, dtype=np.float32)


def test_should_warm_up_synthesizer_once() -> None:
    from services.tts.app.melo_adapter import warm_up

    synth = SlowSynthesizer()

    warm_up(synth)

    assert len(synth.texts) == 1


@pytest.mark.asyncio
async def test_should_not_block_event_loop_while_synthesizing() -> None:
    from services.tts.app.redis_subscriber import TTSRedisSubscriber

    with patch("services.tts.app.redis_subscriber.aioredis") as mock_aioredis:
        mock_redis = MagicMock()
        mock_redis.publish = AsyncMock()
        mock_redis.pubsub.return_value = MagicMock()
        mock_aioredis.Redis.return_value = mock_redis
        subscriber = TTSRedisSubscriber(synthesizer=SlowSynthesizer())
        await subscriber.connect()

        ticks = 0

        async def ticker() -> None:
            nonlocal ticks
            while True:
                await asyncio.sleep(0.02)
                ticks += 1

        task = asyncio.create_task(ticker())
        await subscriber._handle_message(
            json.dumps({"session_id": "s", "text": "안녕"})
        )
        task.cancel()

    # 합성 0.3초 동안 루프가 살아 있었다면 여러 번 돌았어야 한다
    assert ticks >= 5
