"""
한국어로 말한 '헤이 자비스' (끼어들기 시험 2026-10-18)

openwakeword 'hey_jarvis' 는 영어 발음으로 배운 모델이라 한국어 발음(합성 Heami)이 0~10%
로 STT 확인 기준(15%)에도 못 미쳤다 — 에코가 없어도 감지하지 못했다(영어 발음은 에코 0.8
에서도 1초 안에 감지). → 짧은 말(0.6~2.5초)을 소리 크기로 찾아 STT 로 받아 적고,
'헤이 자비스' 로 시작할 때만 감지로 본다(답이 '자비스' 를 말해도 깨지 않게 시작만 본다).
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import numpy as np


def _tone(seconds, amplitude=0.1):
    t = np.arange(int(16000 * seconds)) / 16000
    return (amplitude * np.sin(2 * np.pi * 200 * t)).astype(np.float32)


def _chunks(audio):
    return [audio[i:i + 1600] for i in range(0, len(audio), 1600)]


def test_short_utterance_is_found_after_it_ends() -> None:
    from services.wake_word.app.detector import UtteranceSpotter

    spotter = UtteranceSpotter()
    audio = np.concatenate([np.zeros(16000), _tone(1.2), np.zeros(8000)])

    found = [u for c in _chunks(audio) if (u := spotter.feed(c)) is not None]

    assert len(found) == 1
    assert 1.1 <= len(found[0]) / 16000 <= 2.0


def test_long_speech_and_silence_are_not_spotted() -> None:
    from services.wake_word.app.detector import UtteranceSpotter

    spotter = UtteranceSpotter()
    audio = np.concatenate(
        [np.zeros(16000), _tone(4.0), np.zeros(8000), np.zeros(32000)]
    )

    assert all(spotter.feed(c) is None for c in _chunks(audio))


def _detector(verifier):
    from services.wake_word.app.detector import WakeWordDetector

    detector = WakeWordDetector()
    detector.model = MagicMock()
    detector._use_mock = True
    detector.model.predict.return_value = {"hey_jarvis_v0.1": 0.01}
    detector.redis_client = AsyncMock()
    detector._logger = AsyncMock()
    detector.verifier = verifier
    detector.verify_delay = 0
    return detector


async def _speak(detector, audio):
    for c in _chunks(audio):
        await detector.detect_and_publish(c)
    if detector._verify_task:
        await detector._verify_task


def test_korean_wake_phrase_is_detected_through_speech_to_text() -> None:
    verifier = AsyncMock(return_value="헤이 자비스")
    detector = _detector(verifier)

    asyncio.run(_speak(detector, np.concatenate(
        [np.zeros(16000), _tone(1.0), np.zeros(8000)])))

    verifier.assert_awaited()
    assert detector.redis_client.publish.await_count == 1


def test_name_inside_a_sentence_does_not_wake() -> None:
    # 답이나 대화에 '자비스' 가 들어 있어도 '헤이 자비스' 로 시작하지 않으면 아니다
    verifier = AsyncMock(return_value="자비스는 누구야")
    detector = _detector(verifier)

    asyncio.run(_speak(detector, np.concatenate(
        [np.zeros(16000), _tone(1.0), np.zeros(8000)])))

    assert detector.redis_client.publish.await_count == 0


def test_pause_after_hey_keeps_one_utterance() -> None:
    # '헤이, 자비스' — 쉼표 뒤 0.5초 쉬어도 한 말로 본다(끼어들기 시험 2차: 둘로 쪼개져
    # 둘 다 너무 짧다고 버렸다)
    from services.wake_word.app.detector import UtteranceSpotter

    spotter = UtteranceSpotter()
    audio = np.concatenate(
        [np.zeros(16000), _tone(0.2), np.zeros(8000), _tone(0.6), np.zeros(8000)]
    )

    found = [u for c in _chunks(audio) if (u := spotter.feed(c)) is not None]

    assert len(found) == 1
    assert len(found[0]) / 16000 >= 1.2


def test_fast_wake_phrase_is_spotted() -> None:
    # 빠르게 말한 '헤이 자비스' 는 0.5초다
    from services.wake_word.app.detector import UtteranceSpotter

    spotter = UtteranceSpotter()
    audio = np.concatenate([np.zeros(16000), _tone(0.5), np.zeros(8000)])

    assert any(spotter.feed(c) is not None for c in _chunks(audio))


def test_speech_to_text_writing_cha_still_wakes() -> None:
    # STT 가 '자비스' 를 '차비스' 로 받아 적는다(끼어들기 시험 2차)
    verifier = AsyncMock(return_value="헤이 차비스")
    detector = _detector(verifier)

    asyncio.run(_speak(detector, np.concatenate(
        [np.zeros(16000), _tone(1.0), np.zeros(8000)])))

    assert detector.redis_client.publish.await_count == 1


def test_wake_already_detected_by_model_is_not_detected_again() -> None:
    # 모델이 잡은 'Hey Jarvis' 를 짧은 말 확인이 쿨다운 뒤에 또 잡아 듣기를 다시
    # 시작했다 — 질문이 잘려 받아 적지 못했다(끼어들기 시험 2차)
    verifier = AsyncMock(return_value="Hey Jarvis")
    detector = _detector(verifier)
    detector.cooldown_seconds = 0
    scores = iter([0.01] * 14 + [0.9] + [0.01] * 100)
    detector.model.predict.side_effect = lambda _: {"hey_jarvis_v0.1": next(scores)}

    asyncio.run(_speak(detector, np.concatenate(
        [np.zeros(16000), _tone(1.0), np.zeros(8000)])))

    assert detector.redis_client.publish.await_count == 1


def test_listening_forgets_the_utterance_being_heard() -> None:
    from services.wake_word.app.detector import UtteranceSpotter

    spotter = UtteranceSpotter()
    for c in _chunks(np.concatenate([np.zeros(16000), _tone(0.8)])):
        spotter.feed(c)

    spotter.reset()

    assert all(spotter.feed(c) is None for c in _chunks(np.zeros(8000)))


def test_what_was_said_is_not_logged_when_it_is_not_the_wake_word() -> None:
    # 방 안의 대화가 짧은 말로 잡혀 받아 적은 글이 로그(DB)에 남았다(끼어들기 시험 3차)
    verifier = AsyncMock(return_value="가만있어 움직이지 마")
    detector = _detector(verifier)

    asyncio.run(_speak(detector, np.concatenate(
        [np.zeros(16000), _tone(1.0), np.zeros(8000)])))

    verifier.assert_awaited()
    assert "움직이지" not in str(detector._logger.mock_calls)
