"""
Audio Gateway API Tests

Phase 3.5: Audio Gateway Main - API 엔드포인트 테스트
"""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest
from fastapi.testclient import TestClient


class TestHealthEndpoint:
    """/health 엔드포인트 테스트"""

    def test_audio_gateway_health(self):
        """헬스 엔드포인트가 200을 반환해야 한다"""
        from services.audio_gateway.app.main import app

        client = TestClient(app)
        response = client.get("/health")

        assert response.status_code == 200
        assert response.json()["status"] == "healthy"

    def test_health_includes_service_name(self):
        """헬스 응답에 서비스 이름이 포함되어야 한다"""
        from services.audio_gateway.app.main import app

        client = TestClient(app)
        response = client.get("/health")

        assert response.json()["service"] == "audio-gateway"

    def test_health_includes_components_status(self):
        """
        /info 엔드포인트에 컴포넌트 상태가 포함되어야 한다
        (Phase 28.1: /health는 단순화, /info는 상세 정보)
        """
        from services.audio_gateway.app.main import app

        client = TestClient(app)
        response = client.get("/info")

        data = response.json()
        assert "components" in data
        assert "vad" in data["components"]
        assert "aec" in data["components"]
        assert "barge_in" in data["components"]


class TestAudioStreamEndpoint:
    """오디오 스트림 엔드포인트 테스트"""

    def test_audio_stream_websocket_exists(self):
        """WebSocket 오디오 스트림 엔드포인트가 존재해야 한다"""
        from services.audio_gateway.app.main import app

        # FastAPI 라우터에서 WebSocket 엔드포인트 확인
        routes = [route.path for route in app.routes]
        assert "/ws/audio" in routes or any("/ws/audio" in str(route.path) for route in app.routes)


class TestAudioProcessingEndpoint:
    """오디오 처리 엔드포인트 테스트"""

    def test_process_audio_endpoint_exists(self):
        """오디오 처리 엔드포인트가 존재해야 한다"""
        from services.audio_gateway.app.main import app

        client = TestClient(app)

        # 빈 바디로 요청 (에러 응답이지만 엔드포인트 존재 확인)
        response = client.post("/process", json={})

        # 422 (validation error) 또는 200이면 엔드포인트 존재
        assert response.status_code in [200, 422, 400]


class TestPlaybackControl:
    """재생 제어 엔드포인트 테스트"""

    def test_playback_start_endpoint(self):
        """재생 시작 엔드포인트가 동작해야 한다"""
        from services.audio_gateway.app.main import app

        client = TestClient(app)
        response = client.post("/playback/start")

        assert response.status_code == 200

    def test_playback_stop_endpoint(self):
        """재생 중지 엔드포인트가 동작해야 한다"""
        from services.audio_gateway.app.main import app

        client = TestClient(app)
        response = client.post("/playback/stop")

        assert response.status_code == 200

    def test_playback_status_endpoint(self):
        """재생 상태 엔드포인트가 동작해야 한다"""
        from services.audio_gateway.app.main import app

        client = TestClient(app)
        response = client.get("/playback/status")

        assert response.status_code == 200
        data = response.json()
        assert "is_playing" in data
        assert "queue_size" in data


class TestVADEndpoint:
    """VAD 관련 엔드포인트 테스트"""

    def test_vad_status_endpoint(self):
        """VAD 상태 엔드포인트가 동작해야 한다"""
        from services.audio_gateway.app.main import app

        client = TestClient(app)
        response = client.get("/vad/status")

        assert response.status_code == 200
        data = response.json()
        assert "is_speaking" in data
        assert "threshold" in data

    def test_vad_config_update(self):
        """VAD 설정을 업데이트할 수 있어야 한다"""
        from services.audio_gateway.app.main import app

        client = TestClient(app)
        response = client.post("/vad/config", json={"threshold": 0.6})

        assert response.status_code == 200


class TestAECEndpoint:
    """AEC 관련 엔드포인트 테스트"""

    def test_aec_status_endpoint(self):
        """AEC 상태 엔드포인트가 동작해야 한다"""
        from services.audio_gateway.app.main import app

        client = TestClient(app)
        response = client.get("/aec/status")

        assert response.status_code == 200
        data = response.json()
        assert "enabled" in data
        assert "has_playback_reference" in data

    def test_aec_reset_endpoint(self):
        """AEC 리셋 엔드포인트가 동작해야 한다"""
        from services.audio_gateway.app.main import app

        client = TestClient(app)
        response = client.post("/aec/reset")

        assert response.status_code == 200


class TestBargeInEndpoint:
    """Barge-in 관련 엔드포인트 테스트"""

    def test_barge_in_status_endpoint(self):
        """Barge-in 상태 엔드포인트가 동작해야 한다"""
        from services.audio_gateway.app.main import app

        client = TestClient(app)
        response = client.get("/barge-in/status")

        assert response.status_code == 200
        data = response.json()
        assert "playback_state" in data
        assert "in_cooldown" in data
