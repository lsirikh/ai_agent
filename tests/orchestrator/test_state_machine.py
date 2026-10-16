"""
Orchestrator State Machine Tests

Phase 2.2: 오케스트레이터 상태 머신 테스트
IDLE → LISTENING → PROCESSING → SPEAKING → IDLE 순환
"""
import pytest


class TestStateMachineInitialization:
    """상태 머신 초기화 테스트"""

    def test_initial_state_is_idle(self):
        """초기 상태는 IDLE이어야 한다"""
        from services.orchestrator.app.state_machine import OrchestratorStateMachine, State

        sm = OrchestratorStateMachine()

        assert sm.current_state == State.IDLE

    def test_state_machine_has_all_states(self):
        """모든 필요한 상태가 정의되어야 한다"""
        from services.orchestrator.app.state_machine import State

        assert hasattr(State, "IDLE")
        assert hasattr(State, "LISTENING")
        assert hasattr(State, "PROCESSING")
        assert hasattr(State, "SPEAKING")


class TestStateTransitions:
    """상태 전이 테스트"""

    def test_transition_idle_to_listening(self):
        """IDLE → LISTENING 전이가 가능해야 한다"""
        from services.orchestrator.app.state_machine import OrchestratorStateMachine, State

        sm = OrchestratorStateMachine()

        result = sm.transition_to(State.LISTENING)

        assert result is True
        assert sm.current_state == State.LISTENING

    def test_transition_listening_to_processing(self):
        """LISTENING → STT_PROCESSING 전이가 가능해야 한다 (Phase 32: PROCESSING→STT_PROCESSING)"""
        from services.orchestrator.app.state_machine import OrchestratorStateMachine, State

        sm = OrchestratorStateMachine()
        sm.transition_to(State.LISTENING)

        # Phase 32: LISTENING → STT_PROCESSING → LLM_PROCESSING (PROCESSING는 LLM_PROCESSING 별칭)
        result = sm.transition_to(State.STT_PROCESSING)

        assert result is True
        assert sm.current_state == State.STT_PROCESSING

    def test_transition_processing_to_speaking(self):
        """LLM_PROCESSING → TTS_PROCESSING 전이가 가능해야 한다 (Phase 32: SPEAKING→TTS_PROCESSING)"""
        from services.orchestrator.app.state_machine import OrchestratorStateMachine, State

        sm = OrchestratorStateMachine()
        sm.transition_to(State.LISTENING)
        sm.transition_to(State.STT_PROCESSING)
        sm.transition_to(State.LLM_PROCESSING)

        # Phase 32: LLM_PROCESSING → TTS_PROCESSING (SPEAKING은 TTS_PROCESSING 별칭)
        result = sm.transition_to(State.TTS_PROCESSING)

        assert result is True
        assert sm.current_state == State.TTS_PROCESSING

    def test_transition_speaking_to_idle(self):
        """TTS_PROCESSING → READY 전이가 가능해야 한다 (Phase 32: SPEAKING→TTS_PROCESSING, IDLE→READY)"""
        from services.orchestrator.app.state_machine import OrchestratorStateMachine, State

        sm = OrchestratorStateMachine()
        sm.transition_to(State.LISTENING)
        sm.transition_to(State.STT_PROCESSING)
        sm.transition_to(State.LLM_PROCESSING)
        sm.transition_to(State.TTS_PROCESSING)

        result = sm.transition_to(State.READY)

        assert result is True
        assert sm.current_state == State.READY

    def test_transition_speaking_to_listening_on_barge_in(self):
        """TTS_PROCESSING → LISTENING (Barge-in) 전이가 가능해야 한다"""
        from services.orchestrator.app.state_machine import OrchestratorStateMachine, State

        sm = OrchestratorStateMachine()
        sm.transition_to(State.LISTENING)
        sm.transition_to(State.STT_PROCESSING)
        sm.transition_to(State.LLM_PROCESSING)
        sm.transition_to(State.TTS_PROCESSING)

        # Barge-in으로 LISTENING 전이
        result = sm.handle_barge_in()

        assert result is True
        assert sm.current_state == State.LISTENING


