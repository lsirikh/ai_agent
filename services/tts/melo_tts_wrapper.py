"""
MeloTTS Korean TTS Wrapper

Windows 환경에서 eunjeon 없이 MeloTTS를 사용할 수 있도록
mecab-python3 + unidic으로 패치하는 래퍼 모듈
"""
import os
from typing import Optional, Tuple

# 전역 변수 (싱글톤 패턴)
_melo_tts = None
_melo_speaker_id = None
_initialized = False


class MeCabWrapper:
    """
    eunjeon.Mecab() 인터페이스를 흉내내는 MeCab 래퍼
    g2pkk가 한국어 음소 변환에 사용하는 형태소 분석기 대체
    """

    def __init__(self):
        import MeCab
        import unidic
        self.tagger = MeCab.Tagger(f'-d "{unidic.DICDIR}"')

    def pos(self, text: str) -> list:
        """
        텍스트를 형태소 분석하여 (표층형, 품사) 튜플 리스트 반환
        eunjeon.Mecab().pos() 인터페이스와 호환
        """
        self.tagger.parse('')  # 버퍼 초기화
        node = self.tagger.parseToNode(text)
        result = []
        while node:
            if node.surface:
                features = node.feature.split(',')
                pos = features[0] if features else 'UNK'
                result.append((node.surface, pos))
            node = node.next
        return result


def _apply_mecab_patch():
    """
    g2pkk의 eunjeon 의존성을 mecab-python3로 대체하는 패치 적용
    Windows에서 eunjeon 빌드가 불가능할 때 사용
    """
    import g2pkk.g2pkk as g2pkk_module
    g2pkk_module.G2p.check_mecab = lambda self: None
    g2pkk_module.G2p.get_mecab = lambda self: MeCabWrapper()


def init_melo_tts(device: Optional[str] = None) -> Tuple[object, int]:
    """
    MeloTTS 초기화 (mecab-python3 패치 적용)

    Args:
        device: 사용할 디바이스 ("cuda:0" 또는 "cpu"). None이면 자동 감지

    Returns:
        (TTS 모델, 스피커 ID) 튜플
    """
    global _melo_tts, _melo_speaker_id, _initialized

    if _initialized:
        return _melo_tts, _melo_speaker_id

    print("🔧 MeloTTS 초기화 중...")

    # mecab 패치 적용
    _apply_mecab_patch()

    # MeloTTS 로드
    from melo.api import TTS
    import torch

    if device is None:
        device = "cuda:0" if torch.cuda.is_available() else "cpu"

    _melo_tts = TTS(language='KR', device=device)
    _melo_speaker_id = _melo_tts.hps.data.spk2id['KR']
    _initialized = True

    print(f"✅ MeloTTS 로드 완료 (device: {device})")
    return _melo_tts, _melo_speaker_id


def synthesize(
    text: str,
    output_path: Optional[str] = None,
    speed: float = 1.0
) -> str:
    """
    텍스트를 음성으로 합성하여 WAV 파일로 저장

    Args:
        text: 합성할 한국어 텍스트
        output_path: 출력 파일 경로. None이면 기본 경로 사용
        speed: 음성 속도 (1.0 = 기본)

    Returns:
        생성된 WAV 파일 경로
    """
    tts, speaker_id = init_melo_tts()

    if output_path is None:
        output_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'output')
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, 'tts_output.wav')

    tts.tts_to_file(text, speaker_id, output_path, speed=speed)
    return output_path


def is_available() -> bool:
    """
    MeloTTS 사용 가능 여부 확인

    Returns:
        True if MeloTTS를 사용할 수 있음
    """
    try:
        import MeCab
        import unidic
        from melo.api import TTS
        return True
    except ImportError:
        return False


# 편의를 위한 별칭
tts = synthesize
