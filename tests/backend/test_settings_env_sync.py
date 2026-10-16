"""
Settings-Environment 동기화 테스트
Phase 16.3: Settings Apply 연동
Phase 16.4: Startup 동기화

TDD 방식으로 Settings apply 시 .env 파일 동기화를 검증합니다.
"""
import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock


class TestApplySettingsEnvSync:
    """16.3.1 Settings Apply 연동 테스트"""

    def test_apply_settings_updates_env_file(self, tmp_path):
        """
        Settings apply 호출 시 .env 파일이 업데이트되어야 함
        """
        # Arrange
        env_path = tmp_path / ".env"
        env_path.write_text("LLM_MODEL=old_model\n")

        from services.backend.app.services.env_writer import EnvWriterService
        from services.backend.app.services.settings_env_sync import sync_settings_to_env

        settings_data = {
            "llm": {"model": "qwen2.5-7b-instruct-awq"}
        }

        # Act
        sync_settings_to_env(settings_data, env_path=str(env_path))

        # Assert
        writer = EnvWriterService(env_path=str(env_path))
        assert writer.read("LLM_MODEL") == "Qwen/Qwen2.5-7B-Instruct-AWQ"

    def test_apply_settings_converts_model_id(self, tmp_path):
        """
        Settings apply 시 짧은 모델 ID가 전체 경로로 변환되어야 함
        """
        # Arrange
        env_path = tmp_path / ".env"
        env_path.touch()

        from services.backend.app.services.settings_env_sync import sync_settings_to_env

        settings_data = {
            "llm": {"model": "deepseek-r1-distill-qwen-7b"}
        }

        # Act
        sync_settings_to_env(settings_data, env_path=str(env_path))

        # Assert
        from services.backend.app.services.env_writer import EnvWriterService
        writer = EnvWriterService(env_path=str(env_path))
        assert writer.read("LLM_MODEL") == "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B"

    def test_apply_settings_skips_runtime_settings(self, tmp_path):
        """
        런타임 설정(temperature, speed 등)은 .env에 쓰지 않아야 함
        """
        # Arrange
        env_path = tmp_path / ".env"
        env_path.touch()

        from services.backend.app.services.settings_env_sync import sync_settings_to_env

        settings_data = {
            "llm": {
                "model": "qwen2.5-7b-instruct-awq",
                "temperature": 0.7,
                "max_tokens": 1024
            },
            "tts": {
                "engine": "edge-tts",
                "speed": 1.2
            }
        }

        # Act
        sync_settings_to_env(settings_data, env_path=str(env_path))

        # Assert
        from services.backend.app.services.env_writer import EnvWriterService
        writer = EnvWriterService(env_path=str(env_path))

        # 환경변수로 저장되어야 하는 값
        assert writer.read("LLM_MODEL") is not None
        assert writer.read("TTS_ENGINE") == "edge-tts"

        # 런타임 설정은 저장되면 안됨
        content = env_path.read_text()
        assert "temperature" not in content.lower()
        assert "max_tokens" not in content.lower()
        assert "speed" not in content.lower()

    def test_apply_settings_preserves_existing_env(self, tmp_path):
        """
        Settings에 없는 기존 .env 값은 보존되어야 함
        """
        # Arrange
        env_path = tmp_path / ".env"
        env_path.write_text("CUSTOM_VAR=keep_me\nLLM_MODEL=old_model\n")

        from services.backend.app.services.settings_env_sync import sync_settings_to_env

        settings_data = {
            "llm": {"model": "qwen2.5-7b-instruct-awq"}
        }

        # Act
        sync_settings_to_env(settings_data, env_path=str(env_path))

        # Assert
        from services.backend.app.services.env_writer import EnvWriterService
        writer = EnvWriterService(env_path=str(env_path))
        assert writer.read("CUSTOM_VAR") == "keep_me"
        assert writer.read("LLM_MODEL") == "Qwen/Qwen2.5-7B-Instruct-AWQ"


class TestStartupEnvSync:
    """16.4.1 Startup 동기화 테스트"""

    def test_startup_syncs_db_to_env(self, tmp_path):
        """
        시작 시 DB에서 읽은 설정이 .env로 동기화되어야 함
        """
        # Arrange
        env_path = tmp_path / ".env"
        env_path.touch()

        from services.backend.app.services.settings_env_sync import sync_settings_to_env

        # Mock DB에서 가져온 설정값
        db_settings = {
            "llm": {"model": "phi-4-mini-instruct"},
            "stt": {"model_size": "large-v3"},
            "tts": {"engine": "kokoro"}
        }

        # Act
        sync_settings_to_env(db_settings, env_path=str(env_path))

        # Assert
        from services.backend.app.services.env_writer import EnvWriterService
        writer = EnvWriterService(env_path=str(env_path))
        assert writer.read("LLM_MODEL") == "microsoft/Phi-4-mini-instruct"
        assert writer.read("STT_MODEL_SIZE") == "large-v3"
        assert writer.read("TTS_ENGINE") == "kokoro"

    def test_startup_creates_env_if_missing(self, tmp_path):
        """
        .env 파일이 없으면 생성해야 함
        """
        # Arrange
        env_path = tmp_path / "new_dir" / ".env"
        assert not env_path.exists()

        from services.backend.app.services.settings_env_sync import sync_settings_to_env

        settings_data = {
            "llm": {"model": "qwen2.5-3b-instruct"}
        }

        # Act
        sync_settings_to_env(settings_data, env_path=str(env_path))

        # Assert
        assert env_path.exists()
        from services.backend.app.services.env_writer import EnvWriterService
        writer = EnvWriterService(env_path=str(env_path))
        assert writer.read("LLM_MODEL") == "Qwen/Qwen2.5-3B-Instruct"

    def test_startup_handles_empty_db(self, tmp_path):
        """
        DB가 비어있어도 에러 없이 처리되어야 함
        """
        # Arrange
        env_path = tmp_path / ".env"
        env_path.touch()

        from services.backend.app.services.settings_env_sync import sync_settings_to_env

        # Act - 빈 설정
        sync_settings_to_env({}, env_path=str(env_path))

        # Assert - 에러 없이 완료
        assert env_path.exists()
