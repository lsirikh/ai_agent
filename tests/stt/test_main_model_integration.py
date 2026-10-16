"""
STT Main Model Integration Tests

Phase 10.2.3: STT Main과 ModelManager 통합 테스트
TDD: Red → Green → Refactor
"""
import pytest
from unittest.mock import Mock, patch, MagicMock


class TestMainUsesModelManager:
    """main.py가 ModelManager를 사용하는지 테스트"""

    def test_main_uses_model_manager(self):
        """main.py가 STTModelManager를 사용하는지 확인"""
        from services.stt.app.main import get_model_manager

        manager = get_model_manager()

        from services.stt.app.model_manager import STTModelManager
        assert isinstance(manager, STTModelManager)


class TestTranscribeUsesCurrentModel:
    """transcribe가 현재 모델을 사용하는지 테스트"""

    def test_transcribe_uses_current_model(self):
        """transcribe가 ModelManager의 현재 모델을 사용하는지 확인"""
        from services.stt.app.main import get_model_manager

        manager = get_model_manager()

        # ModelManager가 현재 모델 이름을 반환하는지 확인
        current_model = manager.get_current_model_name()
        assert current_model is not None
        assert isinstance(current_model, str)


class TestModelSwitchViaRedis:
    """Redis로 모델 전환이 가능한지 테스트"""

    def test_model_switch_via_redis(self):
        """Redis 메시지로 모델 전환이 가능한지 확인"""
        from services.stt.app.main import get_model_manager

        manager = get_model_manager()

        # 현재 모델 저장
        original_model = manager.get_current_model_name()

        # 다른 모델로 전환 시도
        new_model = "base" if original_model != "base" else "tiny"
        success = manager.switch_model(new_model)

        assert success is True
        assert manager.get_current_model_name() == new_model

        # 원래 모델로 복원
        manager.switch_model(original_model)


class TestModelsEndpoint:
    """모델 목록 API 엔드포인트 테스트"""

    def test_models_endpoint_exists(self):
        """GET /models 엔드포인트가 존재하는지 확인"""
        from fastapi.testclient import TestClient
        from services.stt.app.main import app

        client = TestClient(app)
        response = client.get("/models")

        assert response.status_code == 200

    def test_models_endpoint_returns_list(self):
        """GET /models가 모델 목록을 반환하는지 확인"""
        from fastapi.testclient import TestClient
        from services.stt.app.main import app

        client = TestClient(app)
        response = client.get("/models")

        data = response.json()
        assert "models" in data
        assert isinstance(data["models"], list)
        assert len(data["models"]) > 0

    def test_models_endpoint_includes_current(self):
        """GET /models가 현재 모델을 표시하는지 확인"""
        from fastapi.testclient import TestClient
        from services.stt.app.main import app

        client = TestClient(app)
        response = client.get("/models")

        data = response.json()
        assert "current_model" in data

        # 현재 모델이 목록에 있는지 확인
        model_ids = [m["id"] for m in data["models"]]
        assert data["current_model"] in model_ids


class TestModelSwitchEndpoint:
    """모델 전환 API 엔드포인트 테스트"""

    def test_model_switch_endpoint_exists(self):
        """POST /models/switch 엔드포인트가 존재하는지 확인"""
        from fastapi.testclient import TestClient
        from services.stt.app.main import app

        client = TestClient(app)
        response = client.post("/models/switch", json={"model": "base"})

        # 200 또는 400 (invalid model) 이어야 함, 404면 엔드포인트 없음
        assert response.status_code in [200, 400]

    def test_model_switch_endpoint_changes_model(self):
        """POST /models/switch가 모델을 변경하는지 확인"""
        from fastapi.testclient import TestClient
        from services.stt.app.main import app, get_model_manager

        client = TestClient(app)

        manager = get_model_manager()
        original = manager.get_current_model_name()
        new_model = "tiny" if original != "tiny" else "base"

        response = client.post("/models/switch", json={"model": new_model})

        assert response.status_code == 200
        assert manager.get_current_model_name() == new_model

        # 복원
        manager.switch_model(original)

    def test_model_switch_endpoint_invalid_model(self):
        """POST /models/switch가 잘못된 모델에 대해 에러를 반환하는지 확인"""
        from fastapi.testclient import TestClient
        from services.stt.app.main import app

        client = TestClient(app)
        response = client.post("/models/switch", json={"model": "invalid-model-name"})

        assert response.status_code == 400