class TestInvalidTransitions:
    """잘못된 상태 전이 테스트"""

    def test_invalid_transition_idle_to_processing(self):
        """IDLE → PROCESSING 직접 전이는 불가능해야 한다"""
        from services.orchestrator.app.state_machine import OrchestratorStateMachine, State

        sm = OrchestratorStateMachine()

        result = sm.transition_to(State.PROCESSING)

        assert result is False
        assert sm.current_state == State.IDLE

    def test_invalid_transition_idle_to_speaking(self):
        """IDLE → SPEAKING 직접 전이는 불가능해야 한다"""
        from services.orchestrator.app.state_machine import OrchestratorStateMachine, State

        sm = OrchestratorStateMachine()

        result = sm.transition_to(State.SPEAKING)

        assert result is False
        assert sm.current_state == State.IDLE


class TestListeningTimeout:
    """LISTENING 타임아웃 테스트"""

    def test_listening_timeout_returns_to_idle(self):
        """LISTENING 상태에서 타임아웃 시 IDLE로 돌아가야 한다"""
        from services.orchestrator.app.state_machine import OrchestratorStateMachine, State

        sm = OrchestratorStateMachine()
        sm.transition_to(State.LISTENING)

        # 타임아웃 처리
        result = sm.handle_timeout()

        assert result is True
        assert sm.current_state == State.IDLE

    def test_timeout_only_in_listening_state(self):
        """타임아웃은 LISTENING 상태에서만 처리되어야 한다"""
        from services.orchestrator.app.state_machine import OrchestratorStateMachine, State

        sm = OrchestratorStateMachine()
        # IDLE 상태에서 타임아웃

        result = sm.handle_timeout()

        assert result is False


class TestBargeInHandling:
    """Barge-in 처리 테스트"""

    def test_barge_in_only_in_speaking_state(self):
        """Barge-in은 SPEAKING 상태에서만 유효해야 한다"""
        from services.orchestrator.app.state_machine import OrchestratorStateMachine, State

        sm = OrchestratorStateMachine()

        # IDLE 상태에서 barge-in
        result = sm.handle_barge_in()

        assert result is False
        assert sm.current_state == State.IDLE

    def test_barge_in_from_processing(self):
        """LLM_PROCESSING 상태에서도 barge-in 가능해야 한다 (Phase 32: PROCESSING→LLM_PROCESSING)"""
        from services.orchestrator.app.state_machine import OrchestratorStateMachine, State

        sm = OrchestratorStateMachine()
        sm.transition_to(State.LISTENING)
        sm.transition_to(State.STT_PROCESSING)
        sm.transition_to(State.LLM_PROCESSING)

        result = sm.handle_barge_in()

        assert result is True
        assert sm.current_state == State.LISTENING


class TestStateCallbacks:
    """상태 변경 콜백 테스트"""

    def test_on_state_change_callback(self):
        """상태 변경 시 콜백이 호출되어야 한다"""
        from services.orchestrator.app.state_machine import OrchestratorStateMachine, State

        state_changes = []

        def on_change(old_state, new_state):
            state_changes.append((old_state, new_state))

        sm = OrchestratorStateMachine(on_state_change=on_change)
        sm.transition_to(State.LISTENING)

        assert len(state_changes) == 1
        assert state_changes[0] == (State.IDLE, State.LISTENING)

    def test_on_enter_callbacks(self):
        """특정 상태 진입 시 콜백이 호출되어야 한다"""
        from services.orchestrator.app.state_machine import OrchestratorStateMachine, State

        entered_states = []

        def on_enter_listening():
            entered_states.append("listening")

        sm = OrchestratorStateMachine()
        sm.register_on_enter(State.LISTENING, on_enter_listening)
        sm.transition_to(State.LISTENING)

        assert "listening" in entered_states


