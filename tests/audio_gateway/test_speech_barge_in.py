"""
말소리로 끼어들기 (사용자 요청 2026-10-17: '헤이 자비스' 없이 내가 말하면 끊어 줘)

- 기존 끼어들기는 TTS '합성' 시작~끝(문장당 약 0.2초)만 재생 중으로 봐
  사실상 꺼져 있었다.
  앱으로 보낸 음성 길이로 실제 재생 구간을 계산한다.
- 재생 중 마이크에는 EdgeVoice 자신의 목소리(에코)도 들어온다. 그 시각 재생 크기 대비
  평소 에코 비율보다 뚜렷이 큰 사람 목소리가 0.3초 이어질 때만 끼어들기로 본다.
"""

import os
import sys

import numpy as np

sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "../../services/audio_gateway")
)


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


def _tone(seconds, amplitude, rate=24000):
    t = np.arange(int(seconds * rate)) / rate
    return (amplitude * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


def test_tracker_knows_real_playback_time_and_level() -> None:
    from app.speech_barge_in import PlaybackTracker

    clock = Clock()
    tracker = PlaybackTracker(clock=clock)
    tracker.add(_tone(2.0, 0.3))  # 2초 분량을 보냄

    clock.now += 1.0
    assert tracker.playing()
    assert 0.15 < tracker.level() < 0.3
    clock.now += 3.0
    assert not tracker.playing()


def test_tracker_keeps_current_level_when_long_answer_is_queued() -> None:
    # 실측: 긴 답은 합성이 재생보다 빨라 1분 넘게 쌓였고, 개수 한도(600 조각)
    # 때문에 지금 재생 중인 앞 조각이 지워져 재생 크기가 0 으로 보였다
    from app.speech_barge_in import PlaybackTracker

    clock = Clock()
    tracker = PlaybackTracker(clock=clock)
    tracker.add(_tone(90.0, 0.3))

    clock.now += 1.0
    assert tracker.level() > 0.15


def test_echo_alone_never_interrupts() -> None:
    from app.speech_barge_in import SpeechBargeIn

    barge = SpeechBargeIn()
    hits = [
        barge.feed(mic_rms=0.4 * 0.2, vad_prob=0.9, far_level=0.2) for _ in range(40)
    ]

    assert not any(hits)


def test_user_voice_over_echo_interrupts_after_300ms() -> None:
    from app.speech_barge_in import SpeechBargeIn

    barge = SpeechBargeIn()
    for _ in range(20):  # 에코만 — 에코 비율을 익힌다
        barge.feed(mic_rms=0.08, vad_prob=0.9, far_level=0.2)

    hits = [barge.feed(mic_rms=0.4, vad_prob=0.9, far_level=0.2) for _ in range(3)]

    assert hits == [False, False, True]


def test_loud_noise_without_voice_does_not_interrupt() -> None:
    from app.speech_barge_in import SpeechBargeIn

    barge = SpeechBargeIn()
    hits = [barge.feed(mic_rms=0.5, vad_prob=0.2, far_level=0.2) for _ in range(10)]

    assert not any(hits)


def test_voice_in_a_pause_between_sentences_interrupts() -> None:
    # 문장 사이(재생 소리가 거의 없음)에 말하면 에코와 헷갈릴 일이 없다
    from app.speech_barge_in import SpeechBargeIn

    barge = SpeechBargeIn()
    hits = [barge.feed(mic_rms=0.1, vad_prob=0.9, far_level=0.0) for _ in range(3)]

    assert hits[-1] is True


def test_gateway_interrupts_when_user_talks_over_the_answer() -> None:
    import asyncio
    from unittest.mock import AsyncMock, MagicMock, patch

    from app import main
    from app.speech_barge_in import EchoDelay, PlaybackTracker, SpeechBargeIn
    from fastapi.testclient import TestClient

    redis = AsyncMock()
    vad = MagicMock()
    vad.detect.return_value = {"is_speech": True, "probability": 0.95}
    tracker = PlaybackTracker()
    loud = (0.5 * 32767 * np.sin(np.arange(1600) / 3)).astype(np.int16).tobytes()

    with (
        patch.object(main, "redis_client", redis),
        patch.object(main, "vad", vad),
        patch.object(main, "reset_session", AsyncMock()),
        patch.object(main, "playback_tracker", tracker),
        patch.object(main, "speech_barge", SpeechBargeIn()),
        patch.object(main, "echo_delay", EchoDelay()),
        patch.object(main, "on_speech_started", AsyncMock()),
    ):
        tracker.add(_tone(5.0, 0.05))  # 답을 5초째 재생 중
        with TestClient(main.app).websocket_connect("/ws/audio") as ws:
            for _ in range(4):
                ws.send_bytes(loud)
                ws.receive_json()
        listening = main._listening_mode
    asyncio.run(main.reset_session())

    channels = [c.args[0] for c in redis.publish.await_args_list]
    assert "edgevoice:barge_in:detected" in channels
    assert listening is True


def test_answer_audio_sent_to_the_app_is_tracked() -> None:
    import asyncio
    from unittest.mock import AsyncMock, patch

    from app import main
    from app.speech_barge_in import PlaybackTracker

    tracker = PlaybackTracker()
    client = AsyncMock()
    main.register_playback_client(client)
    try:
        with patch.object(main, "playback_tracker", tracker):
            asyncio.run(main.forward_tts_audio(_tone(1.0, 0.2).tobytes()))
    finally:
        main.unregister_playback_client(client)

    assert tracker.playing() and tracker.level() > 0.1


def test_gateway_does_not_interrupt_on_its_own_echo() -> None:
    # 실측(E2E): 에코만 들릴 때 예전 에너지 감지기(문턱 0.01)가 끼어들기를 냈다
    import asyncio
    from unittest.mock import AsyncMock, MagicMock, patch

    from app import main
    from app.barge_in import BargeInDetector, PlaybackState
    from app.speech_barge_in import EchoDelay, PlaybackTracker, SpeechBargeIn
    from fastapi.testclient import TestClient

    redis = AsyncMock()
    vad = MagicMock()
    vad.detect.side_effect = lambda _: {
        "is_speech": True, "probability": 0.95, "speech_started": True
    }
    tracker = PlaybackTracker()
    detector = BargeInDetector(vad=vad)
    detector.set_playback_state(PlaybackState.PLAYING)
    detector.redis_client = redis
    # 재생 크기(약 0.35)의 0.3배로 되돌아온 에코
    echo = (0.3 * 0.5 * 32767 * np.sin(np.arange(1600) / 3)).astype(np.int16)

    with (
        patch.object(main, "redis_client", redis),
        patch.object(main, "vad", vad),
        patch.object(main, "reset_session", AsyncMock()),
        patch.object(main, "playback_tracker", tracker),
        patch.object(main, "speech_barge", SpeechBargeIn()),
        patch.object(main, "echo_delay", EchoDelay()),
        patch.object(main, "barge_in_detector", detector),
        patch.object(main, "on_speech_started", AsyncMock()),
    ):
        tracker.add(_tone(5.0, 0.5))
        with TestClient(main.app).websocket_connect("/ws/audio") as ws:
            for _ in range(10):
                ws.send_bytes(echo.tobytes())
                ws.receive_json()
    asyncio.run(main.reset_session())

    channels = [c.args[0] for c in redis.publish.await_args_list]
    assert "edgevoice:barge_in:detected" not in channels


def _speech_like(seconds, rate=24000, seed=0):
    """말처럼 크기가 오르내리는 재생 음성(0.3초 단위로 크기가 바뀐다)."""
    rng = np.random.default_rng(seed)
    t = np.arange(int(seconds * rate)) / rate
    levels = rng.uniform(0.0, 0.5, int(seconds / 0.3) + 1)
    envelope = levels[(t / 0.3).astype(int)]
    return (envelope * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


def _play(seconds, delay, gain, voice_from=None, voice_rms=0.0, seed=0):
    """재생을 시작하고 100ms 마다 마이크 조각을 넣는다. 끼어든 시각(초)을 돌려준다."""
    from app.speech_barge_in import EchoDelay, PlaybackTracker, SpeechBargeIn

    clock = Clock()
    start = clock.now
    tracker = PlaybackTracker(clock=clock)
    audio = _speech_like(seconds, seed=seed)
    tracker.add(audio)
    echo_delay, barge = EchoDelay(), SpeechBargeIn()
    step = 2400
    for i in range(int(seconds * 10)):
        clock.now = start + (i + 1) * 0.1
        j = i - int(round(delay * 10))
        piece = audio[j * step : (j + 1) * step] if j >= 0 else np.zeros(step)
        mic = gain * float(np.sqrt(np.mean(piece**2)))
        if voice_from is not None and clock.now - start > voice_from:
            mic = float(np.hypot(mic, voice_rms))
        far = echo_delay.far_level(tracker)
        if echo_delay.observe(mic, tracker):
            barge.forget_echo(echo_delay.recent_ratios(tracker, barge.min_far))
        if barge.feed(mic, 0.9, far, learn=echo_delay.known):
            return round(clock.now - start, 1), echo_delay
    return None, echo_delay


def test_tracker_level_around_a_moment() -> None:
    from app.speech_barge_in import PlaybackTracker

    clock = Clock()
    tracker = PlaybackTracker(clock=clock)
    tracker.add(np.concatenate([_tone(1.0, 0.0), _tone(1.0, 0.4)]))

    assert tracker.around(clock.now + 0.5, 0.1) == 0.0
    assert tracker.around(clock.now + 1.5, 0.1) > 0.2


def test_echo_delay_is_learned_from_the_loudness_pattern() -> None:
    _, echo_delay = _play(10.0, delay=0.5, gain=0.3)

    assert echo_delay.known
    assert abs(echo_delay.delay - 0.5) <= 0.1


def test_late_loud_echo_never_interrupts() -> None:
    # 원격 데스크톱처럼 에코가 1초 늦고 크게(0.8) 들어와도 끊지 않는다
    for seed in range(3):
        hit, _ = _play(30.0, delay=1.0, gain=0.8, seed=seed)
        assert hit is None


def test_user_voice_over_echo_interrupts_once_delay_is_known() -> None:
    hit, _ = _play(30.0, delay=0.3, gain=0.3, voice_from=15.0, voice_rms=0.25)

    assert hit is not None and 15.0 < hit <= 15.6


def test_barge_in_status_shows_learned_echo() -> None:
    # 실제 스피커·마이크에서 왜 끊었는지/못 끊었는지 볼 수 있게
    from unittest.mock import patch

    from app import main
    from app.speech_barge_in import EchoDelay
    from fastapi.testclient import TestClient

    echo = EchoDelay()
    echo.delay = 0.3
    with patch.object(main, "echo_delay", echo):
        data = TestClient(main.app).get("/barge-in/status").json()

    assert data["speech"]["echo_delay"] == 0.3
    assert "echo_ratio" in data["speech"]


def test_user_voice_right_after_delay_is_learned_interrupts() -> None:
    # E2E 실측: 시차를 익힌 직후 비율을 처음부터 다시 익히는 동안 사용자 말이
    # 에코로 익혀져(0.28 → 0.73) 끝내 끊지 못했다
    hit, echo_delay = _play(30.0, delay=0.3, gain=0.3, voice_from=3.3, voice_rms=0.25)

    assert echo_delay.known
    assert hit is not None and 3.3 < hit <= 3.9


def test_voice_interrupts_when_there_is_no_echo_at_all() -> None:
    # 끼어들기 시험(2026-10-18): 에코가 전혀 없으면(헤드셋) 시차를 익힐 수 없어 기본
    # 비율(재생 크기의 1.8배)과 견주다 보니 보통 목소리로는 끝내 끊지 못했다
    hit, _ = _play(20.0, delay=0.0, gain=0.0, voice_from=2.0, voice_rms=0.08)

    assert hit is not None and 2.0 < hit <= 2.6


def test_first_answer_can_be_interrupted_after_two_seconds() -> None:
    # 끼어들기 시험: 처음 답에서 2초쯤 끼어들면 시차를 아직 못 익혀(3초 필요) 끊지 못했다
    hit, _ = _play(20.0, delay=0.3, gain=0.2, voice_from=2.2, voice_rms=0.2)

    assert hit is not None and 2.2 < hit <= 3.2


def test_loud_late_echo_still_never_interrupts_with_faster_learning() -> None:
    for seed in range(4):
        for delay in (0.0, 0.6, 1.0):
            hit, _ = _play(30.0, delay=delay, gain=0.8, seed=seed)
            assert hit is None, (seed, delay)
