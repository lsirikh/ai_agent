"""
한국어 TTS(MeloTTS) 어댑터 테스트

Kokoro 는 한국어 음성이 없어 답변을 알아들을 수 없었다(되받아 적기 신뢰도 0.09).
TTS_ENGINE=melo 이면 MeloTTS 한국어로 합성하고,
파이프라인 계약(float32 24kHz mono)에 맞게
44.1kHz 출력을 24kHz 로 바꿔 내보낸다.
"""

import numpy as np


class FakeMeloEngine:
    sample_rate = 44100

    def __init__(self) -> None:
        self.calls: list[tuple[str, float]] = []

    def synthesize(self, text: str, voice=None, speed: float = 1.0) -> np.ndarray:
        self.calls.append((text, speed))
        return np.full(44100, 0.25, dtype=np.float32)  # 1초


def test_should_resample_melo_output_to_pipeline_rate() -> None:
    from services.tts.app.melo_adapter import PIPELINE_SAMPLE_RATE, MeloSynthesizer

    synth = MeloSynthesizer(engine=FakeMeloEngine())

    audio = synth.synthesize("안녕하세요.")

    assert PIPELINE_SAMPLE_RATE == 24000
    assert audio.dtype == np.float32
    assert abs(len(audio) - 24000) <= 1
    np.testing.assert_allclose(audio[100:-100], 0.25, atol=1e-4)


def test_should_return_empty_audio_for_blank_text() -> None:
    from services.tts.app.melo_adapter import MeloSynthesizer

    engine = FakeMeloEngine()
    synth = MeloSynthesizer(engine=engine)

    assert len(synth.synthesize("   ")) == 0
    assert engine.calls == []


def test_should_pick_engine_from_setting() -> None:
    from services.tts.app.melo_adapter import MeloSynthesizer, create_voice_synthesizer

    kokoro = object()

    melo = create_voice_synthesizer(
        "melo", kokoro_factory=lambda: kokoro, melo_engine=FakeMeloEngine()
    )
    default = create_voice_synthesizer(
        "kokoro", kokoro_factory=lambda: kokoro, melo_engine=FakeMeloEngine()
    )

    assert isinstance(melo, MeloSynthesizer)
    assert default is kokoro
