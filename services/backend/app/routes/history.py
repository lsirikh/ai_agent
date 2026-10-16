"""
Backend API Chat History Router

Phase 5.4: Chat History 관리 API
"""
import csv
import io
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from ..repositories import MessageRepository, SessionRepository
from ..services import conversation

router = APIRouter(prefix="/api/history", tags=["history"])


# ===== Pydantic Models =====

class Message(BaseModel):
    """메시지"""
    id: str
    session_id: str
    role: str  # "user" | "assistant" | "system"
    content: str
    timestamp: str
    source: Optional[str] = None  # "web" | "voice" | "api"


class MessageCreate(BaseModel):
    """메시지 생성 요청"""
    session_id: str
    role: str = Field(default="user")
    content: str


class MessageResponse(BaseModel):
    """메시지 생성 응답"""
    id: str
    session_id: str
    role: str
    content: str
    timestamp: str


class HistoryResponse(BaseModel):
    """대화 기록 응답"""
    messages: List[Message]
    total: int = 0


class SessionInfo(BaseModel):
    """세션 정보"""
    session_id: str
    created_at: str
    message_count: int


class SessionListResponse(BaseModel):
    """세션 목록 응답"""
    sessions: List[SessionInfo]


class DeleteResponse(BaseModel):
    """삭제 응답"""
    deleted: bool


class ExportResponse(BaseModel):
    """내보내기 응답"""
    messages: List[Message]
    exported_at: str


# ===== In-memory History Store =====

