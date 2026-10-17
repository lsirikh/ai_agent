"""
애매한 호출어 점수를 STT 로 확인한다 (detector.verifier).

최근 소리를 16비트 WAV 로 만들어 STT 서비스(/transcribe)에 보내고
받아 적은 글을 돌려준다.
"""

import io
import wave

import aiohttp
import numpy as np

TIMEOUT_SECONDS = 3.0


def to_wav(audio: np.ndarray, sample_rate: int) -> bytes:
    pcm = (np.clip(audio, -1.0, 1.0) * 32767).astype(np.int16)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm.tobytes())
    return buffer.getvalue()


def make_verifier(stt_url: str, sample_rate: int = 16000, language: str = "ko"):
    async def verify(audio: np.ndarray) -> str:
        form = aiohttp.FormData()
        form.add_field(
            "audio", to_wav(audio, sample_rate), filename="wake.wav",
            content_type="audio/wav",
        )
        form.add_field("language", language)
        timeout = aiohttp.ClientTimeout(total=TIMEOUT_SECONDS)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(f"{stt_url}/transcribe", data=form) as response:
                if response.status != 200:
                    return ""
                return (await response.json()).get("text") or ""

    return verify
