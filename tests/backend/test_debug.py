"""
Backend API Debug Tests

Phase 5.5: Backend API - Debug 테스트
"""
import base64
import io
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from fastapi.websockets import WebSocket


class TestSTTTestEndpoint:
    """STT 테스트 엔드포인트 테스트"""

    def test_stt_test_endpoint(self):
        """STT 테스트를 수행할 수 있어야 한다"""
        from services.backend.app.main import app

        client = TestClient(app)

        # 테스트용 오디오 데이터 (base64 인코딩된 가짜 데이터)
        audio_data = base64.b64encode(b"fake audio data").decode("utf-8")

        with patch("services.backend.app.routes.debug.test_stt_service") as mock_stt:
            mock_stt.return_value = {
                "success": True,
                "text": "테스트 음성입니다",
                "confidence": 0.95,
                "duration_ms": 150
            }

            response = client.post("/api/debug/stt/test", json={
                "audio_base64": audio_data
            })

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "text" in data
        assert "confidence" in data

    def test_stt_test_with_language(self):
        """언어를 지정하여 STT 테스트를 수행할 수 있어야 한다"""
        from services.backend.app.main import app

        client = TestClient(app)

        audio_data = base64.b64encode(b"fake audio").decode("utf-8")

        with patch("services.backend.app.routes.debug.test_stt_service") as mock_stt:
            mock_stt.return_value = {
                "success": True,
                "text": "Hello world",
                "confidence": 0.9,
                "duration_ms": 100
            }

            response = client.post("/api/debug/stt/test", json={
                "audio_base64": audio_data,
                "language": "en"
            })

        assert response.status_code == 200

    def test_stt_test_returns_error_on_failure(self):
        """STT 실패 시 에러 정보를 반환해야 한다"""
        from services.backend.app.main import app

        client = TestClient(app)

        audio_data = base64.b64encode(b"invalid audio").decode("utf-8")

        with patch("services.backend.app.routes.debug.test_stt_service") as mock_stt:
            mock_stt.return_value = {
                "success": False,
                "error": "오디오 형식이 잘못되었습니다"
            }

            response = client.post("/api/debug/stt/test", json={
                "audio_base64": audio_data
            })

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "error" in data


class TestTTSTestEndpoint:
    """TTS 테스트 엔드포인트 테스트"""

    def test_tts_test_endpoint(self):
        """TTS 테스트를 수행할 수 있어야 한다"""
        from services.backend.app.main import app

        client = TestClient(app)

        with patch("services.backend.app.routes.debug.test_tts_service") as mock_tts:
            mock_tts.return_value = {
                "success": True,
                "audio_base64": base64.b64encode(b"synthesized audio").decode("utf-8"),
                "duration_ms": 1200
            }

            response = client.post("/api/debug/tts/test", json={
                "text": "안녕하세요, 테스트입니다."
            })

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "audio_base64" in data
        assert "duration_ms" in data

    def test_tts_test_with_voice(self):
        """음성을 지정하여 TTS 테스트를 수행할 수 있어야 한다"""
        from services.backend.app.main import app

        client = TestClient(app)

        with patch("services.backend.app.routes.debug.test_tts_service") as mock_tts:
            mock_tts.return_value = {
                "success": True,
                "audio_base64": base64.b64encode(b"audio").decode("utf-8"),
                "duration_ms": 1000
            }

            response = client.post("/api/debug/tts/test", json={
                "text": "테스트",
                "voice": "af_bella"
            })

        assert response.status_code == 200

    def test_tts_test_returns_error_on_failure(self):
        """TTS 실패 시 에러 정보를 반환해야 한다"""
        from services.backend.app.main import app

        client = TestClient(app)

        with patch("services.backend.app.routes.debug.test_tts_service") as mock_tts:
            mock_tts.return_value = {
                "success": False,
                "error": "TTS 서비스를 사용할 수 없습니다"
            }

            response = client.post("/api/debug/tts/test", json={
                "text": "테스트"
            })

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "error" in data

    def test_tts_test_empty_text(self):
        """빈 텍스트는 거부해야 한다"""
        from services.backend.app.main import app

        client = TestClient(app)

        response = client.post("/api/debug/tts/test", json={
            "text": ""
        })

        assert response.status_code == 400


class TestLogsWebSocket:
    """로그 WebSocket 테스트"""

    def test_logs_websocket_endpoint_exists(self):
        """로그 WebSocket 엔드포인트가 존재해야 한다"""
        from services.backend.app.main import app

        client = TestClient(app)

        # WebSocket 엔드포인트 연결 테스트
        with client.websocket_connect("/api/debug/logs") as websocket:
            # 연결이 성공하면 테스트 통과
            pass

    def test_logs_websocket_receives_messages(self):
        """WebSocket으로 로그 메시지를 수신할 수 있어야 한다"""
        from services.backend.app.main import app

        client = TestClient(app)

        with patch("services.backend.app.routes.debug.get_log_queue") as mock_queue:
            # 로그 큐에 메시지 추가
            mock_queue.return_value = ["[INFO] Test log message"]

            with client.websocket_connect("/api/debug/logs") as websocket:
                # 연결 직후 초기 메시지 수신
                data = websocket.receive_json()
                assert "connected" in data or "type" in data


class TestLLMTestEndpoint:
    """LLM 테스트 엔드포인트 테스트"""

    def test_llm_test_endpoint(self):
        """LLM 테스트를 수행할 수 있어야 한다"""
        from services.backend.app.main import app

        client = TestClient(app)

        with patch("services.backend.app.routes.debug.test_llm_service") as mock_llm:
            mock_llm.return_value = {
                "success": True,
                "response": "안녕하세요! 무엇을 도와드릴까요?",
                "tokens_used": 25,
                "duration_ms": 500
            }

            response = client.post("/api/debug/llm/test", json={
                "prompt": "안녕"
            })

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "response" in data


class TestServiceHealthCheck:
    """서비스 개별 헬스체크 테스트"""

    def test_check_stt_health(self):
        """STT 서비스 헬스체크"""
        from services.backend.app.main import app

        client = TestClient(app)

        with patch("services.backend.app.routes.debug.check_service_health") as mock_health:
            mock_health.return_value = {
                "service": "stt",
                "healthy": True,
                "latency_ms": 50,
                "version": "1.0.0"
            }

            response = client.get("/api/debug/health/stt")

        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "stt"
        assert "healthy" in data

    def test_check_tts_health(self):
        """TTS 서비스 헬스체크"""
        from services.backend.app.main import app

        client = TestClient(app)

        with patch("services.backend.app.routes.debug.check_service_health") as mock_health:
            mock_health.return_value = {
                "service": "tts",
                "healthy": True,
                "latency_ms": 30,
                "version": "1.0.0"
            }

            response = client.get("/api/debug/health/tts")

        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "tts"

    def test_check_llm_health(self):
        """LLM 서비스 헬스체크"""
        from services.backend.app.main import app

        client = TestClient(app)

        with patch("services.backend.app.routes.debug.check_service_health") as mock_health:
            mock_health.return_value = {
                "service": "llm",
                "healthy": True,
                "latency_ms": 100,
                "model": "Qwen2.5-7B"
            }

            response = client.get("/api/debug/health/llm")

        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "llm"
