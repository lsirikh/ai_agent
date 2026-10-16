"""
TTS Synthesizer Tests

Phase 1.3: Kokoro TTS 합성기 테스트
TDD 방식으로 진행 - 먼저 테스트 작성 후 구현
"""
import os
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

# Kokoro TTS 가용성 체크
def is_kokoro_available() -> bool:
    """Kokoro TTS 모델이 사용 가능한지 확인"""
    try:
        import torch
        return torch.cuda.is_available()
    except ImportError:
        return False


KOKORO_AVAILABLE = is_kokoro_available()


# ==========================================
# Unit Tests (Mock 기반 - Kokoro 없이 실행)
# ==========================================

class TestKokoroTTSInitialization:
    """KokoroTTS 초기화 테스트"""

    def test_kokoro_model_loads_with_default_config(self):
        """기본 설정으로 KokoroTTS가 초기화되어야 한다"""
        from services.tts.app.synthesizer import KokoroTTS

        with patch.object(KokoroTTS, "_load_model", return_value=MagicMock()):
            tts = KokoroTTS()

            assert tts is not None
            assert tts.sample_rate == 24000
            assert tts.voice is not None

    def test_kokoro_model_loads_with_custom_config(self):
        """커스텀 설정으로 KokoroTTS가 초기화되어야 한다"""
        from services.tts.app.synthesizer import KokoroTTS

        with patch.object(KokoroTTS, "_load_model", return_value=MagicMock()):
            tts = KokoroTTS(
                voice="af_bella",
                speed=1.2
            )

            assert tts.voice == "af_bella"
            assert tts.speed == 1.2

    def test_kokoro_has_environment_configs(self):
        """KokoroTTS에 환경별 설정이 있어야 한다"""
        from services.tts.app.synthesizer import KokoroTTS

        assert hasattr(KokoroTTS, "MODEL_CONFIGS")
        configs = KokoroTTS.MODEL_CONFIGS

        assert "development" in configs
        assert "production_jetson" in configs


class TestKokoroTTSSynthesize:
    """KokoroTTS 음성 합성 테스트"""

    def test_synthesize_korean_text_returns_audio(self):
        """한국어 텍스트를 음성으로 변환해야 한다"""
        from services.tts.app.synthesizer import KokoroTTS

        # Mock 오디오 데이터 (24kHz, 1초)
        mock_audio = np.random.randn(24000).astype(np.float32)

        with patch.object(KokoroTTS, "_load_model", return_value=MagicMock()):
            tts = KokoroTTS()

            with patch.object(tts, "_synthesize_internal", return_value=mock_audio):
                result = tts.synthesize("안녕하세요, 반갑습니다.")

                assert isinstance(result, np.ndarray)
                assert len(result) > 0

    def test_synthesize_returns_correct_audio_format(self):
        """합성된 오디오는 올바른 포맷이어야 한다 (24kHz, float32 또는 int16)"""
        from services.tts.app.synthesizer import KokoroTTS

        # Mock 오디오 데이터
        mock_audio = np.random.randn(24000).astype(np.float32)

        with patch.object(KokoroTTS, "_load_model", return_value=MagicMock()):
            tts = KokoroTTS()

            with patch.object(tts, "_synthesize_internal", return_value=mock_audio):
                result = tts.synthesize("테스트 텍스트")

                # float32 또는 int16 포맷이어야 함
                assert result.dtype in [np.float32, np.int16]

    def test_synthesize_empty_text_returns_empty_audio(self):
        """빈 텍스트는 빈 오디오를 반환해야 한다"""
        from services.tts.app.synthesizer import KokoroTTS

        with patch.object(KokoroTTS, "_load_model", return_value=MagicMock()):
            tts = KokoroTTS()

            result = tts.synthesize("")

            assert isinstance(result, np.ndarray)
            assert len(result) == 0

    def test_synthesize_with_different_speeds(self):
        """다양한 속도로 음성을 합성할 수 있어야 한다"""
        from services.tts.app.synthesizer import KokoroTTS

        mock_audio = np.random.randn(24000).astype(np.float32)

        with patch.object(KokoroTTS, "_load_model", return_value=MagicMock()):
            tts = KokoroTTS(speed=1.0)

            with patch.object(tts, "_synthesize_internal", return_value=mock_audio):
                # 기본 속도
                result_normal = tts.synthesize("테스트")

                # 빠른 속도
                tts.speed = 1.5
                result_fast = tts.synthesize("테스트")

                # 속도 설정이 적용되어야 함
                assert tts.speed == 1.5


