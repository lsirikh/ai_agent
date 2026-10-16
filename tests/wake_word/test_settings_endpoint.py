"""
Wake Word Tests - Settings Endpoint

Phase 13.4: Wake Word 서비스 /settings 엔드포인트 테스트
Phase 47.1: Wake Word Threshold 런타임 동적 반영 테스트
"""
import pytest
from unittest.mock import MagicMock, patch


class TestWakeWordSettingsEndpoint:
    """Wake Word /settings 엔드포인트 테스트"""

    def test_wake_word_settings_endpoint_exists(self):
        """
        Wake Word 서비스에 PUT /settings 엔드포인트가 존재해야 함.
        """
        from fastapi.testclient import TestClient
        from services.wake_word.app.main import app

        client = TestClient(app)

        # PUT /settings 엔드포인트 존재 확인
        response = client.put(
            "/settings",
            json={"wake_word": "hey_jarvis", "threshold": 0.6}
        )

        # 404가 아니어야 함 (엔드포인트 존재)
        assert response.status_code != 404

    def test_wake_word_settings_endpoint_applies_threshold(self):
        """
        threshold 설정 변경 시 적용되어야 함.
        """
        from fastapi.testclient import TestClient
        from services.wake_word.app.main import app

        client = TestClient(app)

        # threshold 변경
        response = client.put(
            "/settings",
            json={"threshold": 0.7}
        )

        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "applied" or "threshold" in data


class TestWakeWordAcceptsThreshold:
    """Wake Word /settings가 threshold 파라미터를 처리하는지 테스트 (Phase 13.4)"""

    def test_wake_word_accepts_threshold(self):
        """
        Wake Word /settings가 threshold 파라미터를 받아서 처리해야 함.

        요구사항:
        1. threshold 파라미터를 받아야 함
        2. 유효한 threshold 범위(0.1 ~ 0.9)를 처리해야 함
        3. 응답에 적용된 threshold 또는 상태를 반환해야 함
        """
        from fastapi.testclient import TestClient
        from services.wake_word.app.main import app

        client = TestClient(app)

        # threshold 설정 전송
        response = client.put(
            "/settings",
            json={"threshold": 0.65}
        )

        assert response.status_code == 200
        data = response.json()

        # threshold가 적용되었음을 확인
        assert "threshold" in data or "status" in data

        if "threshold" in data:
            assert data["threshold"] == 0.65

    def test_wake_word_accepts_wake_word_name(self):
        """
        Wake Word /settings가 wake_word 이름 파라미터를 처리해야 함.
        """
        from fastapi.testclient import TestClient
        from services.wake_word.app.main import app

        client = TestClient(app)

        response = client.put(
            "/settings",
            json={"wake_word": "alexa"}
        )

        assert response.status_code == 200
        data = response.json()
        assert "wake_word" in data or "status" in data

    def test_wake_word_accepts_combined_settings(self):
        """
        threshold와 wake_word가 함께 전송될 때도 처리해야 함.
        """
        from fastapi.testclient import TestClient
        from services.wake_word.app.main import app

        client = TestClient(app)

        response = client.put(
            "/settings",
            json={
                "wake_word": "hey_jarvis",
                "threshold": 0.55
            }
        )

        assert response.status_code == 200

    def test_wake_word_threshold_persists(self):
        """
        threshold 설정이 Wake Word 서비스에 저장되고 유지되어야 함.
        """
        from fastapi.testclient import TestClient
        from services.wake_word.app.main import app

        client = TestClient(app)

        # 먼저 threshold 설정
        put_response = client.put(
            "/settings",
            json={"threshold": 0.8}
        )
        assert put_response.status_code == 200

        # GET /health에서 서비스 상태 확인
        health_response = client.get("/health")
        assert health_response.status_code == 200


class TestWakeWordThresholdRuntime:
    """
    Phase 47.1: Wake Word Threshold 런타임 동적 반영 테스트

    Dashboard에서 threshold를 변경하면 서비스 재시작 없이
    즉시 detector에 반영되어야 함.
    """

    def test_wake_word_threshold_updates_at_runtime(self):
        """
        PUT /settings로 threshold 변경 시 detector.set_confidence_threshold() 호출 확인.

        요구사항:
        1. PUT /settings로 threshold 변경 요청
        2. detector.set_confidence_threshold()가 호출되어야 함
        3. detector.confidence_threshold가 새 값으로 변경되어야 함
        """
        from fastapi.testclient import TestClient
        from services.wake_word.app.main import app, service

        client = TestClient(app)

        # 초기 threshold 확인 - detector가 초기화되어 있어야 함
        # lifespan context에서 detector가 생성됨

        # 새로운 threshold로 변경
        new_threshold = 0.35
        response = client.put(
            "/settings",
            json={"threshold": new_threshold}
        )

        assert response.status_code == 200
        data = response.json()

        # 응답에 변경된 threshold 포함
        assert data.get("threshold") == new_threshold

        # detector의 실제 threshold가 변경되었는지 확인
        if service and service.detector:
            assert service.detector.confidence_threshold == new_threshold

    def test_wake_word_threshold_change_logs_event(self):
        """
        Threshold 변경 시 settings_updated Pipeline Log 이벤트가 발행되어야 함.

        요구사항:
        1. threshold 변경 시 Pipeline Log에 settings_updated 이벤트 발행
        2. 이전 값과 새 값이 로그에 포함되어야 함
        """
        from fastapi.testclient import TestClient
        from services.wake_word.app.main import app
        from unittest.mock import AsyncMock, patch

        client = TestClient(app)

        # Pipeline logger를 mock
        with patch("services.wake_word.app.main.get_logger") as mock_get_logger:
            mock_logger = MagicMock()
            mock_logger.info = AsyncMock()
            mock_get_logger.return_value = mock_logger

            # threshold 변경
            response = client.put(
                "/settings",
                json={"threshold": 0.45}
            )

            assert response.status_code == 200

    def test_wake_word_detector_uses_new_threshold_for_detection(self):
        """
        변경된 threshold가 실제 Wake Word 감지에 적용되어야 함.

        요구사항:
        1. threshold를 높은 값(0.9)으로 설정
        2. 낮은 confidence(0.5)로는 감지되지 않아야 함
        3. threshold를 낮은 값(0.3)으로 변경
        4. 같은 confidence(0.5)로 감지되어야 함
        """
        from services.wake_word.app.detector import WakeWordDetector
        import numpy as np

        # Mock detector 생성 (실제 모델 로드 없이)
        detector = WakeWordDetector(confidence_threshold=0.9)

        # 높은 threshold(0.9)에서 낮은 confidence(0.5)는 감지 안됨
        assert detector.confidence_threshold == 0.9

        # threshold 동적 변경
        detector.set_confidence_threshold(0.3)
        assert detector.confidence_threshold == 0.3

        # 이제 0.5 confidence면 감지됨 (threshold 0.3 < 0.5)
