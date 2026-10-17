"""
LLM Client for vLLM/OpenAI-compatible API

Phase 1.2: vLLM 서버와 통신하는 클라이언트 구현
Phase 27.6: LLM 호출 시점에 Pipeline Logging 추가 (vLLM 프록시 로깅)
"""
import os
import time
from typing import Any, AsyncGenerator, Optional

import httpx

from shared.context_builder import (
    DEFAULT_MAX_MODEL_LEN,
    VOICE_MAX_TOKENS,
    build_messages,
    fit_messages,
    input_budget,
    vllm_tokenize,
)
from shared.tool_calling import (
    Confirm,
    schema_tokens,
    stream_with_tools,
    tool_choice_for,
)
from shared.tools import ToolRegistry, required_tool, tool_parser_for

from .pipeline_logger import PipelineLogger


class LLMClient:
    """
    vLLM/OpenAI API 호환 LLM 클라이언트

    Attributes:
        base_url: vLLM 서버 URL
        model_name: 사용할 모델 이름
        timeout: 요청 타임아웃 (초)
        system_prompt: 시스템 프롬프트
        max_context_messages: 최대 컨텍스트 메시지 수
    """

    MODEL_CONFIGS = {
        "development": {
            "model_name": "Qwen/Qwen2.5-14B-Instruct-AWQ",
            # 음성 답은 2~3문장이라 출력 예약을 작게 두고 나머지를 대화 맥락에 쓴다
            "max_tokens": VOICE_MAX_TOKENS,
            "temperature": 0.7
        },
        "production_jetson": {
            "model_name": "Qwen/Qwen2.5-7B-Instruct-GPTQ-Int4",
            "max_tokens": 1024,
            "temperature": 0.7
        }
    }

    def __init__(
        self,
        base_url: Optional[str] = None,
        model_name: Optional[str] = None,
        timeout: float = 30.0,
        system_prompt: Optional[str] = None,
        max_context_messages: int = 20,
        environment: str = "development"
    ):
        """
        LLMClient 초기화

        Args:
            base_url: vLLM 서버 URL (기본: 환경변수 또는 localhost:11000)
            model_name: 모델 이름 (기본: 환경 설정에 따름)
            timeout: 요청 타임아웃 (초)
            system_prompt: 시스템 프롬프트
            max_context_messages: 최대 컨텍스트 메시지 수
            environment: 환경 설정 ("development" 또는 "production_jetson")
        """
        self.environment = environment
        config = self.MODEL_CONFIGS.get(environment, self.MODEL_CONFIGS["development"])

        self.base_url = base_url or os.getenv("VLLM_BASE_URL", "http://localhost:11000")
        self.model_name = model_name or os.getenv("LLM_MODEL_NAME", config["model_name"])
        self.timeout = timeout
        self.system_prompt = system_prompt or ""
        self.max_context_messages = max_context_messages
        # vLLM --max-model-len (/v1/models 응답으로 갱신)
        self.max_model_len = DEFAULT_MAX_MODEL_LEN
        # vLLM 이 도구 요청을 400 으로 거절하면 False (도구 파서 없이 떠 있음)
        self.tools_supported = True

        # 대화 컨텍스트 저장 (백엔드 세션 히스토리를 못 받을 때의 대체)
        self._context: list[dict[str, str]] = []

        # 기본 생성 파라미터
        self._default_params = {
            "max_tokens": config.get("max_tokens", 2048),
            "temperature": config.get("temperature", 0.7),
            "top_p": 0.95
        }

        # Phase 27.6: Pipeline Logger for LLM calls (proxy logging)
        self._logger = PipelineLogger("llm")

    # === Settings Properties for Dynamic Configuration ===

    @property
    def temperature(self) -> float:
        """현재 temperature 값"""
        return self._default_params.get("temperature", 0.7)

    @temperature.setter
    def temperature(self, value: float) -> None:
        """temperature 설정"""
        self._default_params["temperature"] = value

    @property
    def max_tokens(self) -> int:
        """현재 max_tokens 값"""
        return self._default_params.get("max_tokens", 2048)

    @max_tokens.setter
    def max_tokens(self, value: int) -> None:
        """max_tokens 설정"""
        self._default_params["max_tokens"] = value

    @property
    def model(self) -> str:
        """현재 모델 이름"""
        return self.model_name

    @model.setter
    def model(self, value: str) -> None:
        """모델 이름 설정 (런타임에는 vLLM 재시작 필요)"""
        self.model_name = value

    async def _fetch_served_models(self) -> list[str]:
        """vLLM 이 실제로 서비스 중인 모델 ID 목록 (/v1/models)."""
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{self.base_url}/v1/models")
            response.raise_for_status()
            models = response.json().get("data", [])
            if models and models[0].get("max_model_len"):
                self.max_model_len = int(models[0]["max_model_len"])
            return [m["id"] for m in models]

    async def resolve_model(self) -> str:
        """
        요청에 쓸 모델 이름.

        설정(LLM_MODEL_NAME)만 바뀌고 vLLM 은 다른 모델을 서비스하면 404 로 빈 응답이 되므로,
        설정 모델이 서비스 목록에 없으면 서비스 중인 첫 모델을 쓴다. 목록을 못 받으면 설정값 그대로.
        """
        try:
            served = await self._fetch_served_models()
        except Exception:
            return self.model_name

        if served and self.model_name not in served:
            return served[0]
        return self.model_name

    async def _tokenize(self, messages: list[dict[str, str]]) -> Optional[tuple]:
        """vLLM 이 센 실제 프롬프트 토큰 수와 서버 max_model_len."""
        return await vllm_tokenize(self.base_url, await self.resolve_model(), messages)

    def add_to_context(self, role: str, content: str) -> None:
        """
        대화 컨텍스트에 메시지 추가

        Args:
            role: 역할 ("user", "assistant", "system")
            content: 메시지 내용
        """
        self._context.append({"role": role, "content": content})

        # 컨텍스트 길이 제한
        if len(self._context) > self.max_context_messages:
            # 오래된 메시지부터 제거 (시스템 메시지 제외)
            self._context = self._context[-self.max_context_messages:]

    def get_context(self) -> list[dict[str, str]]:
        """현재 대화 컨텍스트 반환"""
        return self._context.copy()

    def clear_context(self) -> None:
        """대화 컨텍스트 초기화"""
        self._context = []

    def set_system_prompt(self, prompt: str) -> None:
        """시스템 프롬프트 설정"""
        self.system_prompt = prompt

    def format_rag_context(self, rag_context: list[dict[str, Any]]) -> str:
        """
        RAG 검색 결과를 프롬프트용 문자열로 변환

        Args:
            rag_context: RAG 검색 결과 리스트
                         [{"content": str, "source": str}, ...]

        Returns:
            포맷팅된 컨텍스트 문자열
        """
        if not rag_context:
            return ""

        formatted_parts = ["[참고 자료]"]
        for i, ctx in enumerate(rag_context, 1):
            source = ctx.get("source", "unknown")
            content = ctx.get("content", "")
            formatted_parts.append(f"\n--- 문서 {i} ({source}) ---\n{content}")

        return "\n".join(formatted_parts)

    def _build_messages(
        self,
        user_message: Optional[str] = None,
        messages: Optional[list[dict[str, str]]] = None,
        rag_context: Optional[list[dict[str, Any]]] = None,
        history: Optional[list[dict[str, str]]] = None,
        summary: Optional[str] = None,
        max_model_len: Optional[int] = None,
        max_tokens: Optional[int] = None
    ) -> list[dict[str, str]]:
        """
        API 요청용 메시지 리스트 구성

        Args:
            user_message: 단일 사용자 메시지
            messages: 대화 기록 리스트 (그대로 보낸다)
            rag_context: RAG 검색 결과 (이번 사용자 메시지에 붙는다)
            history: 세션 히스토리 (None 이면 메모리 컨텍스트)
            summary: 세션 요약
            max_model_len: 토큰 예산 계산용 모델 길이 (기본: self.max_model_len)
            max_tokens: 출력 예약 (기본: self.max_tokens)

        Returns:
            OpenAI 형식의 메시지 리스트
        """
        if messages or not user_message:
            result_messages = []
            if self.system_prompt:
                result_messages.append({"role": "system", "content": self.system_prompt})
            result_messages.extend(messages or [])
            return result_messages

        return build_messages(
            system_prompt=self.system_prompt,
            history=self._context if history is None else history,
            user_message=user_message,
            summary=summary,
            reference=self.format_rag_context(rag_context) if rag_context else None,
            max_model_len=max_model_len or self.max_model_len,
            max_tokens=max_tokens or self.max_tokens,
        )

    async def _make_request(self, messages: list[dict[str, str]], **kwargs) -> dict:
        """
        vLLM 서버에 동기 요청

        Args:
            messages: 메시지 리스트
            **kwargs: 추가 생성 파라미터

        Returns:
            API 응답 딕셔너리
        """
        params = {**self._default_params, **kwargs}

        payload = {
            "model": self.model_name,
            "messages": messages,
            **params
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/v1/chat/completions",
                json=payload
            )
            response.raise_for_status()
            return response.json()

    async def _make_stream_request(
        self,
        messages: list[dict[str, str]],
        **kwargs
    ) -> AsyncGenerator[dict, None]:
        """
        vLLM 서버에 스트리밍 요청

        Args:
            messages: 메시지 리스트
            **kwargs: 추가 생성 파라미터

        Yields:
            스트리밍 응답 청크
        """
        params = {**self._default_params, **kwargs}

        payload = {
            "model": await self.resolve_model(),
            "messages": messages,
            "stream": True,
            **params
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/v1/chat/completions",
                json=payload
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data = line[6:]
                        if data.strip() == "[DONE]":
                            break
                        import json
                        yield json.loads(data)

    async def generate_response(
        self,
        user_message: Optional[str] = None,
        messages: Optional[list[dict[str, str]]] = None,
        rag_context: Optional[list[dict[str, Any]]] = None,
        session_id: Optional[str] = None,
        **kwargs
    ) -> str:
        """
        LLM 응답 생성 (동기)

        Args:
            user_message: 사용자 메시지
            messages: 대화 기록 (user_message 대신 사용)
            rag_context: RAG 검색 결과
            session_id: 세션 ID (로깅용)
            **kwargs: 추가 생성 파라미터

        Returns:
            생성된 응답 텍스트
        """
        built_messages = self._build_messages(user_message, messages, rag_context)

        # Phase 27.6: Log LLM request start
        start_time = time.time()
        input_preview = user_message[:100] if user_message else "messages provided"
        await self._logger.log(
            event="llm_request_started",
            session_id=session_id,
            data={
                "message": f"LLM request started: {input_preview}...",
                "model": self.model_name,
                "message_count": len(built_messages)
            }
        )

        try:
            response = await self._make_request(built_messages, **kwargs)
            result = response["choices"][0]["message"]["content"]

            # Phase 27.6: Log LLM response success
            duration_ms = int((time.time() - start_time) * 1000)
            usage = response.get("usage", {})
            await self._logger.log(
                event="llm_response_completed",
                session_id=session_id,
                data={
                    "message": f"LLM response completed ({len(result)} chars)",
                    "duration_ms": duration_ms,
                    "model": self.model_name,
                    "response_length": len(result),
                    "prompt_tokens": usage.get("prompt_tokens", 0),
                    "completion_tokens": usage.get("completion_tokens", 0),
                    "total_tokens": usage.get("total_tokens", 0)
                }
            )

            return result

        except Exception as e:
            # Phase 27.6: Log LLM error
            duration_ms = int((time.time() - start_time) * 1000)
            await self._logger.log(
                event="llm_request_failed",
                session_id=session_id,
                data={
                    "message": f"LLM request failed: {str(e)}",
                    "duration_ms": duration_ms,
                    "model": self.model_name,
                    "error": str(e)
                },
                level="error"
            )
            raise

    async def generate_stream(
        self,
        user_message: Optional[str] = None,
        messages: Optional[list[dict[str, str]]] = None,
        rag_context: Optional[list[dict[str, Any]]] = None,
        session_id: Optional[str] = None,
        history: Optional[list[dict[str, str]]] = None,
        summary: Optional[str] = None,
        tools: Optional[ToolRegistry] = None,
        confirm: Optional[Confirm] = None,
        **kwargs
    ) -> AsyncGenerator[Any, None]:
        """
        LLM 응답 스트리밍 생성

        Args:
            user_message: 사용자 메시지
            messages: 대화 기록 (user_message 대신 사용)
            rag_context: RAG 검색 결과
            session_id: 세션 ID (로깅용)
            history: 세션 히스토리 (None 이면 메모리 컨텍스트)
            summary: 세션 요약
            tools: 이번 턴에 쓸 도구 (모델에 맞는 tool parser 가 없으면 쓰지 않는다)
            confirm: 확인이 필요한 도구를 실행해도 되는지 묻는 콜백
            **kwargs: 추가 생성 파라미터

        Yields:
            토큰 문자열. 도구를 쓰면 도구 이벤트(dict)도 섞여 나온다
            (shared.tool_calling.stream_with_tools 참고)
        """
        max_tokens = kwargs.get("max_tokens", self.max_tokens)
        if tools and not (
            self.tools_supported and tool_parser_for(await self.resolve_model())
        ):
            tools = None
        reserve = schema_tokens(tools.schemas()) if tools else 0
        if messages or not user_message:
            built_messages = self._build_messages(user_message, messages, rag_context)
        else:
            # 프롬프트(+ 도구 스키마) + max_tokens 가 모델 길이를 넘으면
            # vLLM 이 400 으로 거절해 음성 답이 나오지 않는다
            built_messages = await fit_messages(
                lambda limit: self._build_messages(
                    user_message, None, rag_context, history, summary,
                    limit - reserve, max_tokens
                ),
                max_model_len=self.max_model_len,
                max_tokens=max_tokens,
                tokenize=self._tokenize,
            )

        async def request(
            request_messages: list, schemas: Optional[list], tool_choice=None
        ):
            if not schemas:
                async for chunk in self._make_stream_request(
                    request_messages, **kwargs
                ):
                    yield chunk
                return
            try:
                async for chunk in self._make_stream_request(
                    request_messages,
                    tools=schemas,
                    tool_choice=tool_choice_for(tool_choice),
                    **kwargs,
                ):
                    yield chunk
            except httpx.HTTPStatusError as e:
                # vLLM 에 --enable-auto-tool-choice 가 없으면 400 → 도구를 끄고 다시
                if e.response.status_code != 400:
                    raise
                self.tools_supported = False
                async for chunk in self._make_stream_request(
                    request_messages, **kwargs
                ):
                    yield chunk

        # Phase 27.6: Log stream start
        start_time = time.time()
        input_preview = user_message[:100] if user_message else "messages provided"
        await self._logger.log(
            event="llm_stream_started",
            session_id=session_id,
            data={
                "message": f"LLM stream started: {input_preview}...",
                "model": self.model_name,
                "message_count": len(built_messages)
            }
        )

        total_tokens = 0
        total_content = ""

        try:
            async for item in stream_with_tools(
                request,
                built_messages,
                tools,
                input_budget=input_budget(self.max_model_len, max_tokens),
                confirm=confirm,
                required=(
                    required_tool(user_message, tools.names()) if tools else None
                ),
            ):
                if isinstance(item, str):
                    total_tokens += 1
                    total_content += item
                yield item

            # Phase 27.6: Log stream completion
            duration_ms = int((time.time() - start_time) * 1000)
            await self._logger.log(
                event="llm_stream_completed",
                session_id=session_id,
                data={
                    "message": f"LLM stream completed ({len(total_content)} chars, {total_tokens} chunks)",
                    "duration_ms": duration_ms,
                    "model": self.model_name,
                    "response_length": len(total_content),
                    "chunk_count": total_tokens
                }
            )

        except Exception as e:
            # Phase 27.6: Log stream error
            duration_ms = int((time.time() - start_time) * 1000)
            await self._logger.log(
                event="llm_stream_failed",
                session_id=session_id,
                data={
                    "message": f"LLM stream failed: {str(e)}",
                    "duration_ms": duration_ms,
                    "model": self.model_name,
                    "error": str(e)
                },
                level="error"
            )
            raise
