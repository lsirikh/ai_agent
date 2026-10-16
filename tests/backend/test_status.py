"""
Backend API - System Status Tests

Phase 5.1: 시스템 상태 조회 API 테스트
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


class TestSystemStatus:
    """시스템 상태 조회 테스트"""

    def test_get_system_status(self):
        """시스템 상태를 조회할 수 있어야 한다"""
        from services.backend.app.main import app

        client = TestClient(app)
        response = client.get("/api/status")

        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "timestamp" in data

    def test_status_includes_gpu_info(self):
        """상태에 GPU 정보가 포함되어야 한다"""
        from services.backend.app.main import app

        client = TestClient(app)
        response = client.get("/api/status")

        data = response.json()
        assert "gpu" in data
        # GPU 정보는 사용 가능 여부, 메모리 등 포함
        assert "available" in data["gpu"]

    def test_status_includes_services_health(self):
        """상태에 서비스 헬스 정보가 포함되어야 한다"""
        from services.backend.app.main import app

        client = TestClient(app)
        response = client.get("/api/status")

        data = response.json()
        assert "services" in data
        # 각 서비스의 상태 정보
        services = data["services"]
        assert isinstance(services, dict)

    def test_status_includes_orchestrator_state(self):
        """상태에 Orchestrator 상태가 포함되어야 한다"""
        from services.backend.app.main import app

        client = TestClient(app)
        response = client.get("/api/status")

        data = response.json()
        assert "orchestrator" in data
        assert "state" in data["orchestrator"]


class TestServiceHealth:
    """개별 서비스 헬스 체크 테스트"""

    def test_health_endpoint(self):
        """헬스 엔드포인트가 동작해야 한다"""
        from services.backend.app.main import app

        client = TestClient(app)
        response = client.get("/health")

        assert response.status_code == 200
        # Phase 14.1: Status can be "healthy" or "degraded" depending on DB connection
        assert response.json()["status"] in ["healthy", "degraded"]

    def test_health_includes_service_name(self):
        """헬스 응답에 서비스 이름이 포함되어야 한다"""
        from services.backend.app.main import app

        client = TestClient(app)
        response = client.get("/health")

        assert response.json()["service"] == "backend"

    def test_check_service_health(self):
        """특정 서비스의 헬스를 체크할 수 있어야 한다"""
        from services.backend.app.main import app

        client = TestClient(app)
        response = client.get("/api/status/services/stt")

        # 서비스가 없어도 응답은 있어야 함
        assert response.status_code in [200, 503]


class TestSystemMetrics:
    """시스템 메트릭 테스트"""

    def test_get_system_metrics(self):
        """시스템 메트릭을 조회할 수 있어야 한다"""
        from services.backend.app.main import app

        client = TestClient(app)
        response = client.get("/api/status/metrics")

        assert response.status_code == 200
        data = response.json()
        assert "cpu" in data
        assert "memory" in data

    def test_metrics_includes_cpu_usage(self):
        """메트릭에 CPU 사용률이 포함되어야 한다"""
        from services.backend.app.main import app

        client = TestClient(app)
        response = client.get("/api/status/metrics")

        data = response.json()
        assert "percent" in data["cpu"]

    def test_metrics_includes_memory_usage(self):
        """메트릭에 메모리 사용량이 포함되어야 한다"""
        from services.backend.app.main import app

        client = TestClient(app)
        response = client.get("/api/status/metrics")

        data = response.json()
        assert "total" in data["memory"]
        assert "used" in data["memory"]
        assert "percent" in data["memory"]


class TestPhase17ServiceStatus:
    """Phase 17.3: 추가 서비스 상태 확장 테스트"""

    def test_status_includes_wake_word(self):
        """/api/status에 wake_word 상태가 포함되어야 한다"""
        from services.backend.app.main import app

        client = TestClient(app)
        response = client.get("/api/status")

        assert response.status_code == 200
        data = response.json()
        assert "services" in data
        assert "wake_word" in data["services"]
        assert "status" in data["services"]["wake_word"]

    def test_status_includes_audio_gateway(self):
        """/api/status에 audio_gateway 상태가 포함되어야 한다"""
        from services.backend.app.main import app

        client = TestClient(app)
        response = client.get("/api/status")

        assert response.status_code == 200
        data = response.json()
        assert "services" in data
        assert "audio_gateway" in data["services"]
        assert "status" in data["services"]["audio_gateway"]

    def test_status_includes_orchestrator_in_services(self):
        """orchestrator 상태가 orchestrator 키로 별도 반환되어야 한다"""
        from services.backend.app.main import app

        client = TestClient(app)
        response = client.get("/api/status")

        assert response.status_code == 200
        data = response.json()
        # orchestrator는 별도의 키로 상태 제공
        assert "orchestrator" in data
        assert "state" in data["orchestrator"]

    def test_status_includes_service_display_names(self):
        """서비스 표시 이름이 포함되어야 한다"""
        from services.backend.app.main import app

        client = TestClient(app)
        response = client.get("/api/status")

        assert response.status_code == 200
        data = response.json()
        assert "service_display_names" in data
        display_names = data["service_display_names"]
        assert "wake_word" in display_names
        assert "audio_gateway" in display_names
