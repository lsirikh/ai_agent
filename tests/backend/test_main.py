"""
Backend API Main Tests

Phase 5.6: Backend API - Main 애플리케이션 테스트
"""
import pytest
from fastapi.testclient import TestClient


class TestCORSConfiguration:
    """CORS 설정 테스트"""

    def test_cors_enabled(self):
        """CORS가 활성화되어야 한다"""
        from services.backend.app.main import app

        client = TestClient(app)

        # OPTIONS 요청으로 CORS 프리플라이트 확인
        response = client.options(
            "/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET"
            }
        )

        # CORS 헤더 확인 (allow_credentials=True일 때 요청 origin을 반환)
        assert "access-control-allow-origin" in response.headers
        # allow_origins=["*"]와 allow_credentials=True 조합 시
        # 실제로는 요청한 origin을 반환함
        assert response.headers["access-control-allow-origin"] in ["*", "http://localhost:3000"]

    def test_cors_allows_all_methods(self):
        """CORS가 모든 메서드를 허용해야 한다"""
        from services.backend.app.main import app

        client = TestClient(app)

        response = client.options(
            "/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST"
            }
        )

        assert "access-control-allow-methods" in response.headers

    def test_cors_allows_credentials(self):
        """CORS가 자격 증명을 허용해야 한다"""
        from services.backend.app.main import app

        client = TestClient(app)

        response = client.options(
            "/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET"
            }
        )

        assert "access-control-allow-credentials" in response.headers
        assert response.headers["access-control-allow-credentials"] == "true"


class TestHealthEndpoint:
    """헬스 체크 엔드포인트 테스트"""

    def test_health_endpoint(self):
        """/health 엔드포인트가 동작해야 한다"""
        from services.backend.app.main import app

        client = TestClient(app)
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        # Phase 14: DB 연결 없이도 "degraded"로 정상 동작
        assert data["status"] in ["healthy", "degraded"]
        assert data["service"] == "backend"
        # Phase 14: database 필드 추가
        assert "database" in data

    def test_health_returns_json(self):
        """/health 엔드포인트가 JSON을 반환해야 한다"""
        from services.backend.app.main import app

        client = TestClient(app)
        response = client.get("/health")

        assert response.headers["content-type"] == "application/json"


class TestAppConfiguration:
    """앱 설정 테스트"""

    def test_app_title(self):
        """앱 타이틀이 올바르게 설정되어야 한다"""
        from services.backend.app.main import app

        assert app.title == "EdgeVoice Backend API"

    def test_app_version(self):
        """앱 버전이 설정되어야 한다"""
        from services.backend.app.main import app

        assert app.version is not None
        assert len(app.version) > 0

    def test_openapi_docs_available(self):
        """OpenAPI 문서가 사용 가능해야 한다"""
        from services.backend.app.main import app

        client = TestClient(app)
        response = client.get("/openapi.json")

        assert response.status_code == 200
        data = response.json()
        assert "openapi" in data
        assert "paths" in data


class TestRoutersRegistered:
    """라우터 등록 테스트"""

    def test_status_router_registered(self):
        """Status 라우터가 등록되어야 한다"""
        from services.backend.app.main import app

        client = TestClient(app)
        response = client.get("/api/status")

        assert response.status_code == 200

    def test_settings_router_registered(self):
        """Settings 라우터가 등록되어야 한다"""
        from services.backend.app.main import app

        client = TestClient(app)
        response = client.get("/api/settings")

        assert response.status_code == 200

    def test_knowledge_router_registered(self):
        """Knowledge 라우터가 등록되어야 한다"""
        from services.backend.app.main import app
        from unittest.mock import MagicMock, AsyncMock, patch

        client = TestClient(app)

        with patch("services.backend.app.routes.knowledge.get_rag_client") as mock_rag:
            mock_client = MagicMock()
            mock_client.list_documents = AsyncMock(return_value=[])
            mock_rag.return_value = mock_client

            response = client.get("/api/knowledge/documents")

        assert response.status_code == 200

    def test_history_router_registered(self):
        """History 라우터가 등록되어야 한다"""
        from services.backend.app.main import app
        from unittest.mock import MagicMock, patch

        client = TestClient(app)

        with patch("services.backend.app.routes.history.get_history_store") as mock_store:
            mock_store.return_value.get_messages.return_value = []

            response = client.get("/api/history")

        assert response.status_code == 200

    def test_debug_router_registered(self):
        """Debug 라우터가 등록되어야 한다"""
        from services.backend.app.main import app
        from unittest.mock import patch

        client = TestClient(app)

        with patch("services.backend.app.routes.debug.check_service_health") as mock_health:
            mock_health.return_value = {
                "service": "stt",
                "healthy": True,
                "latency_ms": 50
            }

            response = client.get("/api/debug/health/stt")

        assert response.status_code == 200
