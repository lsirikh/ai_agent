"""
Orchestrator State Machine

Phase 2.2: 오케스트레이터 상태 관리
IDLE → LISTENING → PROCESSING → SPEAKING → IDLE 순환
"""
from datetime import datetime
from enum import Enum, auto
from typing import Any, Callable, Optional


class State(str, Enum):
    """
    오케스트레이터 상태 (Phase 32: 7개 상태로 확장)

    Backend OrchestratorState와 동일한 값 사용
    """
    OFF = "off"                      # 서비스 비활성화
    READY = "ready"                  # 대기 상태 (구 IDLE)
    LISTENING = "listening"          # 음성 입력 수신 중
    STT_PROCESSING = "stt_processing"  # STT 처리 중 (구 PROCESSING 분리)
    LLM_PROCESSING = "llm_processing"  # LLM 처리 중 (구 PROCESSING 분리)
    TTS_PROCESSING = "tts_processing"  # TTS 출력 중 (구 SPEAKING)
    ERROR = "error"                  # 에러 상태

    # 레거시 호환 별칭 (deprecated, 향후 제거 예정)
    IDLE = "ready"                   # READY 별칭 (레거시 호환)
    PROCESSING = "llm_processing"    # LLM_PROCESSING 별칭 (레거시 호환)
    SPEAKING = "tts_processing"      # TTS_PROCESSING 별칭 (레거시 호환)


