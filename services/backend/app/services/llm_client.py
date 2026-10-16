"""
Backend - Simple LLM Client

HTTP 기반 vLLM 클라이언트 (Docker 환경용)
Phase 13.2: Language 설정 연동
Phase 15.2: Sliding Window 컨텍스트 지원
"""
import json
import os
from typing import Any, AsyncIterator, List, Optional

import httpx

from shared.context_builder import (
    DEFAULT_MAX_MODEL_LEN,
    TEXT_MAX_TOKENS,
    build_messages,
    fit_messages,
    input_budget,
    vllm_tokenize,
)
from shared.tool_calling import Confirm, schema_tokens, stream_with_tools
from shared.tools import ToolRegistry, tool_parser_for


class LLMError(Exception):
    """vLLM 호출 실패 (HTTP 오류·연결 실패)."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


# ===== Language Settings (Phase 13.2, Phase 17: 강화) =====

LANGUAGE_PROMPTS = {
    "ko": """당신은 한국어 AI 어시스턴트 EdgeVoice입니다.

[CRITICAL - 언어 규칙]
- 모든 응답은 100% 한국어로 작성해야 합니다.
- 중국어(中文) 사용 절대 금지. 한자 사용 금지.
- 영어, 일본어 등 다른 언어 사용 금지.
- 사용자가 어떤 언어로 질문해도 반드시 한국어로만 답변하세요.

[응답 규칙]
- 친절하고 도움이 되는 답변을 제공하세요.
- 이전 대화 내용을 기억하고 문맥에 맞게 대화하세요.
- 모르는 것은 모른다고 솔직하게 답변하세요.

IMPORTANT: You MUST respond in Korean (한국어) ONLY.
NEVER use Chinese characters (中文/汉字). NEVER switch to any other language.""",

    "en": """You are EdgeVoice AI assistant.

Important rules:
1. Always respond in English only. Never switch to other languages.
2. Provide helpful and friendly responses.
3. Remember the conversation context and respond accordingly.""",

    "ja": """あなたはEdgeVoice AIアシスタントです。

