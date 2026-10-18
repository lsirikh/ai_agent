"""
답하는 도중 한국어 '헤이 자비스' (끼어들기 시험 2차 2026-10-18)

답 음성의 에코가 이어져 짧은 말로 끊어 찾을 수 없었다(에코 0.1 에서도 4번 중 1번).
→ 답하는 중에는 소리가 최근 에코(위쪽 90%)보다 뚜렷이 커지면 그 앞 0.2초부터
2.2초를 STT 로 확인한다. 받아 적은 글이 호출어로 시작하면 감지한다 —
쉼표 뒤의 약한 '헤이' 는 에코에 묻혀 빠지므로 이름만으로도 보되,
답 속의 '자비스는…' 으로는 깨지 않게 이름 뒤에 글자가 바로 붙으면 아니다.
STT 는 '자비스' 를 '차비즈'·'샤비스'·'자비수' 로도 적는다.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import numpy as np


def _tone(seconds, amplitude, hz=200):
    t = np.arange(int(16000 * seconds)) / 16000
    return (amplitude * np.sin(2 * np.pi * hz * t)).astype(np.float32)


def _echo(seconds):
    # 말소리처럼 0.3초마다 커졌다 작아지는 에코
    t = np.arange(int(16000 * seconds)) / 16000
    level = 0.03 + 0.02 * np.sin(2 * np.pi * t / 0.6)
    return (level * np.sin(2 * np.pi * 300 * t)).astype(np.float32)


def _chunks(audio):
    return [audio[i:i + 1600] for i in range(0, len(audio), 1600)]


def test_louder_voice_over_echo_opens_a_window_from_its_start() -> None:
    from services.wake_word.app.detector import LoudOnsetWindow

    window = LoudOnsetWindow()
    audio = _echo(6.0)
    audio[48000:64000] += _tone(1.0, 0.15)

    found = []
    for n, chunk in enumerate(_chunks(audio)):
        got = window.feed(chunk)
        if got is not None:
            found.append((n, got))

    starts = [((n + 1) * 1600 - len(got), got) for n, got in found]
    late = [(start, got) for start, got in starts if start > 0]  # 재생 시작은 넘긴다
    assert len(late) == 1
    start, got = late[0]
    assert abs(len(got) / 16000 - 2.2) < 0.05
    assert 48000 - 3200 <= start <= 48000


def test_echo_alone_does_not_open_windows_after_it_settles() -> None:
    from services.wake_word.app.detector import LoudOnsetWindow

    window = LoudOnsetWindow()
    found = [n for n, c in enumerate(_chunks(_echo(8.0))) if window.feed(c) is not None]

    assert all(n <= 30 for n in found)


def _answering_detector(text):
    from services.wake_word.app.detector import WakeWordDetector

    detector = WakeWordDetector()
    detector.model = MagicMock()
    detector._use_mock = True
    detector.model.predict.return_value = {"hey_jarvis_v0.1": 0.01}
    detector.redis_client = AsyncMock()
    detector._logger = AsyncMock()
    detector.verifier = AsyncMock(return_value=text)
    detector.answering = True
    return detector


def _speak_over_echo(detector):
    audio = _echo(7.0)
    audio[48000:64000] += _tone(1.0, 0.15)

    async def run():
        for c in _chunks(audio):
            await detector.detect_and_publish(c)
            await asyncio.sleep(0)
        if detector._verify_task:
            await detector._verify_task

    asyncio.run(run())
    return detector.redis_client.publish.await_count


def test_wake_over_echo_is_detected_while_answering() -> None:
    assert _speak_over_echo(_answering_detector("헤이 차비즈 가을은 한국에")) == 1


def test_name_alone_at_start_wakes_while_answering() -> None:
    assert _speak_over_echo(_answering_detector("자비수 가을은")) == 1


def test_name_inside_the_answer_does_not_wake() -> None:
    assert _speak_over_echo(_answering_detector("자비스는 제 이름이에요")) == 0


def test_speech_to_text_spellings_of_the_name() -> None:
    from services.wake_word.app.detector import WAKE_START

    for text in ["헤이 샤비스", "헤이 차비즈", "헤이, 자비수.", "Hey Jarvis"]:
        assert WAKE_START.search(text), text
    assert not WAKE_START.search("헤이 서비스 센터")


def test_name_later_in_the_window_wakes_while_answering() -> None:
    # 에코로 먼저 열린 창 뒤쪽에 호출어가 들어간다(끼어들기 시험 3차)
    detector = _answering_detector("10월 중순으로 자비스 한국")
    assert _speak_over_echo(detector) == 1


def test_name_with_a_particle_does_not_wake_while_answering() -> None:
    assert _speak_over_echo(_answering_detector("저는 자비스입니다")) == 0
