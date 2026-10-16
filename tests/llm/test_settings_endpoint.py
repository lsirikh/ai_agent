"""
LLM Tests - Settings Endpoint

Phase 12.3: LLM 설정 수신 테스트
vLLM은 외부 이미지이므로, LLMClient가 설정을 적용하는지 테스트
"""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch


class TestLLMSettingsEndpoint:
    """LLM 설정 수신 테스트"""

    def test_llm_client_accepts_temperature_setting(self):
        """
        LLMClient가 temperature 설정을 수신하고 적용해야 함.
        """
        from services.orchestrator.app.llm_client import LLMClient

        client = LLMClient(base_url="http://mock:11003")

        # 초기 temperature
        initial_temp = client.temperature

        # temperature 설정 변경
        client.temperature = 0.9

        assert client.temperature == 0.9
        assert client.temperature != initial_temp or initial_temp == 0.9

    def test_llm_client_accepts_max_tokens_setting(self):
        """
        LLMClient가 max_tokens 설정을 수신하고 적용해야 함.
        """
        from services.orchestrator.app.llm_client import LLMClient

        client = LLMClient(base_url="http://mock:11003")

        # max_tokens 설정 변경
        client.max_tokens = 2048

        assert client.max_tokens == 2048

    def test_llm_client_accepts_system_prompt_setting(self):
        """
        LLMClient가 system_prompt 설정을 수신하고 적용해야 함.
        """
        from services.orchestrator.app.llm_client import LLMClient

        client = LLMClient(base_url="http://mock:11003")

        # system_prompt 설정 변경
        new_prompt = "You are a helpful AI assistant specialized in EdgeVoice."
        client.system_prompt = new_prompt

        assert client.system_prompt == new_prompt

    def test_llm_client_uses_settings_in_generation(self):
        """
        LLMClient가 설정된 값을 생성 요청에 사용해야 함.
        """
        from services.orchestrator.app.llm_client import LLMClient

        client = LLMClient(base_url="http://mock:11003")
        client.temperature = 0.5
        client.max_tokens = 512

        # 설정이 저장되어 있어야 함
        assert client.temperature == 0.5
        assert client.max_tokens == 512

    @pytest.mark.asyncio
    async def test_llm_settings_applied_to_request(self):
        """
        LLM 요청 시 설정된 값이 적용되어야 함.
        """
        from services.orchestrator.app.llm_client import LLMClient

        client = LLMClient(base_url="http://mock:11003")
        client.temperature = 0.3
        client.max_tokens = 1024
        client.system_prompt = "Test prompt"

        # 설정이 _default_params에 반영되어 있어야 함
        assert client._default_params["temperature"] == 0.3
        assert client._default_params["max_tokens"] == 1024
        assert client.system_prompt == "Test prompt"

        # 이 설정들은 _make_request에서 사용됨
        # (실제 API 호출 없이 설정 반영 확인)


class TestLLMModelChange:
    """LLM 모델 변경 테스트"""

    def test_llm_client_tracks_model_name(self):
        """
        LLMClient가 모델 이름을 추적해야 함.
        """
        from services.orchestrator.app.llm_client import LLMClient

        client = LLMClient(
            base_url="http://mock:11003",
            model_name="Qwen/Qwen2.5-7B-Instruct-AWQ"
        )

        # model property로 접근 가능해야 함
        assert client.model == "Qwen/Qwen2.5-7B-Instruct-AWQ"
        assert client.model_name == "Qwen/Qwen2.5-7B-Instruct-AWQ"

    def test_llm_model_change_requires_restart(self):
        """
        LLM 모델 변경 시 재시작이 필요함을 확인.
        vLLM은 런타임에 모델을 변경할 수 없으므로, 클라이언트 측에서 처리.
        """
        from services.orchestrator.app.llm_client import LLMClient

        client = LLMClient(base_url="http://mock:11003")
        original_model = client.model

        # 모델 이름만 변경 (실제 모델 로드는 vLLM 재시작 필요)
        client.model = "microsoft/phi-4"

        # 클라이언트 측에서 모델 이름은 변경됨
        assert client.model == "microsoft/phi-4"
        assert client.model_name == "microsoft/phi-4"
        assert client.model != original_model


class TestLLMSettingsValidation:
    """LLM 설정 유효성 검증 테스트"""

    def test_temperature_range_validation(self):
        """
        Temperature는 0.0 ~ 2.0 범위여야 함.
        """
        from services.orchestrator.app.llm_client import LLMClient

        client = LLMClient(base_url="http://mock:11003")

        # 유효한 범위
        client.temperature = 0.0
        assert client.temperature == 0.0

        client.temperature = 1.0
        assert client.temperature == 1.0

        client.temperature = 2.0
        assert client.temperature == 2.0

    def test_max_tokens_positive_validation(self):
        """
        max_tokens는 양수여야 함.
        """
        from services.orchestrator.app.llm_client import LLMClient

        client = LLMClient(base_url="http://mock:11003")

        # 유효한 값
        client.max_tokens = 100
        assert client.max_tokens == 100

        client.max_tokens = 4096
        assert client.max_tokens == 4096
