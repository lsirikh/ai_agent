"""
TTS (Text-to-Speech) 모듈

MeloTTS 기반 한국어 음성 합성 서비스
"""
from .melo_tts_wrapper import (
    init_melo_tts,
    synthesize,
    is_available,
    tts,
)

__all__ = [
    'init_melo_tts',
    'synthesize',
    'is_available',
    'tts',
]
