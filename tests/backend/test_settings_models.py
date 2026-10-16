"""
Settings Models Enhancement Tests

Phase 10.3.3: Settings 모델 확장 테스트
TDD: Red → Green → Refactor
"""
import pytest


class TestTTSSettingsModel:
    """TTSSettings 모델 테스트"""

    def test_tts_settings_model(self):
        """TTSSettings에 engine 필드가 있는지 확인"""
        from services.backend.app.routes.settings import TTSSettings

        settings = TTSSettings()

        # engine 필드 존재 확인
        assert hasattr(settings, "engine")
        assert settings.engine is not None

        # 기본값 확인 (melo)
        assert settings.engine == "melo"

    def test_tts_settings_model_with_engine(self):
        """TTSSettings에 engine을 지정할 수 있는지 확인"""
        from services.backend.app.routes.settings import TTSSettings

        settings = TTSSettings(engine="kokoro")
        assert settings.engine == "kokoro"


class TestSTTSettingsModel:
    """STTSettings 모델 테스트"""

    def test_stt_settings_model(self):
        """STTSettings에 model 필드가 있는지 확인"""
        from services.backend.app.routes.settings import STTSettings

        settings = STTSettings()

        # model 필드 존재 확인 (model_size 대신)
        assert hasattr(settings, "model")

    def test_stt_settings_model_with_model(self):
        """STTSettings에 model을 지정할 수 있는지 확인"""
        from services.backend.app.routes.settings import STTSettings

        settings = STTSettings(model="large-v3-turbo")
        assert settings.model == "large-v3-turbo"


class TestLLMSettingsModel:
    """LLMSettings 모델 테스트"""

    def test_llm_settings_model(self):
        """LLMSettings가 올바른 필드를 가지고 있는지 확인"""
        from services.backend.app.routes.settings import LLMSettings

        settings = LLMSettings()

        # 기본 필드 확인
        assert hasattr(settings, "model")
        assert hasattr(settings, "temperature")
        assert hasattr(settings, "max_tokens")
        assert hasattr(settings, "system_prompt")

    def test_llm_settings_model_with_values(self):
        """LLMSettings에 값을 지정할 수 있는지 확인"""
        from services.backend.app.routes.settings import LLMSettings

        settings = LLMSettings(
            model="qwen2.5-7b-instruct-awq",
            temperature=0.5,
            max_tokens=2048
        )

        assert settings.model == "qwen2.5-7b-instruct-awq"
        assert settings.temperature == 0.5
        assert settings.max_tokens == 2048


class TestAllSettingsModel:
    """AllSettings 모델 테스트"""

    def test_all_settings_has_tts_engine(self):
        """AllSettings.tts에 engine이 있는지 확인"""
        from services.backend.app.routes.settings import AllSettings

        settings = AllSettings()

        assert hasattr(settings.tts, "engine")
        assert settings.tts.engine == "melo"