class HistoryStore:
    """대화 기록 저장소 (In-memory)"""

    def __init__(self):
        self._messages: List[Dict[str, Any]] = []
        self._sessions: Dict[str, Dict[str, Any]] = {}

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str
    ) -> str:
        """메시지 추가"""
        msg_id = f"msg-{uuid.uuid4().hex[:8]}"
        timestamp = datetime.now().isoformat()

        message = {
            "id": msg_id,
            "session_id": session_id,
            "role": role,
            "content": content,
            "timestamp": timestamp
        }

        self._messages.append(message)

        # 세션 정보 업데이트
        if session_id not in self._sessions:
            self._sessions[session_id] = {
                "session_id": session_id,
                "created_at": timestamp,
                "message_count": 0
            }
        self._sessions[session_id]["message_count"] += 1

        return msg_id

    def get_messages(
        self,
        session_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """메시지 조회"""
        messages = self._messages

        if session_id:
            messages = [m for m in messages if m["session_id"] == session_id]

        # 최신순 정렬
        messages = sorted(messages, key=lambda x: x["timestamp"], reverse=True)

        # 페이지네이션
        return messages[offset:offset + limit]

    def list_sessions(self) -> List[Dict[str, Any]]:
        """세션 목록 조회"""
        return list(self._sessions.values())

    def clear_session(self, session_id: str) -> bool:
        """특정 세션 삭제"""
        self._messages = [m for m in self._messages if m["session_id"] != session_id]
        if session_id in self._sessions:
            del self._sessions[session_id]
            return True
        return False

    def clear_all(self) -> bool:
        """전체 기록 삭제"""
        self._messages = []
        self._sessions = {}
        return True


# ===== Global Store Instance =====

_history_store: Optional[HistoryStore] = None


def get_history_store() -> HistoryStore:
    """히스토리 저장소 인스턴스 반환"""
    global _history_store
    if _history_store is None:
        _history_store = HistoryStore()
    return _history_store


# ===== Postgres (DB 가 연결돼 있으면 이쪽, 없으면 메모리 저장소) =====

def _to_history_message(message: Dict[str, Any]) -> Dict[str, Any]:
    public = conversation.to_public(message)
    return {
        "id": public["id"],
        "session_id": public["session_id"],
        "role": public["role"],
        "content": public["content"],
        "timestamp": public["created_at"],
        "source": public["source"],
    }


async def _db_messages(
    session_id: Optional[str], limit: int, offset: int
) -> List[Dict[str, Any]]:
    """최신순 메시지."""
    if session_id:
        try:
            rows = await MessageRepository().get_by_session(uuid.UUID(session_id))
        except ValueError:
            return []
        rows = list(reversed(rows))[offset:offset + limit]
    else:
        rows = await MessageRepository().list_recent(limit=limit, offset=offset)
    return [_to_history_message(m) for m in rows]


# ===== API Endpoints =====

@router.get("", response_model=HistoryResponse)
async def get_history(
    session_id: Optional[str] = Query(None, description="세션 ID로 필터링"),
    limit: int = Query(100, ge=1, le=1000, description="최대 반환 수"),
    offset: int = Query(0, ge=0, description="시작 위치")
):
    """
    대화 기록 조회

    Args:
        session_id: 세션 ID (선택)
        limit: 최대 반환 수
        offset: 시작 위치

    Returns:
        대화 기록
    """
    if conversation.is_available():
        messages = await _db_messages(session_id, limit, offset)
    else:
        messages = get_history_store().get_messages(
            session_id=session_id, limit=limit, offset=offset
        )

    return HistoryResponse(
        messages=[Message(**m) for m in messages],
        total=len(messages)
    )


@router.get("/sessions", response_model=SessionListResponse)
async def list_sessions():
    """
    세션 목록 조회

    Returns:
        세션 목록
    """
    if conversation.is_available():
        repo = MessageRepository()
        sessions = [
            {
                "session_id": str(s["id"]),
                "created_at": s["created_at"].isoformat(),
                "message_count": await repo.count_by_session(s["id"]),
            }
            for s in await SessionRepository().list_recent(limit=100)
        ]
    else:
        sessions = get_history_store().list_sessions()

    return SessionListResponse(
        sessions=[SessionInfo(**s) for s in sessions]
    )


@router.post("/messages", response_model=MessageResponse)
async def add_message(message: MessageCreate):
    """
    메시지 추가

    Args:
        message: 추가할 메시지

    Returns:
        추가된 메시지
    """
    if conversation.is_available():
        session_id = await conversation.resolve_session_id(message.session_id)
        saved = await conversation.save_message(
            session_id, message.role, message.content, source="api"
        )
        return MessageResponse(
            id=saved["id"],
            session_id=session_id,
            role=saved["role"],
            content=saved["content"],
            timestamp=saved["created_at"]
        )

    store = get_history_store()
    msg_id = store.add_message(
        session_id=message.session_id,
        role=message.role,
        content=message.content
    )

    # 방금 추가한 메시지 조회
    messages = store.get_messages(session_id=message.session_id, limit=1)
    if messages:
        return MessageResponse(**messages[0])

    return MessageResponse(
        id=msg_id,
        session_id=message.session_id,
        role=message.role,
        content=message.content,
        timestamp=datetime.now().isoformat()
    )


@router.get("/export")
async def export_history(
    format: str = Query("json", description="내보내기 형식 (json, csv)"),
    session_id: Optional[str] = Query(None, description="세션 ID로 필터링")
):
    """
    대화 기록 내보내기

    Args:
        format: 내보내기 형식 (json, csv)
        session_id: 세션 ID (선택)

    Returns:
        내보낸 대화 기록
    """
    if format not in ["json", "csv"]:
        raise HTTPException(status_code=400, detail=f"지원하지 않는 형식입니다: {format}")

    if conversation.is_available():
        messages = await _db_messages(session_id, 10000, 0)
    else:
        messages = get_history_store().get_messages(session_id=session_id, limit=10000)

    if format == "json":
        return JSONResponse(
            content={
                "messages": messages,
                "exported_at": datetime.now().isoformat()
            },
            media_type="application/json"
        )
    else:  # csv
        output = io.StringIO()
        writer = csv.DictWriter(
            output,
            fieldnames=["id", "session_id", "role", "content", "timestamp"],
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(messages)

        output.seek(0)
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=history.csv"}
        )


@router.delete("/sessions/{session_id}", response_model=DeleteResponse)
async def clear_session_history(session_id: str):
    """
    특정 세션의 대화 기록 삭제

    Args:
        session_id: 삭제할 세션 ID

    Returns:
        삭제 결과
    """
    if conversation.is_available():
        try:
            deleted = await SessionRepository().delete(uuid.UUID(session_id))
            return DeleteResponse(deleted=deleted)
        except ValueError:
            return DeleteResponse(deleted=False)

    store = get_history_store()
    result = store.clear_session(session_id)

    return DeleteResponse(deleted=result)


@router.delete("/all", response_model=DeleteResponse)
async def clear_all_history():
    """
    전체 대화 기록 삭제

    Returns:
        삭제 결과
    """
    if conversation.is_available():
        repo = SessionRepository()
        for s in await repo.list_recent(limit=100000):
            await repo.delete(s["id"])
        return DeleteResponse(deleted=True)

    store = get_history_store()
    result = store.clear_all()

    return DeleteResponse(deleted=result)
