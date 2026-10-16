"""
TTS 재생 전달 테스트

게이트웨이는 Docker 안에서 돌아 Windows 스피커로 소리를 낼 수 없고,
/ws/audio 로는 VAD JSON 만 보냈다 → 답변 음성이 사용자에게 한 번도 들리지 않았다.
TTS 오디오(float32 24kHz)를 연결된 클라이언트에 바이너리 프레임으로 보내
클라이언트가 재생한다.
"""

import os
import sys
from unittest.mock import AsyncMock

import pytest

sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "../../services/audio_gateway")
)


@pytest.mark.asyncio
async def test_should_forward_tts_audio_to_every_connected_client() -> None:
    from app import main

    first, second = AsyncMock(), AsyncMock()
    main.register_playback_client(first)
    main.register_playback_client(second)
    try:
        await main.forward_tts_audio(b"\x00\x00\x80\x3f")
    finally:
        main.unregister_playback_client(first)
        main.unregister_playback_client(second)

    first.send_bytes.assert_awaited_once_with(b"\x00\x00\x80\x3f")
    second.send_bytes.assert_awaited_once_with(b"\x00\x00\x80\x3f")


@pytest.mark.asyncio
async def test_should_drop_client_whose_send_fails() -> None:
    from app import main

    broken, healthy = AsyncMock(), AsyncMock()
    broken.send_bytes.side_effect = RuntimeError("closed")
    main.register_playback_client(broken)
    main.register_playback_client(healthy)
    try:
        await main.forward_tts_audio(b"a")
        await main.forward_tts_audio(b"b")
    finally:
        main.unregister_playback_client(healthy)

    assert broken.send_bytes.await_count == 1
    assert healthy.send_bytes.await_count == 2
