"""호출어 확인용 STT 호출: 최근 소리를 WAV 로 만들어 STT 서비스에 보낸다."""

import asyncio
import io
import wave
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np


def test_audio_is_sent_as_16bit_wav() -> None:
    from services.wake_word.app.stt_check import to_wav

    data = to_wav(np.full(1600, 0.5, dtype=np.float32), 16000)

    with wave.open(io.BytesIO(data)) as w:
        assert (w.getframerate(), w.getsampwidth(), w.getnframes()) == (16000, 2, 1600)


def test_verifier_returns_transcribed_text_in_korean() -> None:
    from services.wake_word.app import stt_check

    response = MagicMock(status=200)
    response.json = AsyncMock(return_value={"text": "헤이 자비스"})
    post = MagicMock()
    post.return_value.__aenter__ = AsyncMock(return_value=response)
    post.return_value.__aexit__ = AsyncMock(return_value=False)
    session = MagicMock(post=post)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)

    with patch.object(stt_check.aiohttp, "ClientSession", return_value=session):
        verify = stt_check.make_verifier("http://stt:8001")
        text = asyncio.run(verify(np.zeros(1600, dtype=np.float32)))

    assert text == "헤이 자비스"
    assert post.call_args.args[0] == "http://stt:8001/transcribe"
