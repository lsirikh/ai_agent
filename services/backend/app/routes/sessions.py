"""
Backend API Session Context Router

Phase 15.4: Session Context Endpoints
- GET /api/sessions/{id}/context - 세션 컨텍스트 조회
- DELETE /api/sessions/{id}/context - 세션 컨텍스트 초기화

Phase 18.3.3: Pipeline Session API
- POST /api/sessions/pipeline - 파이프라인(음성) 세션 생성

Phase 18.3.4: Pipeline Message API
- POST /api/sessions/pipeline/messages - 파이프라인 메시지 생성
"""
from typing import Literal, Optional
from uuid import uuid4

from fastapi import APIRouter
from pydantic import BaseModel

from .history import get_history_store
from ..models.session import SessionType, SessionSource


router = APIRouter(prefix="/api/sessions", tags=["sessions"])


# ===== Pydantic Models =====

class SessionContextResponse(BaseModel):
    """세션 컨텍스트 응답"""
    session_id: str
    message_count: int


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
    session_id: str
    role: Literal["user", "assistant", "system"]
    content: str
    source: Optional[str] = "voice"
    audio_url: Optional[str] = None


class PipelineMessageResponse(BaseModel):
    """파이프라인 메시지 생성 응답"""
    message_id: str
    session_id: str
    role: str
    content: str
    source: str
    audio_url: Optional[str] = None


# ===== API Endpoints =====

@router.get("/{session_id}/context", response_model=SessionContextResponse)
async def get_session_context(session_id: str):
    """
    세션 컨텍스트 조회

    Args:
        session_id: 세션 ID

    Returns:
        세션 컨텍스트 정보 (메시지 수)
    """
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

    # TODO: DB에 세션 저장 (Phase 18.3.2 이후)

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

    오케스트레이터에서 음성 파이프라인 메시지를 저장할 때 호출됩니다.
    source 필드와 audio_url을 포함합니다.

    Args:
        request: 메시지 생성 요청

    Returns:
        생성된 메시지 정보
    """
    message_id = str(uuid4())
    source = request.source or "voice"

    # TODO: DB에 메시지 저장 및 브로드캐스트

    return PipelineMessageResponse(
        message_id=message_id,
        session_id=request.session_id,
        role=request.role,
        content=request.content,
        source=source,
        audio_url=request.audio_url
    )
