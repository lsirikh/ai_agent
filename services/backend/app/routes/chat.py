"""
Backend API - Chat Router

Phase 9.1: 채팅 API 라우터
Phase 11.1: ChatService + LLMClient 연동
Phase 11.2: RAGService 연동
Phase 11.3: PersistentHistoryStore 연동
Phase 15.5: LLM Context Settings 통합
Phase 18.4: Chat SSE 스트림 (음성/텍스트 채널 통합)
"""
import asyncio
import json
import os
import time
import uuid
from typing import List, Optional

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

from shared import vision
from shared.mcp_client import start_mcp_from_env
from shared.tools import build_registry, load_tool_settings

from ..constants.redis_channels import RedisChannels
from ..services import conversation
from ..services.chat_service import ChatService, resolve_confirm
from .settings import _llm_context_settings


router = APIRouter(prefix="/api/chat", tags=["chat"])


# 서비스 인스턴스 지연 로딩 (optional dependencies)
# None: 초기화 안됨
_llm_client = None
_rag_service = None
_history_store = None
_chat_service = None
_mcp = None


async def start_mcp():
    """MCP_CONFIG_PATH 에 설정한 MCP 서버에 붙는다(채팅 도구로 쓴다)."""
    global _mcp
    _mcp = await start_mcp_from_env()


async def stop_mcp():
    global _mcp
    if _mcp is not None:
        await _mcp.close()
        _mcp = None


async def get_tools():
    """이번 턴에 쓸 도구: 설정(인터넷 토글, Redis) + MCP 허용 도구."""
    settings = await load_tool_settings(conversation._get_redis())
    mcp_tools = []
    if _mcp is not None:
        try:
            mcp_tools = await _mcp.tools()
        except Exception as e:
            print(f"[Chat] MCP tools unavailable: {e}")
    return build_registry(settings, mcp_tools)


def reset_services():
    """서비스 인스턴스 리셋 (테스트용)"""
    global _llm_client, _rag_service, _history_store, _chat_service
    _llm_client = None
    _rag_service = None
    _history_store = None
    _chat_service = None


def get_llm_client():
    """LLMClient 인스턴스 반환 (지연 로딩)"""
    global _llm_client
    if _llm_client is None:
        try:
            # Backend용 SimpleLLMClient 사용 (HTTP 기반)
            from ..services.llm_client import SimpleLLMClient

            vllm_url = os.getenv("VLLM_BASE_URL", "http://ev-llm:11003")

            _llm_client = SimpleLLMClient(
                base_url=vllm_url,
                system_prompt="당신은 EdgeVoice AI 어시스턴트입니다. 사용자의 질문에 친절하고 정확하게 한국어로만 답변해주세요."
            )
        except Exception:
            pass
    return _llm_client


def get_rag_service():
    """RAGService 인스턴스 반환 (지연 로딩)"""
    global _rag_service
    if _rag_service is None:
        try:
            # Backend용 SimpleRAGClient 사용 (HTTP 기반)
            from ..services.rag_client import SimpleRAGClient

            # 환경변수에서 RAG 서비스 활성화 여부 확인
            rag_enabled = os.getenv("RAG_ENABLED", "true").lower() == "true"

            if rag_enabled:
                _rag_service = SimpleRAGClient()
        except Exception:
            pass
    return _rag_service


async def get_history_store():
    """PersistentHistoryStore 인스턴스 반환 (지연 로딩 + 연결)

    Phase 17: connect() 호출 추가하여 DB 연결 보장
    """
    global _history_store
    if _history_store is None:
        try:
            from ..services.persistent_history import PersistentHistoryStore

            # 환경변수에서 데이터베이스 URL 가져오기
            database_url = os.getenv(
                "DATABASE_URL",
                "postgresql://edgevoice:edgevoice@localhost:5432/edgevoice"
            )

            # History 저장 활성화 여부 확인
            history_enabled = os.getenv("HISTORY_ENABLED", "true").lower() == "true"

            if history_enabled:
                _history_store = PersistentHistoryStore(database_url=database_url)
                # Phase 17: DB 연결 수행
                await _history_store.connect()
        except ImportError:
            # PersistentHistoryStore를 import할 수 없으면 None
            pass
        except Exception as e:
            # 기타 오류 시 None (연결 실패 포함)
            print(f"[Chat] History store connection failed: {e}")
            _history_store = None
    return _history_store


