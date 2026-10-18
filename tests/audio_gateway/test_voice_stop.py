"""
[중단] 버튼(사용자 요청 2026-10-18): 게이트웨이는 남은 답 음성을 앱으로 보내지 않고,
듣는 중이었으면 녹음을 끝낸다. 다음 질문(듣기 시작)부터는 다시 보낸다.
"""

import asyncio
import os
import sys
from unittest.mock import AsyncMock, patch

import numpy as np

sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "../../services/audio_gateway")
)


def test_stop_drops_remaining_answer_audio_until_next_turn() -> None:
    from app import main

    client = AsyncMock()
    main.register_playback_client(client)
    audio = np.zeros(2400, dtype=np.float32).tobytes()
    try:
        with patch.object(main, "_logger") as logger:
            logger.info = AsyncMock()
            asyncio.run(main.stop_answer())
            asyncio.run(main.forward_tts_audio(audio))
            assert client.send_bytes.await_count == 0
            assert not main.playback_tracker.playing()

            main.resume_answer_audio()  # 다음 턴(듣기 시작)
            asyncio.run(main.forward_tts_audio(audio))
            assert client.send_bytes.await_count == 1
    finally:
        main.unregister_playback_client(client)
        main.resume_answer_audio()


def test_stop_while_listening_ends_listening() -> None:
    from app import main

    with patch.object(main, "_logger") as logger, patch.object(
        main, "on_speech_started", AsyncMock()
    ):
        logger.info = AsyncMock()
        asyncio.run(main.handle_wake_word_event({"type": "wake_word_detected"}))
        assert main._listening_mode is True
        asyncio.run(main.stop_answer())

    assert main._listening_mode is False
    main.resume_answer_audio()
