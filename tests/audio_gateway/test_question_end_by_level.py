"""
질문이 끝났는지 소리 크기로도 판단 (사용자 요청 2026-10-18)

'말을 다 끝냈는데 무음이 아니면 계속 기다린다' — TV·선풍기·다른 사람 말소리가 있으면
VAD 가 계속 '말소리' 라고 해 녹음이 끝나지 않았다(실측 12.4초).
→ 이번 질문에서 들은 사용자 목소리 크기를 익히고,
  그보다 뚜렷이 작은 소리는 무음으로 본다.
"""

import os
import sys
from unittest.mock import AsyncMock, patch

import numpy as np
import pytest

sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "../../services/audio_gateway")
)


def _chunk(rms):
    return np.full(1600, rms, dtype=np.float32)


def test_background_much_quieter_than_voice_is_not_voice() -> None:
    from app.speech_end import VoiceLevel

    level = VoiceLevel()
    assert all(level.is_voice(0.1, True) for _ in range(10))

    assert level.is_voice(0.02, True) is False  # 목소리의 1/5 — 배경 소리
    assert level.is_voice(0.09, True) is True
    assert level.is_voice(0.1, False) is False  # VAD 가 말소리가 아니라고 함


def test_first_sounds_count_as_voice_until_level_is_known() -> None:
    from app.speech_end import VoiceLevel

    level = VoiceLevel()

    assert level.is_voice(0.01, True) is True


@pytest.mark.asyncio
async def test_question_ends_when_only_quieter_background_remains() -> None:
    from app import main

    main._listening_mode = True
    main._is_recording = True
    main._question_wait_until = None
    main.voice_level.reset()
    speech = {"is_speech": True, "probability": 0.9}

    with patch.object(main, "_logger") as logger:
        logger.log = AsyncMock()
        logger.info = AsyncMock()
        for _ in range(10):  # 사용자 질문
            await main.handle_vad_result(speech, "s", _chunk(0.1))
        spoke_at = main._last_speech_time
        for _ in range(5):  # 질문 뒤 TV 소리(VAD 는 말소리라고 함)
            await main.handle_vad_result(speech, "s", _chunk(0.015))

    assert main._last_speech_time == spoke_at  # 배경 소리는 말 끝 시간을 늦추지 않는다
    main._listening_mode = False
    main._is_recording = False