async def get_chat_service():
    """ChatService 인스턴스 반환 (지연 로딩)

    Phase 15.5: LLM context settings를 로드하여 ChatService에 전달
    Phase 17: async로 변경하여 history_store 연결 보장
    - context_enabled: 대화 컨텍스트 사용 여부
    - context_window_size: Sliding Window 크기 (최근 N개 메시지)
    """
    global _chat_service
    if _chat_service is None:
        llm_client = get_llm_client()
        rag_service = get_rag_service()
        history_store = await get_history_store()  # Phase 17: await 추가

        # LLM context settings 로드
        context_enabled = _llm_context_settings.context_enabled
        context_window_size = _llm_context_settings.context_window_size

        _chat_service = ChatService(
            llm_client=llm_client,
            rag_service=rag_service,
            history_store=history_store,
            context_enabled=context_enabled,
            context_window_size=context_window_size,
            tool_provider=get_tools
        )
    else:
        # 이미 생성된 ChatService의 설정 업데이트 (동적 설정 반영)
        _chat_service.update_context_settings(
            context_enabled=_llm_context_settings.context_enabled,
            context_window_size=_llm_context_settings.context_window_size
        )
    return _chat_service


class ChatRequest(BaseModel):
    """채팅 요청 모델"""
    session_id: Optional[str] = None
    message: str
    use_rag: bool = True
    # 첨부 이미지(data:image/…;base64). 비전 모델이 설명해 근거로 붙인다
    images: List[str] = Field(default_factory=list, max_length=vision.MAX_IMAGES)

    @field_validator("images")
    @classmethod
    def _images_are_data_urls(cls, images: List[str]) -> List[str]:
        if not all(vision.valid_image(image) for image in images):
            raise ValueError("이미지는 data:image/…;base64 형식, 8MB 이하만 됩니다")
        return images


class ConfirmRequest(BaseModel):
    """도구 실행 확인 (tool_confirm 이벤트의 id)"""
    confirm_id: str
    approved: bool


class ChatEvent(BaseModel):
    """채팅 이벤트 모델"""
    # "token" | "complete" | "rag_context" | "error"
    # | "tool_call" | "tool_confirm" | "tool_result"
    type: str
    content: str
    session_id: str
    sources: list = []


@router.post("/message")
async def send_message(request: ChatRequest):
    """
    채팅 메시지 전송 (SSE 스트리밍)

    Args:
        request: 채팅 요청

    Returns:
        SSE 스트리밍 응답
    """
    # 세션을 지정하지 않으면 음성과 같은 활성 세션에 이어 쓴다
    if conversation.is_available():
        session_id = await conversation.resolve_session_id(request.session_id)
    else:
        session_id = request.session_id or str(uuid.uuid4())

    # Phase 17: ChatService를 미리 await로 가져옴
    chat_service = await get_chat_service()

    async def generate_response():
        """응답 스트리밍 생성기"""
        try:
            async for event in chat_service.process_message(
                session_id=session_id,
                message=request.message,
                use_rag=request.use_rag,
                images=request.images,
            ):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

        except Exception as e:
            # 에러 발생 시 에러 이벤트 발행
            error_event = {
                "type": "error",
                "content": str(e),
                "session_id": session_id,
                "sources": []
            }
            yield f"data: {json.dumps(error_event, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        generate_response(),
        media_type="text/event-stream"
    )


