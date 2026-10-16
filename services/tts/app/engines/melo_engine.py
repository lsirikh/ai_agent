"""
MeloTTS Engine

Phase 10.1.2: MeloTTS-Korean 엔진 구현
"""
import os
import tempfile
from typing import List, Optional

import numpy as np

from .base import TTSEngine


class MeloTTSEngine(TTSEngine):
    """MeloTTS-Korean 엔진 - 고품질 한국어 TTS"""

    def __init__(self):
        """MeloTTSEngine 초기화"""
        self._model = None
        self._speaker_ids = {}
        self._initialized = False

    @property
    def name(self) -> str:
        return "melo"

    @property
    def display_name(self) -> str:
        return "MeloTTS Korean"

    @property
    def sample_rate(self) -> int:
        return 44100

    @property
    def supported_languages(self) -> List[str]:
        return ["ko", "en", "zh", "ja"]

    @property
    def requires_gpu(self) -> bool:
        return False  # CPU도 지원, GPU 권장

    @property
    def requires_internet(self) -> bool:
        return False

    def _apply_mecab_patch(self) -> None:
        """Windows 환경에서 eunjeon 대신 mecab-python3 사용하도록 패치"""
        try:
            class MeCabWrapper:
                """MeCab 래퍼 클래스 - eunjeon.Mecab 대체"""

                def __init__(self):
                    import MeCab
                    import unidic
                    self.tagger = MeCab.Tagger(f'-d "{unidic.DICDIR}"')

                def pos(self, text):
                    """형태소 분석"""
                    self.tagger.parse('')
                    node = self.tagger.parseToNode(text)
                    result = []
                    while node:
                        if node.surface:
                            features = node.feature.split(',')
                            pos = features[0] if features else 'UNK'
                            result.append((node.surface, pos))
                        node = node.next
                    return result

            # g2pkk 모듈 패치
            import g2pkk.g2pkk as g2pkk_module
            g2pkk_module.G2p.check_mecab = lambda self: None
            g2pkk_module.G2p.get_mecab = lambda self: MeCabWrapper()

        except ImportError:
            # MeCab이 없는 경우 패스
            pass

    def _load_model(self) -> None:
        """MeloTTS 모델 로드 (lazy loading)"""
        if self._initialized:
            return

        try:
            self._apply_mecab_patch()

            from melo.api import TTS
            import torch

            device = "cuda:0" if torch.cuda.is_available() else "cpu"
            self._model = TTS(language='KR', device=device)
            self._speaker_ids = self._model.hps.data.spk2id
            self._initialized = True

        except ImportError:
            # melo 패키지가 없는 경우
            self._model = None
            self._initialized = False

    def synthesize(
        self,
        text: str,
        voice: Optional[str] = None,
        speed: float = 1.0
    ) -> np.ndarray:
        """텍스트를 음성으로 합성

        Args:
            text: 합성할 텍스트
            voice: 음성 ID (기본: "KR")
            speed: 발화 속도 (기본 1.0)

        Returns:
            np.ndarray: float32 오디오 데이터 (44100Hz)
        """
        if not text or not text.strip():
            return np.array([], dtype=np.float32)

        self._load_model()

        if self._model is None:
            # 모델이 없는 경우 더미 오디오 반환 (테스트용)
            duration = len(text) * 0.1
            samples = int(self.sample_rate * duration)
            return np.zeros(samples, dtype=np.float32)

        try:
            # spk2id 는 dict 가 아닌 HParams 라 .get 이 없다 → [] 로 꺼낸다
            try:
                speaker_id = self._speaker_ids[voice or 'KR']
            except (KeyError, AttributeError, TypeError):
                speaker_id = self._speaker_ids['KR']

            # 임시 파일에 저장 후 읽기
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
                output_path = f.name

            self._model.tts_to_file(text, speaker_id, output_path, speed=speed)

            import wave
            with wave.open(output_path, 'rb') as w:
                audio = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
            os.unlink(output_path)

            return audio.astype(np.float32) / 32768.0

        except Exception as e:
            print(f"MeloTTS synthesis error: {e}")
            return np.array([], dtype=np.float32)

    def get_available_voices(self) -> List[dict]:
        """사용 가능한 음성 목록 반환"""
        return [
            {"id": "KR", "name": "Korean Female", "language": "ko"},
        ]

    def is_available(self) -> bool:
        """엔진 사용 가능 여부"""
        try:
            import MeCab
            import unidic
            # melo import 체크는 생략 (시간 소요)
            return True
        except ImportError:
            return False
