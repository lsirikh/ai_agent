"""
Settings Apply Endpoint Tests

Phase 10.3.5: Settings Apply API 테스트
TDD: Red → Green → Refactor
"""
import pytest


class TestApplySettingsEndpoint:
    """POST /api/settings/apply 엔드포인트 테스트"""

    def test_apply_settings_endpoint(self):
        """POST /api/settings/apply 엔드포인트가 존재하는지 확인"""
        from fastapi.testclient import TestClient
        from services.backend.app.main import app

        client = TestClient(app)
        response = client.post("/api/settings/apply")

        # 200 또는 다른 성공 응답이어야 함, 404면 엔드포인트 없음
        assert response.status_code in [200, 400, 422]


class TestApplyIdentifiesRestartRequired:
    """재시작 필요 서비스 식별 테스트"""

    def test_apply_identifies_restart_required(self):
        """LLM 모델 변경 시 재시작이 필요한 서비스를 식별하는지 확인"""
        from fastapi.testclient import TestClient
        from services.backend.app.main import app

        client = TestClient(app)

        # 설정 변경 (LLM 모델 변경은 재시작 필요)
        response = client.post("/api/settings/apply", json={
            "changes": {
                "llm": {"model": "qwen2.5-14b-instruct-awq"}
            }
        })

        assert response.status_code == 200
        data = response.json()
        assert "restart_required" in data
        assert isinstance(data["restart_required"], list)

    def test_apply_no_restart_for_hot_swap(self):
        """TTS 엔진 변경은 재시작이 필요 없는지 확인 (hot-swap)"""
        from fastapi.testclient import TestClient
        from services.backend.app.main import app

        client = TestClient(app)

        # TTS 엔진 변경 (hot-swap 가능)
        response = client.post("/api/settings/apply", json={
            "changes": {
                "tts": {"engine": "kokoro"}
            }
        })

        assert response.status_code == 200
        data = response.json()
        assert "restart_required" in data
        # TTS는 hot-swap이므로 재시작 불필요
        assert "tts" not in data["restart_required"]


class TestApplyReturnsRestartCommand:
    """재시작 명령 반환 테스트"""

    def test_apply_returns_restart_command(self):
        """재시작이 필요할 때 명령을 반환하는지 확인"""
        from fastapi.testclient import TestClient
        from services.backend.app.main import app

        client = TestClient(app)

        response = client.post("/api/settings/apply", json={
            "changes": {
                "llm": {"model": "phi-4"}
            }
        })

        assert response.status_code == 200
        data = response.json()

        # 재시작이 필요한 경우 명령 반환
        if len(data.get("restart_required", [])) > 0:
            assert "restart_commands" in data


class TestApplySettingsResponse:
    """Apply 응답 구조 테스트"""

    def test_apply_response_structure(self):
        """응답이 올바른 구조를 가지고 있는지 확인"""
        from fastapi.testclient import TestClient
        from services.backend.app.main import app

        client = TestClient(app)

        response = client.post("/api/settings/apply", json={
            "changes": {
                "tts": {"engine": "melo"}
            }
        })

        assert response.status_code == 200
        data = response.json()

        # 필수 필드 확인
        assert "applied" in data
        assert "restart_required" in data
        assert "message" in data
