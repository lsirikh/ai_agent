"""
TTS API Tests

Phase 1.3: TTS FastAPI 엔드포인트 테스트
"""
import io
import wave
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from fastapi.testclient import TestClient


class TestTTSHealthEndpoint:
    """TTS 헬스 체크 엔드포인트 테스트"""

    def test_tts_health_endpoint_returns_200(self):
        """/health 엔드포인트가 200을 반환해야 한다"""
        with patch("services.tts.app.main.get_synthesizer") as mock_get:
            mock_get.return_value = MagicMock()

            from services.tts.app.main import app
            client = TestClient(app)

            response = client.get("/health")

            assert response.status_code == 200

    def test_tts_health_endpoint_returns_status(self):
        """/health 엔드포인트가 상태 정보를 반환해야 한다"""
        with patch("services.tts.app.main.get_synthesizer") as mock_get:
            mock_get.return_value = MagicMock()

            from services.tts.app.main import app
            client = TestClient(app)

            response = client.get("/health")
            data = response.json()

            assert "status" in data
            assert data["status"] == "healthy"
            assert "service" in data
            assert data["service"] == "tts"


class TestTTSSynthesizeEndpoint:
    """TTS 합성 엔드포인트 테스트"""

    def test_tts_synthesize_endpoint_returns_audio(self):
        """/synthesize 엔드포인트가 오디오를 반환해야 한다"""
        mock_audio = np.random.randn(24000).astype(np.float32)

        with patch("services.tts.app.main.get_synthesizer") as mock_get:
            mock_synth = MagicMock()
            mock_synth.synthesize.return_value = mock_audio
            mock_synth.to_wav_bytes.return_value = b"RIFF" + b"\x00" * 100
            mock_get.return_value = mock_synth

            from services.tts.app.main import app
            client = TestClient(app)

            response = client.post(
                "/synthesize",
                json={"text": "안녕하세요"}
            )

            assert response.status_code == 200
            assert response.headers["content-type"] == "audio/wav"

    def test_tts_synthesize_endpoint_with_voice_parameter(self):
        """/synthesize 엔드포인트에서 음성을 지정할 수 있어야 한다"""
        mock_audio = np.random.randn(24000).astype(np.float32)

        with patch("services.tts.app.main.get_synthesizer") as mock_get:
            mock_synth = MagicMock()
            mock_synth.synthesize.return_value = mock_audio
            mock_synth.to_wav_bytes.return_value = b"RIFF" + b"\x00" * 100
            mock_get.return_value = mock_synth

            from services.tts.app.main import app
            client = TestClient(app)

            response = client.post(
                "/synthesize",
                json={"text": "테스트", "voice": "af_bella"}
            )

            assert response.status_code == 200
            mock_synth.set_voice.assert_called_with("af_bella")

    def test_tts_synthesize_endpoint_with_speed_parameter(self):
        """/synthesize 엔드포인트에서 속도를 지정할 수 있어야 한다"""
        mock_audio = np.random.randn(24000).astype(np.float32)

        with patch("services.tts.app.main.get_synthesizer") as mock_get:
            mock_synth = MagicMock()
            mock_synth.synthesize.return_value = mock_audio
            mock_synth.to_wav_bytes.return_value = b"RIFF" + b"\x00" * 100
            mock_get.return_value = mock_synth

            from services.tts.app.main import app
            client = TestClient(app)

            response = client.post(
                "/synthesize",
                json={"text": "테스트", "speed": 1.5}
            )

            assert response.status_code == 200

    def test_tts_synthesize_endpoint_empty_text_returns_error(self):
        """/synthesize 엔드포인트에 빈 텍스트는 에러를 반환해야 한다"""
        with patch("services.tts.app.main.get_synthesizer") as mock_get:
            mock_synth = MagicMock()
            mock_get.return_value = mock_synth

            from services.tts.app.main import app
            client = TestClient(app)

            response = client.post(
                "/synthesize",
                json={"text": ""}
            )

            assert response.status_code == 400


class TestTTSVoicesEndpoint:
    """TTS 음성 목록 엔드포인트 테스트"""

    def test_tts_voices_endpoint_returns_list(self):
        """/voices 엔드포인트가 음성 목록을 반환해야 한다"""
        mock_voices = ["af_default", "af_bella", "am_adam"]

        with patch("services.tts.app.main.get_synthesizer") as mock_get:
            mock_synth = MagicMock()
            mock_synth.get_available_voices.return_value = mock_voices
            mock_get.return_value = mock_synth

            from services.tts.app.main import app
            client = TestClient(app)

            response = client.get("/voices")

            assert response.status_code == 200
            data = response.json()
            assert "voices" in data
            assert isinstance(data["voices"], list)
            assert len(data["voices"]) > 0


class TestTTSRootEndpoint:
    """TTS 루트 엔드포인트 테스트"""

    def test_tts_root_endpoint_returns_info(self):
        """/ 엔드포인트가 서비스 정보를 반환해야 한다"""
        with patch("services.tts.app.main.get_synthesizer") as mock_get:
            mock_get.return_value = MagicMock()

            from services.tts.app.main import app
            client = TestClient(app)

            response = client.get("/")

            assert response.status_code == 200
            data = response.json()
            assert "name" in data
            assert "version" in data
