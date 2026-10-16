"""
Test STT Transcriber

TDD Phase 1.1: Faster-Whisper 기반 STT 서비스 테스트
"""
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

# 서비스 모듈 경로 추가
SERVICE_PATH = Path(__file__).parent.parent.parent / "services" / "stt"
sys.path.insert(0, str(SERVICE_PATH))


def is_gpu_available() -> bool:
    """CUDA GPU 사용 가능 여부 확인"""
    try:
        import torch
        return torch.cuda.is_available()
    except ImportError:
        return False


def is_whisper_available() -> bool:
    """faster-whisper 라이브러리 설치 여부 확인"""
    try:
        import faster_whisper
        return True
    except ImportError:
        return False


GPU_AVAILABLE = is_gpu_available()
WHISPER_AVAILABLE = is_whisper_available()


class TestTranscriberUnit:
    """Transcriber 유닛 테스트 (모킹 사용)"""

    def test_transcriber_class_exists(self):
        """StreamingTranscriber 클래스가 존재해야 한다"""
        from app.transcriber import StreamingTranscriber
        assert StreamingTranscriber is not None

    def test_transcriber_has_model_configs(self):
        """StreamingTranscriber에 MODEL_CONFIGS가 정의되어야 한다"""
        from app.transcriber import StreamingTranscriber
        assert hasattr(StreamingTranscriber, "MODEL_CONFIGS")
        assert "development" in StreamingTranscriber.MODEL_CONFIGS
        assert "production_jetson" in StreamingTranscriber.MODEL_CONFIGS

    def test_transcriber_development_config(self):
        """개발 환경 설정이 올바른 값을 가져야 한다"""
        from app.transcriber import StreamingTranscriber
        dev_config = StreamingTranscriber.MODEL_CONFIGS["development"]
        # GPU 메모리 절약을 위해 small 모델 사용
        assert dev_config["model_size"] == "small"
        assert dev_config["compute_type"] == "int8"
        assert dev_config["device"] == "cpu"

    def test_transcriber_production_config(self):
        """프로덕션(Jetson) 환경 설정이 올바른 값을 가져야 한다"""
        from app.transcriber import StreamingTranscriber
        prod_config = StreamingTranscriber.MODEL_CONFIGS["production_jetson"]
        assert prod_config["model_size"] == "small"
        assert prod_config["compute_type"] == "int8"

    @patch("app.transcriber.WhisperModel")
    def test_whisper_model_loads(self, mock_whisper):
        """Whisper 모델이 올바른 파라미터로 로드되어야 한다"""
        from app.transcriber import StreamingTranscriber

        mock_model = MagicMock()
        mock_whisper.return_value = mock_model

        transcriber = StreamingTranscriber(environment="development")

        # GPU 메모리 절약을 위해 small 모델을 CPU 모드로 사용
        mock_whisper.assert_called_once_with(
            "small",
            device="cpu",
            compute_type="int8"
        )
        assert transcriber.model == mock_model

    @patch("app.transcriber.WhisperModel")
    def test_transcribe_returns_result(self, mock_whisper):
        """transcribe 메서드가 결과를 반환해야 한다"""
        from app.transcriber import StreamingTranscriber

        # Mock 설정
        mock_segment = MagicMock()
        mock_segment.text = "안녕하세요"
        mock_segment.avg_logprob = -0.3
        mock_segment.start = 0.0
        mock_segment.end = 1.5

        mock_info = MagicMock()
        mock_info.language = "ko"
        mock_info.language_probability = 0.95

        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([mock_segment], mock_info)
        mock_whisper.return_value = mock_model

        transcriber = StreamingTranscriber(environment="development")

        # 테스트용 오디오 (1초, 16kHz)
        audio = np.zeros(16000, dtype=np.float32)
        result = transcriber.transcribe(audio, language="ko")

        assert result["text"] == "안녕하세요"
        assert "confidence" in result
        assert result["language"] == "ko"

    @patch("app.transcriber.WhisperModel")
    def test_transcribe_returns_confidence(self, mock_whisper):
        """transcribe 결과에 신뢰도 점수가 포함되어야 한다"""
        from app.transcriber import StreamingTranscriber

        mock_segment = MagicMock()
        mock_segment.text = "테스트"
        mock_segment.avg_logprob = -0.5  # log probability

        mock_info = MagicMock()
        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([mock_segment], mock_info)
        mock_whisper.return_value = mock_model

        transcriber = StreamingTranscriber(environment="development")
        audio = np.zeros(16000, dtype=np.float32)
        result = transcriber.transcribe(audio)

        assert "confidence" in result
        assert 0.0 <= result["confidence"] <= 1.0

    @patch("app.transcriber.WhisperModel")
    def test_transcribe_korean_audio(self, mock_whisper):
        """한국어 오디오를 전사할 수 있어야 한다"""
        from app.transcriber import StreamingTranscriber

        mock_segment = MagicMock()
        mock_segment.text = "안녕하세요 반갑습니다"
        mock_segment.avg_logprob = -0.2

        mock_info = MagicMock()
        mock_info.language = "ko"

        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([mock_segment], mock_info)
        mock_whisper.return_value = mock_model

        transcriber = StreamingTranscriber(environment="development")
        audio = np.zeros(16000, dtype=np.float32)
        result = transcriber.transcribe(audio, language="ko")

        assert "안녕" in result["text"]
        mock_model.transcribe.assert_called_once()
        call_kwargs = mock_model.transcribe.call_args[1]
        assert call_kwargs.get("language") == "ko"

    @patch("app.transcriber.WhisperModel")
    def test_transcribe_with_vad_filter(self, mock_whisper):
        """VAD 필터가 적용되어야 한다"""
        from app.transcriber import StreamingTranscriber

        mock_segment = MagicMock()
        mock_segment.text = "테스트"
        mock_segment.avg_logprob = -0.3

        mock_info = MagicMock()
        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([mock_segment], mock_info)
        mock_whisper.return_value = mock_model

        transcriber = StreamingTranscriber(environment="development")
        audio = np.zeros(16000, dtype=np.float32)
        transcriber.transcribe(audio)

        call_kwargs = mock_model.transcribe.call_args[1]
        assert call_kwargs.get("vad_filter") is True


