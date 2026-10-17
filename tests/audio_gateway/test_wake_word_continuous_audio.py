"""
대기 중에는 마이크 소리를 끊지 않고 웨이크워드 서비스로 보낸다 (실측 2026-10-17)

VAD 가 말소리로 본 100ms 조각만 보내면 웨이크워드 모델(openWakeWord)이
띄엄띄엄한 소리를 받아 점수가 떨어졌다.
같은 "Hey Jarvis" 에 원격 데스크톱 마이크 수준 잡음(RMS 0.033)을 섞으면
연속 입력 99.9% · VAD 로 자른 입력 40.7%.
사용자 실측 32~42%(기준 30%)와 같다.
"""

import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
from fastapi.testclient import TestClient

sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "../../services/audio_gateway")
)


def test_idle_audio_reaches_wake_word_even_when_vad_says_silence() -> None:
    from app import main
    from app.barge_in import PlaybackState

    redis = AsyncMock()
    vad = MagicMock()
    vad.detect.return_value = {"is_speech": False, "probability": 0.2}
    main.barge_in_detector.set_playback_state(PlaybackState.IDLE)

    with patch.object(main, "redis_client", redis), patch.object(
        main, "vad", vad
    ), patch.object(main, "reset_session", AsyncMock()), patch.object(
        main, "_listening_mode", False
    ):
        with TestClient(main.app).websocket_connect("/ws/audio") as ws:
            ws.send_bytes(np.zeros(1600, dtype=np.int16).tobytes())
            ws.receive_json()

    channels = [c.args[0] for c in redis.publish.await_args_list]
    assert main.AUDIO_OUTPUT_CHANNEL in channels
