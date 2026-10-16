"""
EnvWriterService 테스트
Phase 16: Settings-Environment 동기화 시스템

TDD 방식으로 EnvWriterService 클래스의 동작을 검증합니다.
"""
import pytest
import tempfile
import os
from pathlib import Path


class TestEnvWriterInit:
    """16.1.1 기본 읽기/쓰기 테스트 - 초기화"""

    def test_env_writer_init_creates_empty_file(self, tmp_path):
        """
        초기화 시 .env 파일이 없으면 빈 파일을 생성해야 함
        """
        # Arrange
        env_path = tmp_path / ".env"
        assert not env_path.exists(), "테스트 전에 파일이 없어야 함"

        # Act
        from services.backend.app.services.env_writer import EnvWriterService
        writer = EnvWriterService(env_path=str(env_path))

        # Assert
        assert env_path.exists(), ".env 파일이 생성되어야 함"


class TestEnvWriterReadAll:
    """16.1.1 기본 읽기/쓰기 테스트 - read_all 메서드"""

    def test_env_writer_read_all_empty_file(self, tmp_path):
        """
        빈 .env 파일에서 read_all 호출 시 빈 딕셔너리 반환
        """
        # Arrange
        env_path = tmp_path / ".env"
        env_path.touch()  # 빈 파일 생성

        # Act
        from services.backend.app.services.env_writer import EnvWriterService
        writer = EnvWriterService(env_path=str(env_path))
        result = writer.read_all()

        # Assert
        assert result == {}, "빈 파일에서 빈 딕셔너리 반환해야 함"

    def test_env_writer_read_all_with_values(self, tmp_path):
        """
        값이 있는 .env 파일에서 read_all 호출 시 키-값 딕셔너리 반환
        """
        # Arrange
        env_path = tmp_path / ".env"
        env_path.write_text("KEY1=value1\nKEY2=value2\n")

        # Act
        from services.backend.app.services.env_writer import EnvWriterService
        writer = EnvWriterService(env_path=str(env_path))
        result = writer.read_all()

        # Assert
        assert result == {"KEY1": "value1", "KEY2": "value2"}

    def test_env_writer_read_all_ignores_comments(self, tmp_path):
        """
        주석 라인은 무시해야 함
        """
        # Arrange
        env_path = tmp_path / ".env"
        env_path.write_text("# This is a comment\nKEY1=value1\n# Another comment\n")

        # Act
        from services.backend.app.services.env_writer import EnvWriterService
        writer = EnvWriterService(env_path=str(env_path))
        result = writer.read_all()

        # Assert
        assert result == {"KEY1": "value1"}


class TestEnvWriterRead:
    """16.1.1 기본 읽기/쓰기 테스트 - read 메서드"""

    def test_env_writer_read_single_key(self, tmp_path):
        """
        특정 키의 값을 읽어야 함
        """
        # Arrange
        env_path = tmp_path / ".env"
        env_path.write_text("KEY1=value1\nKEY2=value2\n")

        # Act
        from services.backend.app.services.env_writer import EnvWriterService
        writer = EnvWriterService(env_path=str(env_path))
        result = writer.read("KEY1")

        # Assert
        assert result == "value1"

    def test_env_writer_read_nonexistent_key(self, tmp_path):
        """
        없는 키 읽기 시 None 반환
        """
        # Arrange
        env_path = tmp_path / ".env"
        env_path.write_text("KEY1=value1\n")

        # Act
        from services.backend.app.services.env_writer import EnvWriterService
        writer = EnvWriterService(env_path=str(env_path))
        result = writer.read("NONEXISTENT")

        # Assert
        assert result is None


