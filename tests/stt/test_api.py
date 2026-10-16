"""
Test STT API Endpoints

TDD Phase 1.1: STT FastAPI 엔드포인트 테스트
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# 서비스 모듈 경로 추가
SERVICE_PATH = Path(__file__).parent.parent.parent / "services" / "stt"
sys.path.insert(0, str(SERVICE_PATH))


class TestSTTAPIEndpoints:
    """STT API 엔드포인트 테스트"""

    @pytest.fixture
    def client(self):
        """테스트 클라이언트"""
        with patch("app.main.StreamingTranscriber") as mock_transcriber_class:
            # Mock transcriber 설정
            mock_transcriber = MagicMock()
            mock_transcriber.transcribe.return_value = {
                "text": "테스트 텍스트",
                "confidence": 0.95,
                "language": "ko",
                "segments": []
            }
            mock_transcriber_class.return_value = mock_transcriber

            from app.main import app
            from fastapi.testclient import TestClient
            yield TestClient(app)

    def test_stt_health_endpoint(self, client):
        """/health 엔드포인트가 정상 응답해야 한다"""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "service" in data
        assert data["service"] == "stt"

    def test_stt_root_endpoint(self, client):
        """루트 엔드포인트가 서비스 정보를 반환해야 한다"""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "name" in data
        assert "stt" in data["name"].lower() or "transcriber" in data["name"].lower()

    def test_stt_transcribe_endpoint_exists(self, client):
        """/transcribe 엔드포인트가 존재해야 한다"""
        # POST 요청 (파일 없이)
        response = client.post("/transcribe")
        # 422 (Validation Error) 또는 다른 에러가 나와도
        # 404가 아니면 엔드포인트가 존재하는 것
        assert response.status_code != 404

    def test_stt_transcribe_with_audio(self, client):
        """/transcribe 엔드포인트가 오디오를 처리해야 한다"""
        import io
        import wave
        import numpy as np

        # 테스트용 WAV 파일 생성
        sample_rate = 16000
        duration = 1.0  # 1초
        samples = int(sample_rate * duration)
        audio_data = np.zeros(samples, dtype=np.int16)

        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)  # int16
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(audio_data.tobytes())

        wav_buffer.seek(0)

        response = client.post(
            "/transcribe",
            files={"audio": ("test.wav", wav_buffer, "audio/wav")}
        )
        assert response.status_code == 200
        data = response.json()
        assert "text" in data
        assert "confidence" in data

    def test_stt_transcribe_with_language(self, client):
        """/transcribe 엔드포인트가 언어 파라미터를 처리해야 한다"""
        import io
        import wave
        import numpy as np

        # 테스트용 WAV 파일 생성
        audio_data = np.zeros(16000, dtype=np.int16)
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(16000)
            wav_file.writeframes(audio_data.tobytes())
        wav_buffer.seek(0)

        response = client.post(
            "/transcribe",
            files={"audio": ("test.wav", wav_buffer, "audio/wav")},
            data={"language": "ko"}
        )
        assert response.status_code == 200

    def test_stt_transcribe_returns_segments(self, client):
        """/transcribe 응답에 세그먼트 정보가 포함될 수 있어야 한다"""
        import io
        import wave
        import numpy as np

        audio_data = np.zeros(16000, dtype=np.int16)
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(16000)
            wav_file.writeframes(audio_data.tobytes())
        wav_buffer.seek(0)

        response = client.post(
            "/transcribe",
            files={"audio": ("test.wav", wav_buffer, "audio/wav")}
        )
        assert response.status_code == 200
        data = response.json()
        assert "segments" in data
