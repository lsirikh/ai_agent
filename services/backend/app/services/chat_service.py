"""
Backend API - ChatService

Phase 9.2: 채팅 서비스 클래스
Phase 15.3: Sliding Window 컨텍스트 로드
"""
import asyncio
from typing import Any, AsyncIterator, Awaitable, Callable, List, Optional, Tuple

from . import conversation

# 채팅 도구 실행 확인: tool_confirm 이벤트의 id → 사용자의 승인 여부를 기다리는 Future
CONFIRM_TIMEOUT_SECONDS = 120.0
_confirms: dict = {}


def resolve_confirm(confirm_id: str, approved: bool) -> bool:
    """POST /api/chat/confirm. 기다리는 확인이 없으면 False."""
    future = _confirms.get(confirm_id)
    if future is None or future.done():
        return False
    future.set_result(approved)
    return True


async def _wait_confirm(event: dict) -> bool:
    future = _confirms.get(event["id"])
    if future is None:
        return False
    try:
        return await asyncio.wait_for(future, CONFIRM_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        return False
    finally:
        _confirms.pop(event["id"], None)


class ChatService:
    """
    채팅 서비스

    LLM 호출, RAG 컨텍스트 검색, 대화 기록 저장을 담당
    """

    def __init__(
        self,
        llm_client: Optional[Any] = None,
        rag_service: Optional[Any] = None,
        history_store: Optional[Any] = None,
        context_enabled: bool = True,
        context_window_size: int = 20,
        tool_provider: Optional[Callable[[], Awaitable[Any]]] = None
    ):
        """
        ChatService 초기화

        Args:
            llm_client: LLM 클라이언트 (None이면 기본 클라이언트 사용)
            rag_service: RAG 서비스 (None이면 RAG 비활성화)
            history_store: 대화 기록 저장소 (None이면 저장 비활성화)
            context_enabled: 컨텍스트 로드 활성화 여부
            context_window_size: Sliding Window 크기 (최근 N개 메시지)
            tool_provider: 이번 턴에 쓸 ToolRegistry 를 돌려주는 함수
                (None 이면 도구 없음)
        """
        self.llm_client = llm_client
        self.rag_service = rag_service
        self.history_store = history_store
        self.context_enabled = context_enabled
        self.context_window_size = context_window_size
        self.tool_provider = tool_provider

    async def process_message(
        self,
        session_id: str,
        message: str,
        use_rag: bool = True
    ) -> AsyncIterator[dict]:
        """
        메시지 처리 (스트리밍)

        Args:
            session_id: 세션 ID
            message: 사용자 메시지
            use_rag: RAG 사용 여부

        Yields:
            채팅 이벤트 (type, content, session_id, sources)
        """
        # 1. RAG 컨텍스트 검색 (use_rag가 True이고 rag_service가 있을 때)
        rag_context = None
        sources = []

        if use_rag and self.rag_service:
            results = await self._get_rag_context(message)
            if results:
                rag_context = results["context"]
                sources = results["sources"]

                # RAG 컨텍스트 이벤트 발행
                yield {
                    "type": "rag_context",
                    "content": rag_context,
                    "session_id": session_id,
                    "sources": sources
                }

        # 2. 대화 히스토리 로드
        # (활성 세션: 요약 + 요약 이후 턴, DB 가 없으면 Sliding Window)
        conversation_history, summary = await self._load_context(session_id)

        # 3. 시스템 프롬프트 생성
        # (고정 — RAG 근거는 이번 질문에 붙여 접두사 캐시를 지킨다)
        system_prompt = self._build_system_prompt()
        extra = {}
        if summary:
            extra["summary"] = summary
        if rag_context:
            extra["reference"] = (
                "다음은 관련 문서 내용입니다. 이 정보를 참고하여 답변하고, "
                f"출처 정보가 있으면 답변에 포함해주세요:\n\n{rag_context}"
            )

        registry = await self.tool_provider() if self.tool_provider else None
        if registry:
            extra["tools"] = registry
            extra["confirm"] = _wait_confirm

        # 4. LLM 스트리밍 호출
        full_response = ""
        tool_results = []
        web_sources = []

        if self.llm_client:
            async for token in self.llm_client.generate_stream(
                message,
                system_prompt=system_prompt,
                conversation_history=conversation_history,
                **extra
            ):
                if isinstance(token, dict):
                    # 도구 이벤트 (tool_call · tool_confirm · tool_result)
                    # → 채팅에 "검색함"·확인 표시
                    if token["type"] == "tool_confirm":
                        loop = asyncio.get_running_loop()
                        _confirms[token["id"]] = loop.create_future()
                    elif token["type"] == "tool_result":
                        tool_results.append(token)
                        web_sources.extend(token["sources"])
                    yield {
                        "type": token["type"],
                        "content": token.get("content", ""),
                        "session_id": session_id,
                        "sources": token.get("sources", []),
                        "id": token["id"],
                        "tool": token["name"],
                        "arguments": token["arguments"],
                    }
                    continue
                full_response += token
                yield {
                    "type": "token",
                    "content": token,
                    "session_id": session_id,
                    "sources": []
                }
        else:
            # LLM 클라이언트가 없으면 기본 응답
            default_response = f"안녕하세요! '{message}'에 대해 말씀해 주셨네요."
            full_response = default_response
            yield {
                "type": "token",
                "content": default_response,
                "session_id": session_id,
                "sources": []
            }

        # 5. 완료 이벤트
        sources = sources + web_sources
        yield {
            "type": "complete",
            "content": full_response,
            "session_id": session_id,
            "sources": sources
        }

        # 6. History 저장 (빈 답은 저장하지 않는다)
        if not full_response.strip():
            return
        if conversation.is_available():
            await conversation.save_message(session_id, "user", message, source="web")
            for result in tool_results:
                await conversation.save_message(
                    session_id,
                    "tool",
                    result["content"],
                    source="web",
                    rag_sources=[
                        {"tool": result["name"], "is_error": result["is_error"]},
                        *result["sources"],
                    ],
                )
            await conversation.save_message(
                session_id,
                "assistant",
                full_response,
                source="web",
                rag_sources=sources,
            )
            conversation.schedule_summary(session_id, self.llm_client)
        elif self.history_store:
            await self._save_to_history(
                session_id=session_id,
                user_message=message,
                assistant_response=full_response,
                sources=sources
            )

    def _build_system_prompt(self, rag_context: Optional[str] = None) -> str:
        """
        시스템 프롬프트 생성

        Phase 17: 한국어 응답 강제 프롬프트 강화

        Args:
            rag_context: RAG 컨텍스트 (있으면 프롬프트에 포함)

        Returns:
            시스템 프롬프트 문자열
        """
        base_prompt = """당신은 한국어 AI 어시스턴트 EdgeVoice입니다.

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
NEVER use Chinese characters (中文/汉字). NEVER switch to any other language."""

        if rag_context:
            return f"""{base_prompt}

다음은 관련 문서 내용입니다. 이 정보를 참고하여 답변해주세요:

{rag_context}

출처 정보가 있으면 답변에 포함해주세요."""

        return base_prompt

    async def _get_rag_context(self, query: str) -> Optional[dict]:
        """
        RAG 컨텍스트 검색

        Args:
            query: 검색 쿼리

        Returns:
            {"context": str, "sources": list} 또는 None
        """
        if not self.rag_service:
            return None

        try:
            # SimpleRAGClient는 async 메서드, 기존 RAGService는 sync
            if hasattr(self.rag_service, 'retrieve'):
                retrieve_method = self.rag_service.retrieve
                if callable(retrieve_method):
                    import asyncio
                    if asyncio.iscoroutinefunction(retrieve_method):
                        results = await retrieve_method(query, top_k=3)
                    else:
                        results = retrieve_method(query, top_k=3)
                else:
                    results = []
            else:
                results = []

            if not results:
                return None

            # 컨텍스트 포맷
            context_parts = []
            sources = []

            for i, result in enumerate(results, 1):
                context_parts.append(f"[문서 {i}]\n{result['content']}")
                sources.append({
                    "doc_id": result.get("doc_id", ""),
                    "filename": result.get("metadata", {}).get("filename", "unknown"),
                    "score": result.get("score", 0)
                })

            formatted_context = "\n\n---\n\n".join(context_parts)

            return {
                "context": formatted_context,
                "sources": sources
            }

        except Exception:
            return None

    async def _save_to_history(
        self,
        session_id: str,
        user_message: str,
        assistant_response: str,
        sources: list
    ) -> None:
        """
        대화 기록 저장

        Args:
            session_id: 세션 ID
            user_message: 사용자 메시지
            assistant_response: AI 응답
            sources: RAG 출처 목록
        """
        if not self.history_store:
            return

        try:
            # 사용자 메시지 저장
            await self.history_store.add_message(
                session_id=session_id,
                role="user",
                content=user_message
            )

            # AI 응답 저장 (메타데이터에 출처 포함)
            await self.history_store.add_message(
                session_id=session_id,
                role="assistant",
                content=assistant_response,
                metadata={
                    "rag_used": len(sources) > 0,
                    "sources": sources
                }
            )

        except Exception:
            pass  # 저장 실패 시 무시

    async def _load_context(self, session_id: str) -> Tuple[List[dict], Optional[str]]:
        """
        (히스토리, 세션 요약).
        길이 제한은 LLM 클라이언트의 ContextBuilder 가 토큰 예산으로 맞춘다.
        """
        if not self.context_enabled:
            return [], None
        if conversation.is_available():
            context = await conversation.get_context(session_id)
            return context["messages"], context["summary"]
        return await self._load_conversation_history(session_id), None

    async def _load_conversation_history(self, session_id: str) -> List[dict]:
        """
        Sliding Window 방식으로 대화 히스토리 로드

        Args:
            session_id: 세션 ID

        Returns:
            대화 히스토리 리스트 [{"role": "user"|"assistant", "content": str}, ...]
            시간순 정렬 (오래된 순 → 최신순)
        """
        # 컨텍스트 비활성화 시 빈 리스트 반환
        if not self.context_enabled:
            return []

        # history_store가 없으면 빈 리스트 반환
        if not self.history_store:
            return []

        try:
            # DB에서 최근 N개 메시지 조회 (DESC로 반환됨)
            messages = await self.history_store.get_session_messages(
                session_id,
                limit=self.context_window_size
            )

            if not messages:
                return []

            # 시간순 정렬 (오래된 순 → 최신순)으로 뒤집기
            messages.reverse()

            # role, content만 추출하여 반환
            return [
                {"role": msg["role"], "content": msg["content"]}
                for msg in messages
            ]

        except Exception:
            return []

    def update_context_settings(
        self,
        context_enabled: Optional[bool] = None,
        context_window_size: Optional[int] = None
    ) -> None:
        """
        런타임에 컨텍스트 설정 변경

        Args:
            context_enabled: 컨텍스트 활성화 여부
            context_window_size: Sliding Window 크기
        """
        if context_enabled is not None:
            self.context_enabled = context_enabled
        if context_window_size is not None:
            self.context_window_size = context_window_size