@router.post("/confirm")
async def confirm_tool(request: ConfirmRequest):
    """
    채팅 중 tool_confirm 이벤트(쓰기·파괴적 MCP 도구)에 대한 사용자 답.
    기다리는 확인이 없으면(시간 초과·이미 답함) 404.
    """
    if not resolve_confirm(request.confirm_id, request.approved):
        raise HTTPException(status_code=404, detail="no pending confirmation")
    return {"confirm_id": request.confirm_id, "approved": request.approved}


@router.websocket("/ws/{session_id}")
async def websocket_chat(websocket: WebSocket, session_id: str):
    """
    WebSocket 채팅 엔드포인트

    Args:
        websocket: WebSocket 연결
        session_id: 세션 ID
    """
    await websocket.accept()
    # Phase 17: await 추가
    chat_service = await get_chat_service()

    try:
        while True:
            data = await websocket.receive_json()

            if data.get("type") == "message":
                content = data.get("content", "")
                use_rag = data.get("use_rag", True)

                try:
                    async for event in chat_service.process_message(
                        session_id=session_id,
                        message=content,
                        use_rag=use_rag
                    ):
                        await websocket.send_json(event)

                except Exception as e:
                    await websocket.send_json({
                        "type": "error",
                        "content": str(e),
                        "session_id": session_id,
                        "sources": []
                    })

    except WebSocketDisconnect:
        pass
    except Exception:
        pass


# ===== Phase 18.4: Chat SSE 스트림 =====

@router.get("/stream")
async def stream_chat(session_id: Optional[str] = None):
    """
    세션별 채팅 메시지 SSE 스트림

    클라이언트가 이 엔드포인트에 연결하면 해당 세션의 메시지를
    실시간으로 수신할 수 있습니다. 음성/텍스트 채널 통합을 위해
    pipeline에서 생성된 메시지도 이 스트림을 통해 전달됩니다.

    이벤트 타입:
    - init: 초기 연결 + 세션 전체 히스토리
    - message: 새 메시지 저장됨 (Redis edgevoice:chat:message)
    - heartbeat: 연결 유지용 (30초마다)

    Args:
        session_id: 세션 ID (없으면 활성 세션)

    Returns:
        StreamingResponse (text/event-stream)
    """

    async def event_generator():
        """SSE 이벤트 생성기"""
        pubsub = None
        try:
            sid = session_id
            messages = []
            if conversation.is_available():
                sid = await conversation.resolve_session_id(session_id)
                # 히스토리를 읽는 사이에 저장된 메시지를 놓치지 않도록 먼저 구독한다
                pubsub = conversation.subscribe_messages()
                await pubsub.subscribe(RedisChannels.CHAT_MESSAGE)
                messages = await conversation.list_messages(sid)

            # 1. 초기 연결 이벤트 (히스토리 포함)
            init_data = {
                "session_id": sid,
                "messages": messages,
                "timestamp": time.time()
            }
            yield f"event: init\ndata: {json.dumps(init_data, ensure_ascii=False)}\n\n"

            # 2. 새 메시지 전달 및 heartbeat
            last_heartbeat = time.time()
            while True:
                if pubsub is None:
                    await asyncio.sleep(1)
                else:
                    item = await pubsub.get_message(
                        ignore_subscribe_messages=True, timeout=1.0
                    )
                    if item and item.get("type") == "message":
                        message = json.loads(item["data"])
                        if message.get("session_id") == sid:
                            data = json.dumps(message, ensure_ascii=False)
                            yield f"event: message\ndata: {data}\n\n"

                # 30초마다 heartbeat
                if time.time() - last_heartbeat >= 30:
                    last_heartbeat = time.time()
                    data = json.dumps({"timestamp": last_heartbeat})
                    yield f"event: heartbeat\ndata: {data}\n\n"

        except asyncio.CancelledError:
            # 클라이언트 연결 종료
            pass
        except Exception as e:
            yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"
        finally:
            if pubsub is not None:
                try:
                    await pubsub.unsubscribe()
                    await pubsub.aclose()
                except Exception:
                    pass

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )
