"""
MeloTTS 화자 ID 회귀 테스트

실제 MeloTTS 의 hps.data.spk2id 는 dict 가 아니라 HParams(인덱싱만 되고 .get 이 없음)라,
엔진의 .get() 호출이 매번 예외 → 빈 음성이 됐다(컨테이너에서 확인).
"""

import wave

import numpy as np


class HParamsLike:
    """melo.utils.HParams 처럼 [] 로만 꺼낼 수 있는 화자 표"""

    def __init__(self, **items: int) -> None:
        self._items = items

    def __getitem__(self, key: str) -> int:
        return self._items[key]


class FakeMeloModel:
    def __init__(self) -> None:
        self.speaker_ids: list[int] = []

    def tts_to_file(
        self, text: str, speaker_id: int, output_path: str, speed: float = 1.0
    ) -> None:
        self.speaker_ids.append(speaker_id)
        with wave.open(output_path, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(44100)
            w.writeframes((np.full(4410, 0.5) * 32767).astype(np.int16).tobytes())


def test_should_synthesize_with_hparams_speaker_table() -> None:
    from services.tts.app.engines.melo_engine import MeloTTSEngine

    engine = MeloTTSEngine()
    model = FakeMeloModel()
    engine._model = model
    engine._speaker_ids = HParamsLike(KR=0)
    engine._initialized = True

    audio = engine.synthesize("안녕하세요.")

    assert model.speaker_ids == [0]
    assert len(audio) == 4410
    np.testing.assert_allclose(audio, 0.5, atol=1e-3)