class TestPhase32StateEnumExtension:
    """Phase 32: State Enum 7개 확장 테스트"""

    def test_orchestrator_state_enum_has_off_state(self):
        """State Enum에 OFF 상태가 있어야 한다"""
        from services.orchestrator.app.state_machine import State

        assert hasattr(State, "OFF")

    def test_orchestrator_state_enum_has_ready_state(self):
        """State Enum에 READY 상태가 있어야 한다 (IDLE 대체)"""
        from services.orchestrator.app.state_machine import State

        assert hasattr(State, "READY")

    def test_orchestrator_state_enum_has_stt_processing_state(self):
        """State Enum에 STT_PROCESSING 상태가 있어야 한다"""
        from services.orchestrator.app.state_machine import State

        assert hasattr(State, "STT_PROCESSING")

    def test_orchestrator_state_enum_has_llm_processing_state(self):
        """State Enum에 LLM_PROCESSING 상태가 있어야 한다"""
        from services.orchestrator.app.state_machine import State

        assert hasattr(State, "LLM_PROCESSING")

    def test_orchestrator_state_enum_has_tts_processing_state(self):
        """State Enum에 TTS_PROCESSING 상태가 있어야 한다"""
        from services.orchestrator.app.state_machine import State

        assert hasattr(State, "TTS_PROCESSING")

    def test_orchestrator_state_enum_has_error_state(self):
        """State Enum에 ERROR 상태가 있어야 한다"""
        from services.orchestrator.app.state_machine import State

        assert hasattr(State, "ERROR")

    def test_orchestrator_state_values_match_backend_enum(self):
        """State 값이 Backend OrchestratorState와 일치해야 한다"""
        from services.orchestrator.app.state_machine import State

        # Backend enum 값과 일치하는지 확인
        assert State.OFF.value == "off"
        assert State.READY.value == "ready"
        assert State.LISTENING.value == "listening"
        assert State.STT_PROCESSING.value == "stt_processing"
        assert State.LLM_PROCESSING.value == "llm_processing"
        assert State.TTS_PROCESSING.value == "tts_processing"
        assert State.ERROR.value == "error"