class TestKokoroTTSStreaming:
    """KokoroTTS 스트리밍 합성 테스트"""

    @pytest.mark.asyncio
    async def test_synthesize_stream_yields_audio_chunks(self):
        """스트리밍 합성은 오디오 청크를 순차적으로 yield해야 한다"""
        from services.tts.app.synthesizer import KokoroTTS

        with patch.object(KokoroTTS, "_load_model", return_value=MagicMock()):
            tts = KokoroTTS()

            # Mock 스트리밍 응답
            async def mock_stream():
                for _ in range(3):
                    yield np.random.randn(4800).astype(np.float32)  # 0.2초 청크

            with patch.object(tts, "_synthesize_stream_internal", return_value=mock_stream()):
                chunks = []
                async for chunk in tts.synthesize_stream("안녕하세요"):
                    chunks.append(chunk)

                assert len(chunks) == 3
                for chunk in chunks:
                    assert isinstance(chunk, np.ndarray)

    @pytest.mark.asyncio
    async def test_synthesize_stream_handles_long_text(self):
        """긴 텍스트도 스트리밍으로 처리할 수 있어야 한다"""
        from services.tts.app.synthesizer import KokoroTTS

        with patch.object(KokoroTTS, "_load_model", return_value=MagicMock()):
            tts = KokoroTTS()

            long_text = "이것은 매우 긴 문장입니다. " * 10

            async def mock_stream():
                for _ in range(10):
                    yield np.random.randn(4800).astype(np.float32)

            with patch.object(tts, "_synthesize_stream_internal", return_value=mock_stream()):
                chunks = []
                async for chunk in tts.synthesize_stream(long_text):
                    chunks.append(chunk)

                assert len(chunks) == 10


class TestKokoroTTSVoiceSelection:
    """KokoroTTS 음성 선택 테스트"""

    def test_voice_selection_default(self):
        """기본 음성이 설정되어야 한다"""
        from services.tts.app.synthesizer import KokoroTTS

        with patch.object(KokoroTTS, "_load_model", return_value=MagicMock()):
            tts = KokoroTTS()

            assert tts.voice is not None
            assert isinstance(tts.voice, str)

    def test_voice_selection_custom(self):
        """커스텀 음성을 선택할 수 있어야 한다"""
        from services.tts.app.synthesizer import KokoroTTS

        with patch.object(KokoroTTS, "_load_model", return_value=MagicMock()):
            tts = KokoroTTS(voice="af_bella")

            assert tts.voice == "af_bella"

    def test_get_available_voices(self):
        """사용 가능한 음성 목록을 조회할 수 있어야 한다"""
        from services.tts.app.synthesizer import KokoroTTS

        with patch.object(KokoroTTS, "_load_model", return_value=MagicMock()):
            tts = KokoroTTS()

            voices = tts.get_available_voices()

            assert isinstance(voices, list)
            assert len(voices) > 0

    def test_set_voice(self):
        """음성을 변경할 수 있어야 한다"""
        from services.tts.app.synthesizer import KokoroTTS

        with patch.object(KokoroTTS, "_load_model", return_value=MagicMock()):
            tts = KokoroTTS(voice="af_default")

            tts.set_voice("af_bella")

            assert tts.voice == "af_bella"


class TestKokoroTTSAudioConversion:
    """KokoroTTS 오디오 변환 테스트"""

    def test_to_int16_conversion(self):
        """float32 오디오를 int16으로 변환할 수 있어야 한다"""
        from services.tts.app.synthesizer import KokoroTTS

        with patch.object(KokoroTTS, "_load_model", return_value=MagicMock()):
            tts = KokoroTTS()

            # float32 오디오 (-1.0 ~ 1.0)
            float_audio = np.array([0.0, 0.5, -0.5, 1.0, -1.0], dtype=np.float32)

            int16_audio = tts.to_int16(float_audio)

            assert int16_audio.dtype == np.int16
            assert len(int16_audio) == len(float_audio)

    def test_to_wav_bytes(self):
        """오디오를 WAV 바이트로 변환할 수 있어야 한다"""
        from services.tts.app.synthesizer import KokoroTTS

        with patch.object(KokoroTTS, "_load_model", return_value=MagicMock()):
            tts = KokoroTTS()

            audio = np.random.randn(24000).astype(np.float32)

            wav_bytes = tts.to_wav_bytes(audio)

            assert isinstance(wav_bytes, bytes)
            assert len(wav_bytes) > 0
            # WAV 헤더 확인
            assert wav_bytes[:4] == b"RIFF"


# ==========================================
# Integration Tests (Kokoro 모델 필요)
# ==========================================

@pytest.mark.skipif(not KOKORO_AVAILABLE, reason="Kokoro TTS not available (requires GPU)")
class TestKokoroTTSIntegration:
    """Kokoro TTS 통합 테스트"""

    def test_real_synthesize_korean(self):
        """실제 Kokoro 모델로 한국어 음성 합성"""
        from services.tts.app.synthesizer import KokoroTTS

        tts = KokoroTTS(environment="development")

        result = tts.synthesize("안녕하세요, 테스트입니다.")

        assert isinstance(result, np.ndarray)
        assert len(result) > 0
        assert result.dtype in [np.float32, np.int16]

    @pytest.mark.asyncio
    async def test_real_synthesize_stream(self):
        """실제 Kokoro 모델로 스트리밍 합성"""
        from services.tts.app.synthesizer import KokoroTTS

        tts = KokoroTTS(environment="development")

        chunks = []
        async for chunk in tts.synthesize_stream("스트리밍 테스트입니다."):
            chunks.append(chunk)
            if len(chunks) > 10:  # 무한 루프 방지
                break

        assert len(chunks) > 0
