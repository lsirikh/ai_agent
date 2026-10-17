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


def _clock():
    """조각마다 0.1초씩 가는 시계 (time.time() 해상도가 낮아 같은 값이 나온다)."""
    import time
    from unittest.mock import MagicMock

    fake = MagicMock(wraps=time)
    ticks = iter(1000.0 + 0.1 * i for i in range(10_000))
    fake.time.side_effect = lambda: next(ticks)
    return fake


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

    with patch.object(main, "_logger") as logger, patch.object(main, "time", _clock()):
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


def test_vad_tail_and_background_do_not_lower_the_voice_level() -> None:
    # E2E 실측: 호출어 뒤 VAD 가 잠시 '말소리' 라고 한 아주 작은 소리를 목소리로 익혀
    # 기준이 낮아졌고, 배경 말소리(목소리의 약 1/4)를 질문으로 이어 받아 적었다
    from app.speech_end import VoiceLevel

    level = VoiceLevel()
    tail = [level.is_voice(0.002, True) for _ in range(5)]  # 호출어 뒤 VAD 꼬리
    for _ in range(10):
        level.is_voice(0.1, True)  # 질문
    background = [level.is_voice(rms, True) for rms in [0.03, 0.035, 0.028] * 20]

    assert not any(tail)
    assert sum(background) <= 3  # 가끔 큰 음절 정도만


@pytest.mark.asyncio
async def test_single_loud_syllable_in_background_does_not_extend_question() -> None:
    # E2E 실측: 배경 말소리의 큰 음절 하나(0.1초)가 말 끝을 1.4초 늦췄다
    from app import main

    main._listening_mode = True
    main._is_recording = True
    main.voice_level.reset()
    speech = {"is_speech": True, "probability": 0.9}

    with patch.object(main, "_logger") as logger, patch.object(main, "time", _clock()):
        logger.log = AsyncMock()
        for _ in range(10):
            await main.handle_vad_result(speech, "s", _chunk(0.1))
        spoke_at = main._last_speech_time
        for rms in [0.015, 0.015, 0.1, 0.015, 0.015]:
            await main.handle_vad_result(speech, "s", _chunk(rms))

    assert main._last_speech_time == spoke_at
    main._listening_mode = False
    main._is_recording = False


@pytest.mark.asyncio
async def test_audio_after_the_question_is_not_sent_to_stt() -> None:
    # 말 끝 뒤의 배경 소리까지 받아 적었다 → 마지막 목소리 0.5초 뒤까지만 보낸다
    import time

    from app import main

    main._is_recording = True
    main._last_speech_time = time.time() - 2.0
    with (
        patch.object(main, "on_speech_ended", AsyncMock()) as ended,
        patch.object(main, "_logger") as logger,
    ):
        logger.info = AsyncMock()
        await main.process_speech_timeout()

    trim = ended.await_args.kwargs["trim_seconds"]
    assert 1.4 <= trim <= 1.6