重要なルール：
1. 必ず日本語でのみ回答してください。他の言語に切り替えないでください。
2. 親切で役立つ回答を提供してください。
3. 会話の文脈を覚えて、適切に応答してください。"""
}

LANGUAGE_VOICE_MAPPING = {
    "ko": "ko-KR-SunHiNeural",
    "en": "en-US-JennyNeural",
    "ja": "ja-JP-NanamiNeural"
}


def get_system_prompt_by_language(language: str) -> str:
    """
    언어에 맞는 시스템 프롬프트 반환

    Args:
        language: 언어 코드 (ko, en, ja)

    Returns:
        해당 언어의 시스템 프롬프트
    """
    return LANGUAGE_PROMPTS.get(language, LANGUAGE_PROMPTS["ko"])


def get_voice_by_language(language: str) -> str:
    """
    언어에 맞는 TTS 음성 반환

    Args:
        language: 언어 코드 (ko, en, ja)

    Returns:
        해당 언어의 TTS 음성 이름
    """
    return LANGUAGE_VOICE_MAPPING.get(language, LANGUAGE_VOICE_MAPPING["ko"])


class SimpleLLMClient:
    """
    간단한 vLLM HTTP 클라이언트

    Docker 환경에서 직접 HTTP 호출로 LLM과 통신
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        model_name: Optional[str] = None,
        system_prompt: Optional[str] = None
    ):
        """
        SimpleLLMClient 초기화

        Args:
            base_url: vLLM 서버 URL
            model_name: 모델 이름 (None이면 자동 감지)
            system_prompt: 시스템 프롬프트
        """
        self.base_url = base_url or os.getenv("VLLM_BASE_URL", "http://ev-llm:11003")
        self.model_name = model_name
        self.system_prompt = system_prompt or "당신은 EdgeVoice AI 어시스턴트입니다."
        self.max_model_len = DEFAULT_MAX_MODEL_LEN
        # vLLM 이 도구 요청을 400 으로 거절하면 False (도구 파서 없이 떠 있음)
        self.tools_supported = True
        self._http_client = httpx.AsyncClient(timeout=60.0)

    async def _get_model_name(self) -> Optional[str]:
        """vLLM에서 로드된 모델명 가져오기"""
        if self.model_name:
            return self.model_name

        try:
            response = await self._http_client.get(f"{self.base_url}/v1/models")
            if response.status_code == 200:
                data = response.json()
                if data.get("data"):
                    self.model_name = data["data"][0].get("id")
                    self.max_model_len = int(data["data"][0].get("max_model_len") or self.max_model_len)
                    return self.model_name
        except Exception:
            pass
        return None

    async def generate_stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        conversation_history: Optional[List[dict]] = None,
        max_tokens: int = TEXT_MAX_TOKENS,
        temperature: float = 0.7,
        summary: Optional[str] = None,
        reference: Optional[str] = None,
        tools: Optional[ToolRegistry] = None,
        confirm: Optional[Confirm] = None
    ) -> AsyncIterator[Any]:
        """
        스트리밍 방식으로 텍스트 생성 (토큰 예산 안에서 히스토리를 넣는다)

        Args:
            prompt: 사용자 프롬프트
            system_prompt: 시스템 프롬프트 (None이면 기본값 사용)
            conversation_history: 이전 대화 컨텍스트 [{"role": "user"|"assistant", "content": str}, ...]
            max_tokens: 최대 토큰 수
            temperature: 온도 (창의성)
            summary: 세션 요약 (시스템 메시지 끝에 고정)
            reference: RAG 근거 (이번 질문 앞에 붙는다)
            tools: 이번 턴에 쓸 도구 (모델에 맞는 tool parser 가 없으면 쓰지 않는다)
            confirm: 확인이 필요한 도구를 실행해도 되는지 묻는 콜백

        Yields:
            생성된 토큰. 도구를 쓰면 도구 이벤트(dict)도 섞여 나온다
            (shared.tool_calling.stream_with_tools 참고)

        Raises:
            LLMError: vLLM 이 오류 상태(400·500 등)로 답하면
                — 빈 답이 저장되지 않고 호출자가 오류를 알린다
        """
        model_name = await self._get_model_name()
        if not model_name:
            yield "죄송합니다. LLM 모델을 찾을 수 없습니다."
            return

        if tools and (not self.tools_supported or not tool_parser_for(model_name)):
            tools = None
        reserve = schema_tokens(tools.schemas()) if tools else 0
        messages = await fit_messages(
            lambda limit: build_messages(
                system_prompt=system_prompt or self.system_prompt,
                history=conversation_history or [],
                user_message=prompt,
                summary=summary,
                reference=reference,
                max_model_len=limit - reserve,
                max_tokens=max_tokens,
            ),
            max_model_len=self.max_model_len,
            max_tokens=max_tokens,
            tokenize=lambda m: vllm_tokenize(self.base_url, model_name, m),
        )

        async def request(request_messages: list, schemas: Optional[list]):
            payload = {
                "model": model_name,
                "messages": request_messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "stream": True
            }
            if not schemas:
                async for chunk in self._stream_chunks(payload):
                    yield chunk
                return
            try:
                async for chunk in self._stream_chunks(
                    {**payload, "tools": schemas, "tool_choice": "auto"}
                ):
                    yield chunk
            except LLMError as e:
                # vLLM 에 --enable-auto-tool-choice 가 없으면 400 → 도구를 끄고 다시
                if e.status_code != 400:
                    raise
                self.tools_supported = False
                async for chunk in self._stream_chunks(payload):
                    yield chunk

        async for item in stream_with_tools(
            request,
            messages,
            tools,
            input_budget=input_budget(self.max_model_len, max_tokens),
            confirm=confirm,
        ):
            yield item

    async def _stream_chunks(self, payload: dict) -> AsyncIterator[dict]:
        """vLLM 스트리밍 요청 → 청크(dict). 오류 상태·연결 실패는 LLMError."""
        try:
            async with self._http_client.stream(
                "POST",
                f"{self.base_url}/v1/chat/completions",
                json=payload
            ) as response:
                try:
                    response.raise_for_status()
                except httpx.HTTPStatusError:
                    body = await response.aread()
                    detail = body.decode("utf-8", errors="ignore")[:300]
                    raise LLMError(
                        f"LLM 오류 {response.status_code}: {detail}",
                        status_code=response.status_code,
                    )
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str.strip() == "[DONE]":
                            break
                        try:
                            data = json.loads(data_str)
                        except Exception:
                            continue
                        yield data
        except LLMError:
            raise
        except Exception as e:
            raise LLMError(f"LLM 연결 오류: {e}") from e

    async def complete(
        self,
        messages: List[dict],
        max_tokens: int = 512,
        temperature: float = 0.2
    ) -> str:
        """스트리밍 없이 한 번에 생성 (세션 요약 등 내부용)."""
        model_name = await self._get_model_name()
        if not model_name:
            raise LLMError("LLM 모델을 찾을 수 없습니다")
        response = await self._http_client.post(
            f"{self.base_url}/v1/chat/completions",
            json={
                "model": model_name,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
            },
        )
        if response.status_code >= 400:
            raise LLMError(f"LLM 오류 {response.status_code}: {response.text[:300]}")
        return response.json()["choices"][0]["message"]["content"] or ""

    async def close(self):
        """HTTP 클라이언트 종료"""
        await self._http_client.aclose()