class TestPhase32StateTransitions:
    """Phase 32: 새로운 상태 전이 규칙 테스트"""

    def test_state_transition_off_to_ready(self):
        """OFF → READY 전이가 가능해야 한다"""
        from services.orchestrator.app.state_machine import OrchestratorStateMachine, State

        sm = OrchestratorStateMachine()
        sm._current_state = State.OFF  # 강제 설정

        result = sm.transition_to(State.READY)

        assert result is True
        assert sm.current_state == State.READY

    def test_state_transition_ready_to_listening(self):
        """READY → LISTENING 전이가 가능해야 한다"""
        from services.orchestrator.app.state_machine import OrchestratorStateMachine, State

        sm = OrchestratorStateMachine()

        result = sm.transition_to(State.LISTENING)

        assert result is True
        assert sm.current_state == State.LISTENING

    def test_state_transition_listening_to_stt_processing(self):
        """LISTENING → STT_PROCESSING 전이가 가능해야 한다"""
        from services.orchestrator.app.state_machine import OrchestratorStateMachine, State

        sm = OrchestratorStateMachine()
        sm.transition_to(State.LISTENING)

        result = sm.transition_to(State.STT_PROCESSING)

        assert result is True
        assert sm.current_state == State.STT_PROCESSING

    def test_state_transition_stt_to_llm_processing(self):
        """STT_PROCESSING → LLM_PROCESSING 전이가 가능해야 한다"""
        from services.orchestrator.app.state_machine import OrchestratorStateMachine, State

        sm = OrchestratorStateMachine()
        sm.transition_to(State.LISTENING)
        sm.transition_to(State.STT_PROCESSING)

        result = sm.transition_to(State.LLM_PROCESSING)

        assert result is True
        assert sm.current_state == State.LLM_PROCESSING

    def test_state_transition_llm_to_tts_processing(self):
        """LLM_PROCESSING → TTS_PROCESSING 전이가 가능해야 한다"""
        from services.orchestrator.app.state_machine import OrchestratorStateMachine, State

        sm = OrchestratorStateMachine()
        sm.transition_to(State.LISTENING)
        sm.transition_to(State.STT_PROCESSING)
        sm.transition_to(State.LLM_PROCESSING)

        result = sm.transition_to(State.TTS_PROCESSING)

        assert result is True
        assert sm.current_state == State.TTS_PROCESSING

    def test_state_transition_tts_to_ready(self):
        """TTS_PROCESSING → READY 전이가 가능해야 한다"""
        from services.orchestrator.app.state_machine import OrchestratorStateMachine, State

        sm = OrchestratorStateMachine()
        sm.transition_to(State.LISTENING)
        sm.transition_to(State.STT_PROCESSING)
        sm.transition_to(State.LLM_PROCESSING)
        sm.transition_to(State.TTS_PROCESSING)

        result = sm.transition_to(State.READY)

        assert result is True
        assert sm.current_state == State.READY

    def test_state_transition_any_to_error(self):
        """모든 상태에서 ERROR로 전이 가능해야 한다"""
        from services.orchestrator.app.state_machine import OrchestratorStateMachine, State

        # READY → ERROR
        sm = OrchestratorStateMachine()
        result = sm.transition_to(State.ERROR)
        assert result is True
        assert sm.current_state == State.ERROR

    def test_state_machine_initial_state_is_ready(self):
        """StateMachine의 초기 상태는 READY여야 한다"""
        from services.orchestrator.app.state_machine import OrchestratorStateMachine, State

        sm = OrchestratorStateMachine()

        assert sm.current_state == State.READY

    def test_state_machine_can_transition_to_off(self):
        """READY → OFF 전이가 가능해야 한다"""
        from services.orchestrator.app.state_machine import OrchestratorStateMachine, State

        sm = OrchestratorStateMachine()

        result = sm.transition_to(State.OFF)

        assert result is True
        assert sm.current_state == State.OFF

    def test_state_machine_error_state_preserves_context(self):
        """ERROR 상태에서도 상태 정보를 유지해야 한다"""
        from services.orchestrator.app.state_machine import OrchestratorStateMachine, State

        sm = OrchestratorStateMachine()
        sm.transition_to(State.LISTENING)
        sm.transition_to(State.ERROR)

        info = sm.get_state_info()

        assert info["current_state"] == "ERROR"
        assert "entered_at" in info


class TestStateMetadata:
    """상태 메타데이터 테스트"""

    def test_get_state_info(self):
        """현재 상태 정보를 조회할 수 있어야 한다"""
        from services.orchestrator.app.state_machine import OrchestratorStateMachine, State

        sm = OrchestratorStateMachine()
        sm.transition_to(State.LISTENING)

        info = sm.get_state_info()

        assert info["current_state"] == "LISTENING"
        assert "entered_at" in info

    def test_state_history(self):
        """상태 변경 이력을 조회할 수 있어야 한다"""
        from services.orchestrator.app.state_machine import OrchestratorStateMachine, State

        sm = OrchestratorStateMachine()
        sm.transition_to(State.LISTENING)
        sm.transition_to(State.PROCESSING)

        history = sm.get_history()

        assert len(history) >= 2

    def test_can_transition(self):
        """전이 가능 여부를 미리 확인할 수 있어야 한다"""
        from services.orchestrator.app.state_machine import OrchestratorStateMachine, State

        sm = OrchestratorStateMachine()

        assert sm.can_transition_to(State.LISTENING) is True
        assert sm.can_transition_to(State.PROCESSING) is False
