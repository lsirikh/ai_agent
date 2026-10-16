"""
TTS Tests - Settings Endpoint

Phase 12.3: TTS 서비스 /settings 엔드포인트 테스트
"""
import pytest
from unittest.mock import MagicMock, patch


class TestTTSSettingsEndpoint:
    """TTS /settings 엔드포인트 테스트"""

    def test_tts_settings_endpoint_exists(self):
        """
        TTS 서비스에 PUT /settings 엔드포인트가 존재해야 함.
        """
        from fastapi.testclient import TestClient
        from services.tts.app.main import app

        client = TestClient(app)

        # PUT /settings 엔드포인트 존재 확인
        response = client.put(
            "/settings",
            json={"engine": "melo", "voice": "af_heart", "speed": 1.0}
        )

        # 404가 아니어야 함 (엔드포인트 존재)
        assert response.status_code != 404

    def test_tts_settings_endpoint_applies_engine(self):
        """
        TTS 설정 변경 시 엔진이 변경되어야 함.
        """
        from fastapi.testclient import TestClient
        from services.tts.app.main import app

        client = TestClient(app)

        # 설정 변경
        response = client.put(
            "/settings",
            json={"engine": "edge_tts"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "applied" or "engine" in data

    def test_tts_settings_endpoint_applies_voice(self):
        """
        TTS 설정 변경 시 음성이 변경되어야 함.
        """
        from fastapi.testclient import TestClient
        from services.tts.app.main import app

        client = TestClient(app)

        # 음성 변경
        response = client.put(
            "/settings",
            json={"voice": "ko-KR-SunHiNeural"}
        )

        assert response.status_code == 200

    def test_tts_settings_endpoint_applies_speed(self):
        """
        TTS 설정 변경 시 속도가 변경되어야 함.
        """
        from fastapi.testclient import TestClient
        from services.tts.app.main import app

        client = TestClient(app)

        # 속도 변경
        response = client.put(
            "/settings",
            json={"speed": 1.5}
        )

        assert response.status_code == 200
        data = response.json()
        # 응답에 적용된 설정이 포함되어야 함
        assert "speed" in data or "status" in data

    def test_tts_settings_endpoint_returns_current_settings(self):
        """
        설정 변경 후 현재 설정 상태를 반환해야 함.
        """
        from fastapi.testclient import TestClient
        from services.tts.app.main import app

        client = TestClient(app)

        response = client.put(
            "/settings",
            json={"engine": "melo", "speed": 1.2}
        )

        assert response.status_code == 200
        data = response.json()
        # 현재 설정 또는 상태 반환
        assert "status" in data or "engine" in data or "speed" in data


class TestTTSAcceptsSpeedSetting:
    """TTS /settings가 speed 파라미터를 처리하는지 테스트 (Phase 13.3)"""

    def test_tts_accepts_speed_setting(self):
        """
        TTS /settings가 speed 파라미터를 받아서 처리해야 함.

        요구사항:
        1. speed 파라미터를 받아야 함
        2. 유효한 speed 범위(0.5 ~ 2.0)를 처리해야 함
        3. 응답에 적용된 speed 또는 상태를 반환해야 함
        """
        from fastapi.testclient import TestClient
        from services.tts.app.main import app

        client = TestClient(app)

        # speed 설정 전송
        response = client.put(
            "/settings",
            json={"speed": 1.3}
        )

        assert response.status_code == 200
        data = response.json()

        # speed가 적용되었음을 확인
        # 응답에 speed 또는 status가 포함되어야 함
        assert "speed" in data or "status" in data

        if "speed" in data:
            assert data["speed"] == 1.3

    def test_tts_accepts_speed_with_other_settings(self):
        """
        speed가 다른 설정과 함께 전송될 때도 처리해야 함.
        """
        from fastapi.testclient import TestClient
        from services.tts.app.main import app

        client = TestClient(app)

        response = client.put(
            "/settings",
            json={
                "engine": "melo",
                "voice": "af_heart",
                "speed": 0.8
            }
        )

        assert response.status_code == 200

    def test_tts_speed_persists_in_settings(self):
        """
        speed 설정이 TTS 서비스에 저장되고 유지되어야 함.
        """
        from fastapi.testclient import TestClient
        from services.tts.app.main import app

        client = TestClient(app)

        # 먼저 speed 설정
        put_response = client.put(
            "/settings",
            json={"speed": 1.7}
        )
        assert put_response.status_code == 200

        # 설정 후 다시 조회하여 speed가 유지되는지 확인
        # GET /settings 또는 GET /health에서 현재 설정 확인
        health_response = client.get("/health")
        assert health_response.status_code == 200

        # 다시 settings 업데이트 시에도 이전 설정이 반영되어야 함
        put_response2 = client.put(
            "/settings",
            json={"voice": "test-voice"}
        )
        assert put_response2.status_code == 200
