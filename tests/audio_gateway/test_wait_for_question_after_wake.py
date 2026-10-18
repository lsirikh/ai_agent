"""
호출어 뒤 질문을 시작할 시간을 준다 (실측 2026-10-17)

웨이크워드가 호출어를 말하는 도중에 감지되면 그때부터 '2초 무음 = 말 끝' 이 적용돼,
"헤이 자비스 … (2.5초 쉼) 부산은 지금 비 와?" 에서 질문 전에 녹음이 끝났다
(호출어 끝부분 2.1초만 STT 로 갔다). 감지 뒤 일정 시간은 무음이어도 기다린다.
"""

import os
import sys
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "../../services/audio_gateway")
)


@pytest.mark.asyncio
async def test_should_wait_for_question_after_wake_word_before_ending() -> None:
    from app import main

    now = [1000.0]
    with patch.object(main.time, "time", lambda: now[0]), patch.object(
        main, "on_speech_started", AsyncMock()
    ), patch.object(main, "_speech_timeout_seconds", 2.0):
        await main.handle_wake_word_event({"type": "wake_word_detected"})
        try:
            now[0] += 2.5  # 호출어 뒤 2.5초 동안 아직 질문을 시작하지 않음
            assert main.check_speech_timeout() is False

            # 실측(2026-10-18): 사용자는 호출어 뒤 5초쯤 쉬었다가 질문했는데
            # 4초에 끝내 놓쳤다 → 목소리를 못 들었으면
            # NO_QUESTION_TIMEOUT_SECONDS 까지 기다린다
            now[0] += main.WAIT_FOR_QUESTION_SECONDS
            assert main.check_speech_timeout() is False
            # 질문 없이 기다림이 지나면 끝낸다
            now[0] = 1000.0 + main.NO_QUESTION_TIMEOUT_SECONDS
            assert main.check_speech_timeout() is True
        finally:
            await main.reset_session()


@pytest.mark.asyncio
async def test_end_pause_applies_once_waiting_is_over() -> None:
    from app import main

    now = [1000.0]
    with patch.object(main.time, "time", lambda: now[0]), patch.object(
        main, "on_speech_started", AsyncMock()
    ), patch.object(main, "_speech_timeout_seconds", 2.0):
        await main.handle_wake_word_event({"type": "wake_word_detected"})
        try:
            now[0] += main.WAIT_FOR_QUESTION_SECONDS + 1  # 질문 중
            main._last_speech_time = now[0]
            main._voice_heard = True  # (handle_vad_result 가 목소리를 들으면 켠다)
            now[0] += 2.0  # 질문 뒤 2초 무음
            assert main.check_speech_timeout() is True
        finally:
            await main.reset_session()


@pytest.mark.asyncio
async def test_recording_is_not_cut_when_no_voice_was_heard() -> None:
    # 실측(2026-10-18): 목소리를 못 들었는데도 '마지막 목소리(=호출어 순간)
    # 0.5초 뒤까지' 로 잘라 0.5초만 STT 로 보냈다 — 빈 결과로 아무 말 없이 꺼졌다
    from app import main

    now = [1000.0]
    with patch.object(main.time, "time", lambda: now[0]), patch.object(
        main, "on_speech_started", AsyncMock()
    ), patch.object(main, "on_speech_ended", AsyncMock()) as ended, patch.object(
        main, "_logger"
    ) as logger:
        logger.info = AsyncMock()
        await main.handle_wake_word_event({"type": "wake_word_detected"})
        now[0] += main.NO_QUESTION_TIMEOUT_SECONDS
        await main.process_speech_timeout()

    assert ended.await_args.kwargs["trim_seconds"] == 0
