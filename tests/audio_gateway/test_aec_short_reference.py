"""
AEC 회귀 테스트: 재생 참조가 마이크 청크보다 짧을 때

TTS 마지막 청크처럼 참조가 짧으면 필터 입력 창이 filter_length 보다 짧아져
np.dot 이 "shapes (256,) and (255,) not aligned" 로 실패했고,
그 뒤 모든 /ws/audio 연결이 첫 청크에서 끊겼다.
"""

import numpy as np


def test_should_process_mic_chunk_when_reference_is_shorter_than_chunk() -> None:
    from services.audio_gateway.app.aec import AcousticEchoCanceller

    aec = AcousticEchoCanceller(filter_length=256)
    aec.set_playback_reference(np.full(1000, 0.1, dtype=np.float32))
    mic = np.random.default_rng(0).uniform(-0.2, 0.2, 1600).astype(np.float32)

    out = aec.process(mic)

    assert out.shape == mic.shape
    assert np.all(np.isfinite(out))


def test_should_process_chunk_when_reference_is_shorter_than_filter() -> None:
    from services.audio_gateway.app.aec import AcousticEchoCanceller

    aec = AcousticEchoCanceller(filter_length=256)
    aec.set_playback_reference(np.full(100, 0.1, dtype=np.float32))
    mic = np.zeros(1600, dtype=np.float32)

    out = aec.process(mic)

    assert out.shape == mic.shape
