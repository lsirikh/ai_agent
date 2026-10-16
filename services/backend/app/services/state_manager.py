"""
State Manager Service
Phase 18.1.2: Orchestrator 상태 관리

기능:
- Redis에 Orchestrator 상태 저장 (TTL 60초)
- 상태 변경 시 Pub/Sub으로 브로드캐스트
- 현재 상태 조회
"""
import json
from datetime import datetime
from typing import Optional, Any
from uuid import UUID

from ..constants.redis_channels import RedisChannels
from ..models.orchestrator import OrchestratorState


# Redis key constants
ORCHESTRATOR_STATE_KEY = "orchestrator:state"
STATE_TTL_SECONDS = 60

# Export DASHBOARD_UPDATES_CHANNEL for status.py compatibility
DASHBOARD_UPDATES_CHANNEL = RedisChannels.DASHBOARD_UPDATES


class StateManager:
    """
    Orchestrator 상태 관리 서비스

    Redis를 사용하여 상태를 저장하고 Pub/Sub으로 브로드캐스트
    """

    _instance: Optional["StateManager"] = None

    @classmethod
    def get_instance(cls, redis=None) -> "StateManager":
        """
        싱글톤 인스턴스 반환

        Args:
            redis: Redis client (처음 호출 시 필요)

        Returns:
            StateManager 인스턴스
        """
        if cls._instance is None:
            cls._instance = cls(redis=redis)
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """싱글톤 인스턴스 리셋 (테스트용)"""
        cls._instance = None

    def __init__(self, redis=None):
        """
        Args:
            redis: Redis client (async). None이면 연결하지 않음 (테스트용)
        """
        self._redis = redis

    async def update_state(
        self,
        state: OrchestratorState,
        session_id: Optional[UUID] = None,
        metadata: Optional[dict] = None
    ) -> None:
        """
        Orchestrator 상태 업데이트

        Args:
            state: 새 상태
            session_id: 연관된 세션 ID (선택)
            metadata: 추가 메타데이터 (선택)
        """
        if self._redis is None:
            return

        # 상태 데이터 구성
        state_data = {
            "state": state.value,
            "timestamp": datetime.utcnow().isoformat(),
        }

        if session_id:
            state_data["session_id"] = str(session_id)

        if metadata:
            state_data["metadata"] = metadata

        # JSON 직렬화
        state_json = json.dumps(state_data)

        # Redis에 저장 (TTL 60초)
        await self._redis.set(
            ORCHESTRATOR_STATE_KEY,
            state_json,
            ex=STATE_TTL_SECONDS
        )

        # Pub/Sub으로 브로드캐스트
        event_data = {
            "event": "orchestrator_state",
            "data": state_data
        }
        await self._redis.publish(
            RedisChannels.DASHBOARD_UPDATES,
            json.dumps(event_data)
        )

    async def get_current_state(self) -> Optional[dict]:
        """
        현재 Orchestrator 상태 조회

        Returns:
            상태 딕셔너리 또는 None
        """
        if self._redis is None:
            return None

        state_json = await self._redis.get(ORCHESTRATOR_STATE_KEY)

        if state_json is None:
            return {"state": OrchestratorState.OFF.value}

        # bytes인 경우 디코딩
        if isinstance(state_json, bytes):
            state_json = state_json.decode("utf-8")

        return json.loads(state_json)

    async def get_state_enum(self) -> OrchestratorState:
        """
        현재 상태를 Enum으로 반환

        Returns:
            OrchestratorState enum
        """
        state_data = await self.get_current_state()

        if state_data is None:
            return OrchestratorState.OFF

        state_value = state_data.get("state", "OFF")

        try:
            return OrchestratorState(state_value)
        except ValueError:
            return OrchestratorState.OFF


# 싱글톤 인스턴스
_state_manager: Optional[StateManager] = None


async def get_state_manager(redis=None) -> StateManager:
    """
    StateManager 인스턴스 반환

    Args:
        redis: Redis client (처음 호출 시 필요)

    Returns:
        StateManager 인스턴스
    """
    global _state_manager

    if _state_manager is None:
        _state_manager = StateManager(redis=redis)

    return _state_manager


def reset_state_manager() -> None:
    """StateManager 리셋 (테스트용)"""
    global _state_manager
    _state_manager = None
