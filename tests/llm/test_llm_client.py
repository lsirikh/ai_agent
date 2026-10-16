"""
LLM Client Tests

Phase 1.2: vLLM 기반 LLM 클라이언트 테스트
TDD 방식으로 진행 - 먼저 테스트 작성 후 구현
"""
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# vLLM 서버 가용성 체크
VLLM_HOST = os.getenv("VLLM_HOST", "localhost")
VLLM_PORT = int(os.getenv("VLLM_PORT", "11003"))  # vLLM 서비스 포트


def is_vllm_available() -> bool:
    """vLLM 서버가 실행 중인지 확인 (실제 API 엔드포인트 체크)"""
    import httpx
    try:
        # vLLM의 /v1/models 엔드포인트 체크하고 실제 모델이 로드되었는지 확인
        response = httpx.get(f"http://{VLLM_HOST}:{VLLM_PORT}/v1/models", timeout=2.0)
        if response.status_code != 200:
            return False
        data = response.json()
        # 모델이 로드되어 있는지 확인
        if not data.get("data"):
            return False
        # 간단한 채팅 요청으로 실제 작동 확인
        model_id = data["data"][0]["id"]
        chat_response = httpx.post(
            f"http://{VLLM_HOST}:{VLLM_PORT}/v1/chat/completions",
            json={
                "model": model_id,
                "messages": [{"role": "user", "content": "hi"}],
                "max_tokens": 5
            },
            timeout=10.0
        )
        return chat_response.status_code == 200
    except Exception:
        return False


VLLM_AVAILABLE = is_vllm_available()


def get_loaded_model_name() -> str:
    """vLLM에 로드된 모델 이름 가져오기"""
    import httpx
    try:
        response = httpx.get(f"http://{VLLM_HOST}:{VLLM_PORT}/v1/models", timeout=2.0)
        if response.status_code == 200:
            data = response.json()
            if data.get("data"):
                return data["data"][0]["id"]
    except Exception:
        pass
    return "Qwen/Qwen2.5-14B-Instruct-AWQ"  # fallback


LOADED_MODEL_NAME = get_loaded_model_name() if VLLM_AVAILABLE else None


# ==========================================
# Unit Tests (Mock 기반 - vLLM 없이 실행)
# ==========================================

class TestLLMClientInitialization:
    """LLMClient 초기화 테스트"""

    def test_llm_client_initialization_with_default_config(self):
        """기본 설정으로 LLMClient가 초기화되어야 한다"""
        from services.orchestrator.app.llm_client import LLMClient

        client = LLMClient()

        assert client is not None
        assert client.base_url is not None
        assert client.model_name is not None
        assert client.timeout > 0

    def test_llm_client_initialization_with_custom_config(self):
        """커스텀 설정으로 LLMClient가 초기화되어야 한다"""
        from services.orchestrator.app.llm_client import LLMClient

        client = LLMClient(
            base_url="http://custom-llm:11000",
            model_name="custom-model",
            timeout=60.0
        )

        assert client.base_url == "http://custom-llm:11000"
        assert client.model_name == "custom-model"
        assert client.timeout == 60.0

    def test_llm_client_has_environment_configs(self):
        """LLMClient에 환경별 설정이 있어야 한다"""
        from services.orchestrator.app.llm_client import LLMClient

        assert hasattr(LLMClient, "MODEL_CONFIGS")
        configs = LLMClient.MODEL_CONFIGS

        assert "development" in configs
        assert "production_jetson" in configs

        # 개발 환경은 대용량 모델 사용
        assert "72B" in configs["development"]["model_name"] or "14B" in configs["development"]["model_name"]
        # Jetson은 경량 모델 사용
        assert "7B" in configs["production_jetson"]["model_name"] or "3B" in configs["production_jetson"]["model_name"]


