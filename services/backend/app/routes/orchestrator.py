"""
Orchestrator Routes
Phase 18.1.3: Orchestrator 상태 수신 API

엔드포인트:
- POST /api/orchestrator/state: Orchestrator 상태 업데이트
- GET /api/orchestrator/state: 현재 상태 조회
"""
import json
import time
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..models.orchestrator import OrchestratorState
from ..services.state_manager import StateManager, get_state_manager


router = APIRouter(
    prefix="/api/orchestrator",
    tags=["orchestrator"]
)


class StateUpdateRequest(BaseModel):
    """상태 업데이트 요청 모델"""
    state: OrchestratorState
    session_id: Optional[str] = None
    metadata: Optional[dict] = None


class StateUpdateResponse(BaseModel):
    """상태 업데이트 응답 모델"""
    status: str = "ok"


class StateResponse(BaseModel):
    """현재 상태 응답 모델"""
    state: str
    session_id: Optional[str] = None
    metadata: Optional[dict] = None
    timestamp: Optional[str] = None


# Redis client - lifespan에서 주입됨
_redis_client = None
_state_manager: Optional[StateManager] = None


def set_redis_client(redis):
    """Redis 클라이언트 설정 (lifespan에서 호출)"""
    global _redis_client, _state_manager
    _redis_client = redis
    _state_manager = StateManager.get_instance(redis=redis)


async def get_state_manager_instance() -> StateManager:
    """StateManager 인스턴스 반환"""
    global _state_manager
    if _state_manager is None:
        _state_manager = StateManager.get_instance(redis=_redis_client)
    return _state_manager


# 앱의 [중단] 버튼 — 오케스트레이터·게이트웨이가 구독한다
VOICE_STOP_CHANNEL = "edgevoice:voice:stop"


@router.post("/stop")
async def stop_voice():
    """
    말하는 도중 멈추기(사용자 요청 2026-10-18: '말을 한번 시작하면 중단을 못 해').
    오케스트레이터는 답을 멈추고 대기로, 게이트웨이는 남은 답 음성을 버린다.
    """
    from ..services import conversation

    event = {"type": "stop", "source": "button", "timestamp": time.time()}
    await conversation._get_redis().publish(VOICE_STOP_CHANNEL, json.dumps(event))
    return {"status": "stopping"}


# '헤이 자비스' 감지와 같은 채널 — 오케스트레이터는 듣기로, 게이트웨이는 녹음을 시작한다
WAKE_WORD_CHANNEL = "edgevoice:wake_word:detected"


@router.post("/listen")
async def start_listening():
    """앱의 파형을 눌러 듣기 시작(사용자 요청 2026-10-19: 호출어 없이 누르면 입력)."""
    from ..services import conversation

    event = {
        "type": "wake_word_detected",
        "wake_word": "button",
        "confidence": 1.0,
        "source": "button",
        "timestamp": time.time(),
    }
    await conversation._get_redis().publish(WAKE_WORD_CHANNEL, json.dumps(event))
    return {"status": "listening"}


@router.post("/state", response_model=StateUpdateResponse)
async def update_orchestrator_state(request: StateUpdateRequest):
    """
    Orchestrator 상태 업데이트

    Orchestrator가 상태 변경 시 이 엔드포인트를 호출하여
    Backend에 알립니다.

    상태는 Redis에 저장되고 SSE로 연결된 클라이언트에 브로드캐스트됩니다.
    """
    manager = await get_state_manager_instance()

    session_uuid = None
    if request.session_id:
        try:
            session_uuid = UUID(request.session_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid session_id format")

    await manager.update_state(
        state=request.state,
        session_id=session_uuid,
        metadata=request.metadata
    )

    return StateUpdateResponse(status="ok")


@router.get("/state", response_model=StateResponse)
async def get_orchestrator_state():
    """
    현재 Orchestrator 상태 조회

    Returns:
        현재 상태 정보
    """
    manager = await get_state_manager_instance()
    state_data = await manager.get_current_state()

    if state_data is None:
        return StateResponse(state=OrchestratorState.OFF.value)

    return StateResponse(
        state=state_data.get("state", OrchestratorState.OFF.value),
        session_id=state_data.get("session_id"),
        metadata=state_data.get("metadata"),
        timestamp=state_data.get("timestamp")
    )
