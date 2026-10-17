"""
AEC 발산 (실측 2026-10-17): 답 문장 앞의 거의 무음인 재생 참조 뒤에 소리가 오면
NLMS 갱신이 무음(x·x ≈ 0)으로 나뉘어 계수가 폭주했다. 마이크 크기 0.1 이
49.8 로 커져 VAD·STT·웨이크워드·끼어들기가 모두 망가졌다(E2E 마이크 크기 22).
"""

import os
import sys

import numpy as np

sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "../../services/audio_gateway")
)


def _near_silence_then_speech(aec, rng):
    biggest = 0.0
    for k in range(30):
        amplitude = 1e-4 if k < 10 else 0.3  # 문장 앞 무음 → 말
        reference = amplitude * rng.standard_normal(4800)
        aec.set_playback_reference(reference.astype(np.float32))
        mic = (0.1 * rng.standard_normal(1600)).astype(np.float32)
        out = aec.process(mic)
        biggest = max(biggest, float(np.sqrt(np.mean(out**2))))
    return biggest


def test_aec_does_not_blow_up_after_near_silent_reference() -> None:
    from app.aec import AcousticEchoCanceller

    biggest = _near_silence_then_speech(
        AcousticEchoCanceller(), np.random.default_rng(0)
    )

    assert biggest < 0.2  # 입력 0.1 의 두 배를 넘지 않는다


def test_gateway_mic_audio_stays_sane_while_answer_plays() -> None:
    # API 수준: 답을 재생하는 동안 웨이크워드로 보내는 마이크 소리가 커지지 않는다
    import asyncio
    from unittest.mock import AsyncMock, MagicMock, patch

    from app import main
    from app.aec import AcousticEchoCanceller
    from app.barge_in import BargeInDetector, PlaybackState
    from fastapi.testclient import TestClient

    redis = AsyncMock()
    vad = MagicMock()
    vad.detect.side_effect = lambda _: {"is_speech": False, "probability": 0.1}
    aec = AcousticEchoCanceller()
    detector = BargeInDetector(vad=vad)
    detector.set_playback_state(PlaybackState.PLAYING)
    rng = np.random.default_rng(1)

    with (
        patch.object(main, "redis_client", redis),
        patch.object(main, "vad", vad),
        patch.object(main, "aec", aec),
        patch.object(main, "barge_in_detector", detector),
        patch.object(main, "reset_session", AsyncMock()),
    ):
        with TestClient(main.app).websocket_connect("/ws/audio") as ws:
            for k in range(30):
                amplitude = 1e-4 if k < 10 else 0.3
                aec.set_playback_reference(
                    (amplitude * rng.standard_normal(4800)).astype(np.float32)
                )
                mic = (0.1 * 32767 * rng.standard_normal(1600)).astype(np.int16)
                ws.send_bytes(mic.tobytes())
                ws.receive_json()
    asyncio.run(main.reset_session())

    sent = [
        np.frombuffer(c.args[1], dtype=np.float32)
        for c in redis.publish.await_args_list
        if c.args[0] == main.AUDIO_OUTPUT_CHANNEL
    ]
    assert sent
    assert max(float(np.sqrt(np.mean(s**2))) for s in sent) < 0.2
