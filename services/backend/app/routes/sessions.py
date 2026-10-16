"""
Backend API Session Context Router

Phase 15.4: Session Context Endpoints
- GET /api/sessions/{id}/context - 세션 컨텍스트 조회
- DELETE /api/sessions/{id}/context - 세션 컨텍스트 초기화

Phase 18.3.3: Pipeline Session API
- POST /api/sessions/pipeline - 파이프라인(음성) 세션 생성

Phase 18.3.4: Pipeline Message API
- POST /api/sessions/pipeline/messages - 파이프라인 메시지 생성

통합 대화(음성 + 텍스트)
- GET /api/sessions/active - 활성 세션 (없으면 만든다)
- POST /api/sessions - 새 세션을 만들고 활성으로 지정 ("새 대화")
- GET /api/sessions/{id}/messages - 세션 전체 메시지 (시간순)
"""
from typing import Literal, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .history import get_history_store
from ..models.session import SessionType
from ..services import conversation


router = APIRouter(prefix="/api/sessions", tags=["sessions"])


# ===== Pydantic Models =====

class SessionContextResponse(BaseModel):
    """세션 컨텍스트 응답 (요약 + 요약 이후 메시지)"""
    session_id: str
    message_count: int
    summary: Optional[str] = None
    messages: list = []


class PipelineSessionRequest(BaseModel):
    """파이프라인 세션 생성 요청"""
    session_id: Optional[str] = None
    source: Optional[str] = "orchestrator"


class PipelineSessionResponse(BaseModel):
    """파이프라인 세션 생성 응답"""
    session_id: str
    session_type: str
    source: str


class SessionContextClearResponse(BaseModel):
    """세션 컨텍스트 삭제 응답"""
    session_id: str
    status: str


class PipelineMessageRequest(BaseModel):
    """파이프라인 메시지 생성 요청"""
    session_id: Optional[str] = None
    role: Literal["user", "assistant", "system", "tool"]
    content: str
    source: Optional[str] = "voice"
    audio_url: Optional[str] = None
    # {"sources": [...]} — 도구 결과·웹 출처 (messages.rag_sources 에 저장)
    metadata: Optional[dict] = None


class PipelineMessageResponse(BaseModel):
    """파이프라인 메시지 생성 응답"""
    message_id: str
    session_id: str
    role: str
    content: str
    source: str
    audio_url: Optional[str] = None


class SessionResponse(BaseModel):
    """활성/새 세션 응답"""
    session_id: str


class SessionMessagesResponse(BaseModel):
    """세션 메시지 목록"""
    session_id: str
    messages: list


def _require_db() -> None:
    if not conversation.is_available():
        raise HTTPException(status_code=503, detail="Database not connected")


# ===== 통합 대화 =====

@router.get("/active", response_model=SessionResponse)
async def get_active_session():
    """음성·채팅이 함께 쓰는 활성 세션. 재시작해도 같은 ID 가 이어진다."""
    _require_db()
    return SessionResponse(session_id=await conversation.get_active_session_id())


@router.post("", response_model=SessionResponse)
async def create_session():
    """새 대화: 새 세션을 만들고 활성으로 지정한다. 이전 세션은 그대로 남는다."""
    _require_db()
    return SessionResponse(session_id=await conversation.start_new_session())


@router.get("/{session_id}/messages", response_model=SessionMessagesResponse)
async def get_session_messages(session_id: str):
    """세션의 전체 메시지 (시간순)."""
    _require_db()
    try:
        messages = await conversation.list_messages(session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="session_id must be a UUID")
    return SessionMessagesResponse(session_id=session_id, messages=messages)


# ===== API Endpoints =====

@router.get("/{session_id}/context", response_model=SessionContextResponse)
async def get_session_context(session_id: str):
    """
    세션 컨텍스트 조회

    Args:
        session_id: 세션 ID

    Returns:
        요약 + 요약에 덮이지 않은 메시지 (프롬프트 조립용)
    """
    if conversation.is_available():
        try:
            return SessionContextResponse(**await conversation.get_context(session_id))
        except ValueError:
            raise HTTPException(status_code=400, detail="session_id must be a UUID")

    store = get_history_store()
    messages = store.get_messages(session_id=session_id, limit=10000)

    return SessionContextResponse(
        session_id=session_id,
        message_count=len(messages)
    )


@router.delete("/{session_id}/context", response_model=SessionContextClearResponse)
async def clear_session_context(session_id: str):
    """
    세션 컨텍스트 초기화 (메시지 삭제)

    Args:
        session_id: 세션 ID

    Returns:
        삭제 결과
    """
    store = get_history_store()
    store.clear_session(session_id)

    return SessionContextClearResponse(
        session_id=session_id,
        status="cleared"
    )


# ===== Phase 18.3.3: Pipeline Session API =====

@router.post("/pipeline", response_model=PipelineSessionResponse)
async def create_pipeline_session(request: PipelineSessionRequest):
    """
    파이프라인(음성) 세션 생성

    오케스트레이터에서 음성 파이프라인 시작 시 호출됩니다.
    VOICE 타입의 세션을 생성합니다.

    Args:
        request: 세션 생성 요청 (session_id, source)

    Returns:
        생성된 세션 정보
    """
    # 세션 ID 생성 또는 사용
    session_id = request.session_id or str(uuid4())
    source = request.source or "orchestrator"

    return PipelineSessionResponse(
        session_id=session_id,
        session_type=SessionType.VOICE.value,
        source=source
    )


# ===== Phase 18.3.4: Pipeline Message API =====

@router.post("/pipeline/messages", response_model=PipelineMessageResponse)
async def create_pipeline_message(request: PipelineMessageRequest):
    """
    파이프라인 메시지 생성

    오케스트레이터가 음성 턴(인식 문장·최종 답)을 저장할 때 호출한다.
    DB 가 연결돼 있으면 세션에 저장하고 채팅 스트림으로 발행한다
    (session_id 가 없거나 틀리면 활성 세션).

    Args:
        request: 메시지 생성 요청

    Returns:
        생성된 메시지 정보
    """
    source = request.source or "voice"

    if not conversation.is_available():
        return PipelineMessageResponse(
            message_id=str(uuid4()),
            session_id=request.session_id or "",
            role=request.role,
            content=request.content,
            source=source,
            audio_url=request.audio_url
        )

    session_id = await conversation.resolve_session_id(request.session_id)
    message = await conversation.save_message(
        session_id,
        request.role,
        request.content,
        source=source,
        rag_sources=(request.metadata or {}).get("sources"),
    )
    if request.role == "assistant":
        from .chat import get_llm_client

        conversation.schedule_summary(session_id, get_llm_client())

    return PipelineMessageResponse(
        message_id=message["id"],
        session_id=session_id,
        role=request.role,
        content=request.content,
        source=source,
        audio_url=request.audio_url
    )
