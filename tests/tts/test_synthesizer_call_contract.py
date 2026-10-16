"""
TTS 구독자 ↔ 합성기 호출 계약 테스트

실제 KokoroTTS.synthesize 는 synthesize(text) 만 받고 np.ndarray(float32) 를 반환한다.
이전 구독자는 synthesize(text=, voice=, speed=) 로 불러 TypeError 가 나고,
반환값을 `if audio_data` 로 검사해 배열에서도 실패했다.
→ 오디오가 한 번도 발행되지 않았다.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest


class TextOnlySynthesizer:
    """KokoroTTS 와 같은 시그니처의 가짜 합성기"""

    def __init__(self) -> None:
        self.texts: list[str] = []

    def synthesize(self, text: str) -> np.ndarray:
        self.texts.append(text)
        return np.linspace(-0.5, 0.5, 8, dtype=np.float32)


@pytest.mark.asyncio
async def test_should_publish_audio_when_synthesizer_accepts_text_only() -> None:
    from services.tts.app.redis_subscriber import TTS_AUDIO_CHANNEL, TTSRedisSubscriber

    synthesizer = TextOnlySynthesizer()
    with patch("services.tts.app.redis_subscriber.aioredis") as mock_aioredis:
        mock_redis = MagicMock()
        mock_redis.publish = AsyncMock()
        mock_redis.pubsub.return_value = MagicMock()
        mock_aioredis.Redis.return_value = mock_redis

        subscriber = TTSRedisSubscriber(synthesizer=synthesizer)
        await subscriber.connect()
        await subscriber._handle_message(
            json.dumps(
                {
                    "session_id": "sess-tts",
                    "text": "안녕하세요.",
                    "voice": "af_heart",
                    "speed": 1.0,
                }
            )
        )

    assert synthesizer.texts == ["안녕하세요."]
    audio_payloads = [
        c[0][1]
        for c in mock_redis.publish.call_args_list
        if c[0][0] == TTS_AUDIO_CHANNEL
    ]
    assert audio_payloads, "오디오 청크가 발행되지 않았다"
    published = np.frombuffer(b"".join(audio_payloads), dtype=np.float32)
    np.testing.assert_allclose(published, np.linspace(-0.5, 0.5, 8, dtype=np.float32))