class TestEnvWriterWrite:
    """16.1.2 쓰기 테스트"""

    def test_env_writer_write_new_key(self, tmp_path):
        """
        새 키를 빈 파일에 쓰기
        """
        # Arrange
        env_path = tmp_path / ".env"
        env_path.touch()

        # Act
        from services.backend.app.services.env_writer import EnvWriterService
        writer = EnvWriterService(env_path=str(env_path))
        result = writer.write("NEW_KEY", "new_value")

        # Assert
        assert result is True
        assert writer.read("NEW_KEY") == "new_value"

    def test_env_writer_write_update_existing(self, tmp_path):
        """
        기존 키 값 업데이트
        """
        # Arrange
        env_path = tmp_path / ".env"
        env_path.write_text("EXISTING_KEY=old_value\n")

        # Act
        from services.backend.app.services.env_writer import EnvWriterService
        writer = EnvWriterService(env_path=str(env_path))
        result = writer.write("EXISTING_KEY", "new_value")

        # Assert
        assert result is True
        assert writer.read("EXISTING_KEY") == "new_value"

    def test_env_writer_write_preserves_comments(self, tmp_path):
        """
        쓰기 시 주석 보존
        """
        # Arrange
        env_path = tmp_path / ".env"
        original_content = "# This is a header comment\nKEY1=value1\n# Section comment\nKEY2=value2\n"
        env_path.write_text(original_content)

        # Act
        from services.backend.app.services.env_writer import EnvWriterService
        writer = EnvWriterService(env_path=str(env_path))
        writer.write("KEY1", "updated_value")

        # Assert - 주석이 보존되어야 함
        content = env_path.read_text()
        assert "# This is a header comment" in content
        assert "# Section comment" in content
        assert "KEY1=updated_value" in content

    def test_env_writer_write_many(self, tmp_path):
        """
        여러 키를 한 번에 쓰기
        """
        # Arrange
        env_path = tmp_path / ".env"
        env_path.write_text("EXISTING=keep\n")

        # Act
        from services.backend.app.services.env_writer import EnvWriterService
        writer = EnvWriterService(env_path=str(env_path))
        result = writer.write_many({
            "KEY1": "value1",
            "KEY2": "value2",
            "EXISTING": "updated"
        })

        # Assert
        assert result is True
        assert writer.read("KEY1") == "value1"
        assert writer.read("KEY2") == "value2"
        assert writer.read("EXISTING") == "updated"


class TestSettingsEnvMap:
    """16.2.1 Settings-Env 매핑 테스트"""

    def test_settings_env_map_llm_model(self):
        """
        LLM model 설정은 LLM_MODEL 환경변수로 매핑됨
        """
        from services.backend.app.services.env_writer import SETTINGS_ENV_MAP

        assert "llm" in SETTINGS_ENV_MAP
        assert SETTINGS_ENV_MAP["llm"]["model"] == "LLM_MODEL"

    def test_settings_env_map_stt_model_size(self):
        """
        STT model_size 설정은 STT_MODEL_SIZE 환경변수로 매핑됨
        """
        from services.backend.app.services.env_writer import SETTINGS_ENV_MAP

        assert "stt" in SETTINGS_ENV_MAP
        assert SETTINGS_ENV_MAP["stt"]["model_size"] == "STT_MODEL_SIZE"

    def test_settings_env_map_tts_engine(self):
        """
        TTS engine 설정은 TTS_ENGINE 환경변수로 매핑됨
        """
        from services.backend.app.services.env_writer import SETTINGS_ENV_MAP

        assert "tts" in SETTINGS_ENV_MAP
        assert SETTINGS_ENV_MAP["tts"]["engine"] == "TTS_ENGINE"

    def test_settings_env_map_runtime_settings_none(self):
        """
        런타임 설정(temperature, speed 등)은 None으로 매핑됨 (.env 불필요)
        """
        from services.backend.app.services.env_writer import SETTINGS_ENV_MAP

        # temperature는 런타임 설정
        assert SETTINGS_ENV_MAP["llm"].get("temperature") is None
        # speed는 런타임 설정
        assert SETTINGS_ENV_MAP["tts"].get("speed") is None


class TestModelIdMap:
    """16.2.2 Model ID 변환 테스트"""

    def test_model_id_map_qwen_short_to_full(self):
        """
        qwen2.5-7b 짧은 ID가 전체 HuggingFace 경로로 변환됨
        """
        from services.backend.app.services.env_writer import MODEL_ID_MAP

        assert "qwen2.5-7b-instruct-awq" in MODEL_ID_MAP
        assert MODEL_ID_MAP["qwen2.5-7b-instruct-awq"] == "Qwen/Qwen2.5-7B-Instruct-AWQ"

    def test_model_id_map_deepseek_short_to_full(self):
        """
        deepseek-r1 짧은 ID가 전체 HuggingFace 경로로 변환됨
        """
        from services.backend.app.services.env_writer import MODEL_ID_MAP

        assert "deepseek-r1-distill-qwen-7b" in MODEL_ID_MAP
        assert MODEL_ID_MAP["deepseek-r1-distill-qwen-7b"] == "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B"

    def test_model_id_map_unknown_returns_original(self):
        """
        없는 ID는 원본 그대로 반환 (get_model_path 함수 사용)
        """
        from services.backend.app.services.env_writer import get_model_path

        unknown_id = "unknown-model-xyz"
        assert get_model_path(unknown_id) == unknown_id