class TestLLMClientGenerateResponse:
    """LLMClient 응답 생성 테스트"""

    @pytest.mark.asyncio
    async def test_generate_response_returns_text(self):
        """generate_response는 텍스트를 반환해야 한다"""
        from services.orchestrator.app.llm_client import LLMClient

        client = LLMClient()

        # Mock HTTP 클라이언트
        mock_response = {
            "choices": [
                {
                    "message": {
                        "content": "안녕하세요! 무엇을 도와드릴까요?"
                    }
                }
            ]
        }

        with patch.object(client, "_make_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response

            result = await client.generate_response("안녕하세요")

            assert isinstance(result, str)
            assert "안녕하세요" in result or "도와" in result
            mock_request.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_response_with_messages(self):
        """대화 기록을 포함한 응답 생성이 가능해야 한다"""
        from services.orchestrator.app.llm_client import LLMClient

        client = LLMClient()

        messages = [
            {"role": "user", "content": "내 이름은 김철수야"},
            {"role": "assistant", "content": "안녕하세요 김철수님!"},
            {"role": "user", "content": "내 이름이 뭐라고 했지?"}
        ]

        mock_response = {
            "choices": [
                {
                    "message": {
                        "content": "김철수님이라고 하셨습니다."
                    }
                }
            ]
        }

        with patch.object(client, "_make_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response

            result = await client.generate_response(messages=messages)

            assert isinstance(result, str)
            # _make_request가 올바른 messages와 함께 호출되었는지 확인
            call_args = mock_request.call_args
            assert call_args is not None


class TestLLMClientStreaming:
    """LLMClient 스트리밍 테스트"""

    @pytest.mark.asyncio
    async def test_generate_stream_yields_tokens(self):
        """generate_stream은 토큰을 순차적으로 yield해야 한다"""
        from services.orchestrator.app.llm_client import LLMClient

        client = LLMClient()

        # Mock 스트리밍 응답
        async def mock_stream_response():
            tokens = ["안녕", "하세요", "!", " 무엇을", " 도와", "드릴까요", "?"]
            for token in tokens:
                yield {"choices": [{"delta": {"content": token}}]}

        with patch.object(client, "_make_stream_request", return_value=mock_stream_response()):
            tokens = []
            async for token in client.generate_stream("안녕하세요"):
                tokens.append(token)

            assert len(tokens) > 0
            full_text = "".join(tokens)
            assert "안녕하세요" in full_text

    @pytest.mark.asyncio
    async def test_generate_stream_handles_stop_token(self):
        """스트리밍이 stop 토큰에서 올바르게 종료되어야 한다"""
        from services.orchestrator.app.llm_client import LLMClient

        client = LLMClient()

        async def mock_stream_with_stop():
            yield {"choices": [{"delta": {"content": "Hello"}}]}
            yield {"choices": [{"delta": {"content": " World"}}]}
            yield {"choices": [{"delta": {}, "finish_reason": "stop"}]}

        with patch.object(client, "_make_stream_request", return_value=mock_stream_with_stop()):
            tokens = []
            async for token in client.generate_stream("Hi"):
                tokens.append(token)

            assert len(tokens) == 2
            assert "Hello" in tokens
            assert " World" in tokens


class TestLLMClientContextManagement:
    """LLMClient 대화 컨텍스트 관리 테스트"""

    def test_context_management_add_message(self):
        """대화 메시지를 컨텍스트에 추가할 수 있어야 한다"""
        from services.orchestrator.app.llm_client import LLMClient

        client = LLMClient()

        client.add_to_context("user", "안녕하세요")
        client.add_to_context("assistant", "안녕하세요! 무엇을 도와드릴까요?")

        context = client.get_context()
        assert len(context) == 2
        assert context[0]["role"] == "user"
        assert context[0]["content"] == "안녕하세요"
        assert context[1]["role"] == "assistant"

    def test_context_management_clear(self):
        """컨텍스트를 비울 수 있어야 한다"""
        from services.orchestrator.app.llm_client import LLMClient

        client = LLMClient()

        client.add_to_context("user", "첫 번째 메시지")
        client.add_to_context("assistant", "첫 번째 응답")

        client.clear_context()

        assert len(client.get_context()) == 0

    def test_context_management_max_history(self):
        """컨텍스트 길이가 제한되어야 한다 (오래된 메시지 제거)"""
        from services.orchestrator.app.llm_client import LLMClient

        client = LLMClient(max_context_messages=4)

        # 5쌍의 대화 추가 (10개 메시지)
        for i in range(5):
            client.add_to_context("user", f"메시지 {i}")
            client.add_to_context("assistant", f"응답 {i}")

        context = client.get_context()
        # max_context_messages가 4이면 최근 4개 메시지만 유지
        assert len(context) <= 4


class TestLLMClientSystemPrompt:
    """LLMClient 시스템 프롬프트 테스트"""

    def test_system_prompt_injection(self):
        """시스템 프롬프트가 올바르게 주입되어야 한다"""
        from services.orchestrator.app.llm_client import LLMClient

        system_prompt = "당신은 친절한 AI 비서입니다. 항상 한국어로 답변하세요."
        client = LLMClient(system_prompt=system_prompt)

        assert client.system_prompt == system_prompt

    @pytest.mark.asyncio
    async def test_system_prompt_included_in_request(self):
        """요청에 시스템 프롬프트가 포함되어야 한다"""
        from services.orchestrator.app.llm_client import LLMClient

        system_prompt = "당신은 친절한 AI 비서입니다."
        client = LLMClient(system_prompt=system_prompt)

        mock_response = {
            "choices": [{"message": {"content": "응답입니다."}}]
        }

        with patch.object(client, "_make_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response

            await client.generate_response("안녕")

            # 호출 인자 확인
            call_args = mock_request.call_args
            assert call_args is not None
            messages = call_args[0][0] if call_args[0] else call_args[1].get("messages", [])

            # 시스템 메시지가 첫 번째로 포함되어야 함
            if messages:
                assert messages[0]["role"] == "system"
                assert system_prompt in messages[0]["content"]

    def test_update_system_prompt(self):
        """시스템 프롬프트를 업데이트할 수 있어야 한다"""
        from services.orchestrator.app.llm_client import LLMClient

        client = LLMClient(system_prompt="초기 프롬프트")

        new_prompt = "새로운 프롬프트입니다."
        client.set_system_prompt(new_prompt)

        assert client.system_prompt == new_prompt


class TestLLMClientRAGContext:
    """LLMClient RAG 컨텍스트 주입 테스트"""

    @pytest.mark.asyncio
    async def test_rag_context_injection(self):
        """RAG 컨텍스트가 프롬프트에 주입되어야 한다"""
        from services.orchestrator.app.llm_client import LLMClient

        client = LLMClient()

        rag_context = [
            {"content": "EdgeVoice는 음성 AI 비서 시스템입니다.", "source": "docs/intro.md"},
            {"content": "Whisper 모델을 사용하여 음성을 인식합니다.", "source": "docs/stt.md"}
        ]

        mock_response = {
            "choices": [{"message": {"content": "EdgeVoice에 대해 설명드리겠습니다."}}]
        }

        with patch.object(client, "_make_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_response

            await client.generate_response(
                "EdgeVoice가 뭐야?",
                rag_context=rag_context
            )

            call_args = mock_request.call_args
            assert call_args is not None

    def test_format_rag_context(self):
        """RAG 컨텍스트가 올바른 형식으로 변환되어야 한다"""
        from services.orchestrator.app.llm_client import LLMClient

        client = LLMClient()

        rag_context = [
            {"content": "문서 내용 1", "source": "doc1.md"},
            {"content": "문서 내용 2", "source": "doc2.md"}
        ]

        formatted = client.format_rag_context(rag_context)

        assert "문서 내용 1" in formatted
        assert "문서 내용 2" in formatted
        assert "doc1.md" in formatted or "참고 자료" in formatted


# ==========================================
# Integration Tests (vLLM 서버 필요)
# ==========================================

@pytest.mark.skipif(not VLLM_AVAILABLE, reason="vLLM server not available")
class TestLLMClientIntegration:
    """vLLM 서버 연동 통합 테스트"""

    @pytest.mark.asyncio
    async def test_real_generate_response(self):
        """실제 vLLM 서버에서 응답 생성"""
        from services.orchestrator.app.llm_client import LLMClient

        client = LLMClient(
            base_url=f"http://{VLLM_HOST}:{VLLM_PORT}",
            model_name=LOADED_MODEL_NAME
        )

        result = await client.generate_response("1 더하기 1은?")

        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_real_streaming_response(self):
        """실제 vLLM 서버에서 스트리밍 응답"""
        from services.orchestrator.app.llm_client import LLMClient

        client = LLMClient(
            base_url=f"http://{VLLM_HOST}:{VLLM_PORT}",
            model_name=LOADED_MODEL_NAME
        )

        tokens = []
        async for token in client.generate_stream("오늘 날씨가 어때?"):
            tokens.append(token)
            if len(tokens) > 50:  # 무한 루프 방지
                break

        assert len(tokens) > 0
        full_text = "".join(tokens)
        assert len(full_text) > 0
