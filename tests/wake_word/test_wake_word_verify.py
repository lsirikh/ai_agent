"""
애매한 호출어 점수를 STT 로 확인
(사용자 보고 2026-10-18: '헤이 자비스' 를 잘 못 알아듣는다)

실측: 사용자의 '헤이 자비스' 는 40.7%·41.7% 로 감지되거나
22.5%·28.4% 로 놓쳤다(기준 30%).
하루 동안 아무도 부르지 않았을 때도 15~30% 가 63번 나와 기준만 낮출 수는 없다.
→ 15~30% 면 최근 2.5초를 STT 로 받아 적어 '자비스' 가 있을 때만 감지로 본다.

또 말소리 끼어들기 직후 모델 버퍼에 남은 '헤이 자…' 로 96% 재감지돼 막 시작한 답을
취소했다 → 듣기를 시작·끝낼 때 모델 버퍼를 비운다.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import numpy as np


def _detector(score, verifier=None):
    from services.wake_word.app.detector import WakeWordDetector

    detector = WakeWordDetector()
    detector.model = MagicMock()
    detector._use_mock = True
    detector.model.predict.return_value = {"hey_jarvis_v0.1": score}
    detector.redis_client = AsyncMock()
    detector._logger = AsyncMock()
    detector.verifier = verifier
    return detector


async def _feed(detector, chunks=5):
    for _ in range(chunks):
        await detector.detect_and_publish(np.zeros(1600, dtype=np.float32))
    if detector._verify_task:
        await detector._verify_task


def _published(detector):
    return [c.args for c in detector.redis_client.publish.await_args_list]


def test_ambiguous_score_is_confirmed_by_speech_to_text() -> None:
    verifier = AsyncMock(return_value="헤이 자비스!")
    detector = _detector(0.22, verifier)

    asyncio.run(_feed(detector))

    verifier.assert_awaited_once()
    assert len(_published(detector)) == 1
    assert "wake_word_detected" in _published(detector)[0][1]


def test_ambiguous_score_without_wake_word_in_speech_is_ignored() -> None:
    verifier = AsyncMock(return_value="오늘 날씨 어때")
    detector = _detector(0.22, verifier)

    asyncio.run(_feed(detector))

    assert _published(detector) == []


def test_low_score_is_not_sent_to_speech_to_text() -> None:
    verifier = AsyncMock(return_value="헤이 자비스")
    detector = _detector(0.05, verifier)

    asyncio.run(_feed(detector))

    verifier.assert_not_awaited()
    assert _published(detector) == []


def test_listening_clears_leftover_wake_word_audio() -> None:
    from services.wake_word.app.main import WakeWordService

    detector = _detector(0.0)
    service = WakeWordService(detector=detector)

    service.handle_state({"type": "state_change", "new_state": "LISTENING"})

    detector.model.reset.assert_called()