@pytest.mark.skipif(not WHISPER_AVAILABLE, reason="faster-whisper not installed")
@pytest.mark.skipif(not GPU_AVAILABLE, reason="CUDA GPU not available")
class TestTranscriberIntegration:
    """Transcriber 통합 테스트 (실제 모델 사용)"""

    @pytest.fixture(scope="class")
    def transcriber(self):
        """테스트용 Transcriber 인스턴스"""
        from app.transcriber import StreamingTranscriber
        # 통합 테스트는 작은 모델 사용
        return StreamingTranscriber(environment="production_jetson")

    def test_real_model_loads(self, transcriber):
        """실제 Whisper 모델이 로드되어야 한다"""
        assert transcriber.model is not None

    def test_real_transcribe_silence(self, transcriber):
        """무음 오디오를 처리할 수 있어야 한다"""
        # 1초 무음
        audio = np.zeros(16000, dtype=np.float32)
        result = transcriber.transcribe(audio)
        # 무음은 빈 텍스트 또는 짧은 결과
        assert isinstance(result["text"], str)

    def test_real_transcribe_returns_valid_result(self, transcriber):
        """실제 전사 결과가 유효한 형식이어야 한다"""
        # 테스트용 오디오 (노이즈)
        audio = np.random.randn(16000).astype(np.float32) * 0.01
        result = transcriber.transcribe(audio)

        assert "text" in result
        assert "confidence" in result
        assert isinstance(result["text"], str)
        assert isinstance(result["confidence"], float)