class OrchestratorStateMachine:
    """
    오케스트레이터 상태 머신 (Phase 32: 7개 상태 시스템)

    상태 전이 규칙:
    - OFF → READY: 서비스 활성화
    - READY → LISTENING: Wake word 감지 또는 수동 활성화
    - READY → OFF: 서비스 비활성화
    - READY → ERROR: 에러 발생
    - LISTENING → STT_PROCESSING: 음성 입력 완료
    - LISTENING → READY: 타임아웃
    - LISTENING → ERROR: 에러 발생
    - STT_PROCESSING → LLM_PROCESSING: STT 완료
    - STT_PROCESSING → READY: 취소
    - STT_PROCESSING → LISTENING: Barge-in
    - STT_PROCESSING → ERROR: 에러 발생
    - LLM_PROCESSING → TTS_PROCESSING: 첫 문장 생성 완료
    - LLM_PROCESSING → LISTENING: Barge-in
    - LLM_PROCESSING → READY: 취소
    - LLM_PROCESSING → ERROR: 에러 발생
    - TTS_PROCESSING → READY: 모든 문장 출력 완료
    - TTS_PROCESSING → LISTENING: Barge-in
    - TTS_PROCESSING → ERROR: 에러 발생
    - ERROR → READY: 에러 복구

    Attributes:
        current_state: 현재 상태
        on_state_change: 상태 변경 콜백
    """

    # 유효한 상태 전이 정의 (Phase 32: 7개 상태 시스템)
    VALID_TRANSITIONS = {
        State.OFF: [State.READY, State.ERROR],
        State.READY: [State.LISTENING, State.OFF, State.ERROR],
        State.LISTENING: [State.STT_PROCESSING, State.READY, State.ERROR],
        State.STT_PROCESSING: [State.LLM_PROCESSING, State.READY, State.LISTENING, State.ERROR],
        State.LLM_PROCESSING: [State.TTS_PROCESSING, State.LISTENING, State.READY, State.ERROR],
        State.TTS_PROCESSING: [State.READY, State.LISTENING, State.ERROR],
        State.ERROR: [State.READY, State.OFF],
        # 레거시 호환 (IDLE, PROCESSING, SPEAKING은 READY, LLM_PROCESSING, TTS_PROCESSING과 동일)
        State.IDLE: [State.LISTENING, State.OFF, State.ERROR],
        State.PROCESSING: [State.TTS_PROCESSING, State.LISTENING, State.READY, State.ERROR],
        State.SPEAKING: [State.READY, State.LISTENING, State.ERROR],
    }

    def __init__(
        self,
        on_state_change: Optional[Callable[[State, State], None]] = None
    ):
        """
        상태 머신 초기화

        Args:
            on_state_change: 상태 변경 시 호출되는 콜백 (old_state, new_state)
        """
        self._current_state = State.READY  # Phase 32: 초기 상태를 READY로 변경
        self._entered_at = datetime.now()
        self._history: list[dict[str, Any]] = []
        self._on_state_change = on_state_change
        # 새로운 상태들에 대한 콜백 등록을 위해 고유 상태만 사용
        unique_states = [State.OFF, State.READY, State.LISTENING,
                         State.STT_PROCESSING, State.LLM_PROCESSING,
                         State.TTS_PROCESSING, State.ERROR]
        self._on_enter_callbacks: dict[State, list[Callable]] = {s: [] for s in unique_states}

        # 초기 상태 기록
        self._record_transition(None, State.IDLE)

    @property
    def current_state(self) -> State:
        """현재 상태 반환"""
        return self._current_state

    def can_transition_to(self, target_state: State) -> bool:
        """
        특정 상태로 전이 가능한지 확인

        Args:
            target_state: 전이하려는 상태

        Returns:
            전이 가능 여부
        """
        valid_targets = self.VALID_TRANSITIONS.get(self._current_state, [])
        return target_state in valid_targets

    def transition_to(self, target_state: State) -> bool:
        """
        특정 상태로 전이

        Args:
            target_state: 전이하려는 상태

        Returns:
            전이 성공 여부
        """
        if not self.can_transition_to(target_state):
            return False

        old_state = self._current_state
        self._current_state = target_state
        self._entered_at = datetime.now()

        # 이력 기록
        self._record_transition(old_state, target_state)

        # 콜백 호출
        if self._on_state_change:
            self._on_state_change(old_state, target_state)

        # on_enter 콜백 호출
        for callback in self._on_enter_callbacks.get(target_state, []):
            callback()

        return True

    def handle_barge_in(self) -> bool:
        """
        Barge-in 이벤트 처리

        STT_PROCESSING, LLM_PROCESSING, TTS_PROCESSING 상태에서만 유효
        (레거시: SPEAKING, PROCESSING도 지원)

        Returns:
            처리 성공 여부
        """
        barge_in_states = [
            State.STT_PROCESSING, State.LLM_PROCESSING, State.TTS_PROCESSING,
            State.SPEAKING, State.PROCESSING  # 레거시 호환
        ]
        if self._current_state in barge_in_states:
            return self.transition_to(State.LISTENING)
        return False

    def handle_timeout(self) -> bool:
        """
        타임아웃 이벤트 처리

        LISTENING 상태에서만 유효

        Returns:
            처리 성공 여부
        """
        if self._current_state == State.LISTENING:
            return self.transition_to(State.IDLE)
        return False

    def register_on_enter(self, state: State, callback: Callable) -> None:
        """
        특정 상태 진입 시 호출될 콜백 등록

        Args:
            state: 대상 상태
            callback: 콜백 함수
        """
        self._on_enter_callbacks[state].append(callback)

    def get_state_info(self) -> dict[str, Any]:
        """
        현재 상태 정보 반환

        Returns:
            상태 정보 딕셔너리
        """
        return {
            "current_state": self._current_state.name,
            "entered_at": self._entered_at.isoformat(),
            "duration_seconds": (datetime.now() - self._entered_at).total_seconds()
        }

    def get_history(self, limit: int = 10) -> list[dict[str, Any]]:
        """
        상태 변경 이력 반환

        Args:
            limit: 반환할 최대 이력 수

        Returns:
            상태 변경 이력 리스트
        """
        return self._history[-limit:]

    def _record_transition(self, from_state: Optional[State], to_state: State) -> None:
        """상태 전이 기록"""
        self._history.append({
            "from": from_state.name if from_state else None,
            "to": to_state.name,
            "timestamp": datetime.now().isoformat()
        })

        # 이력 크기 제한
        if len(self._history) > 100:
            self._history = self._history[-50:]

    def reset(self) -> None:
        """상태 머신 초기화 (IDLE로 리셋)"""
        old_state = self._current_state
        self._current_state = State.IDLE
        self._entered_at = datetime.now()
        self._record_transition(old_state, State.IDLE)

        if self._on_state_change:
            self._on_state_change(old_state, State.IDLE)
