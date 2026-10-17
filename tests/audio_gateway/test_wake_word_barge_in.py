"""
TTS 로 말하는 도중 '헤이 자비스' 로 끼어들기 (사용자 요청 2026-10-17)

에너지·VAD 끼어들기는 스피커 소리가 마이크로 다시 들어와(노이즈 캔슬링·다중 마이크 없음)
동작하지 않았다. 재생 중에도 소리를 웨이크워드 서비스로 보내고, 호출어가 들리면
재생을 끝내고 듣기·녹음으로 바꾼다. 듣는 동안 남은 답 음성은 앱으로 보내지 않는다.
"""

import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest
from fastapi.testclient import TestClient

sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "../../services/audio_gateway")
)


def test_audio_reaches_wake_word_while_tts_is_playing() -> None:
    from app import main
    from app.barge_in import PlaybackState

    redis = AsyncMock()
    vad = MagicMock()
    vad.detect.return_value = {"is_speech": True, "probability": 0.9}
    main.barge_in_detector.set_playback_state(PlaybackState.PLAYING)
    try:
        with patch.object(main, "redis_client", redis), patch.object(
            main, "vad", vad
        ), patch.object(main, "reset_session", AsyncMock()), patch.object(
            main.barge_in_detector, "detect_and_publish", AsyncMock(return_value={})
        ):
            with TestClient(main.app).websocket_connect("/ws/audio") as ws:
                ws.send_bytes(np.zeros(1600, dtype=np.int16).tobytes())
                ws.receive_json()
    finally:
        main.barge_in_detector.set_playback_state(PlaybackState.IDLE)

    channels = [c.args[0] for c in redis.publish.await_args_list]
    assert main.AUDIO_OUTPUT_CHANNEL in channels


@pytest.mark.asyncio
async def test_wake_word_during_playback_stops_playback_and_listens() -> None:
    from app import main
    from app.barge_in import PlaybackState

    main.barge_in_detector.set_playback_state(PlaybackState.PLAYING)
    with patch.object(main, "on_speech_started", AsyncMock()):
        await main.handle_wake_word_event({"type": "wake_word_detected"})
    try:
        assert main.barge_in_detector.playback_state == PlaybackState.IDLE
        assert main._listening_mode is True
    finally:
        await main.reset_session()


@pytest.mark.asyncio
async def test_leftover_answer_audio_is_not_played_while_listening() -> None:
    from app import main

    client = AsyncMock()
    main.register_playback_client(client)
    with patch.object(main, "on_speech_started", AsyncMock()):
        await main.handle_wake_word_event({"type": "wake_word_detected"})
    try:
        await main.forward_tts_audio(b"\x00\x00\x80\x3f")
        client.send_bytes.assert_not_awaited()
    finally:
        await main.reset_session()
        main.unregister_playback_client(client)

    await main.forward_tts_audio(b"\x00\x00\x80\x3f")
    client.send_bytes.assert_not_awaited()  # 등록 해제 뒤
