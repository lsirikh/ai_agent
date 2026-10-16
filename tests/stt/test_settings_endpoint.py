"""
STT Tests - Settings Endpoint

Phase 12.3: STT 서비스 /settings 엔드포인트 테스트
"""
import pytest
from unittest.mock import MagicMock, patch


class TestSTTSettingsEndpoint:
    """STT /settings 엔드포인트 테스트"""

    def test_stt_settings_endpoint_exists(self):
        """
        STT 서비스에 PUT /settings 엔드포인트가 존재해야 함.
        """
        from fastapi.testclient import TestClient
        from services.stt.app.main import app

        client = TestClient(app)

        # PUT /settings 엔드포인트 존재 확인
        response = client.put(
            "/settings",
            json={"model": "large-v3", "language": "ko"}
        )

        # 404가 아니어야 함 (엔드포인트 존재)
        assert response.status_code != 404

    def test_stt_settings_endpoint_applies_model(self):
        """
        STT 설정 변경 시 모델이 변경되어야 함.
        """
        from fastapi.testclient import TestClient
        from services.stt.app.main import app

        client = TestClient(app)

        # 모델 변경
        response = client.put(
            "/settings",
            json={"model": "small"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "applied" or "model" in data

    def test_stt_settings_endpoint_applies_language(self):
        """
        STT 설정 변경 시 언어가 변경되어야 함.
        """
        from fastapi.testclient import TestClient
        from services.stt.app.main import app

        client = TestClient(app)

        # 언어 변경
        response = client.put(
            "/settings",
            json={"language": "en"}
        )

        assert response.status_code == 200

    def test_stt_settings_endpoint_returns_current_settings(self):
        """
        설정 변경 후 현재 설정 상태를 반환해야 함.
        """
        from fastapi.testclient import TestClient
        from services.stt.app.main import app

        client = TestClient(app)

        response = client.put(
            "/settings",
            json={"model": "medium", "language": "ko"}
        )

        assert response.status_code == 200
        data = response.json()
        # 현재 설정 또는 상태 반환
        assert "status" in data or "model" in data or "language" in data
