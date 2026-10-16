"""
Phase 32.4: Legacy Code Compatibility Tests

Tests that the new 7-state system maintains backward compatibility
with the old 4-state names (IDLE, PROCESSING, SPEAKING).
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestReadyStateBehavesLikeIdle:
    """READY 상태가 IDLE처럼 동작하는지 테스트"""

    def test_ready_state_behaves_like_idle(self):
        """READY 상태가 IDLE과 동일한 동작을 해야 한다"""
        from services.orchestrator.app.state_machine import OrchestratorStateMachine, State

        sm = OrchestratorStateMachine()

        # 초기 상태는 READY
        assert sm.current_state == State.READY

        # READY에서 LISTENING으로 전이 가능
        assert sm.can_transition_to(State.LISTENING)
        result = sm.transition_to(State.LISTENING)
        assert result is True
        assert sm.current_state == State.LISTENING

    def test_idle_alias_points_to_ready(self):
        """IDLE은 READY의 별칭이어야 한다"""
        from services.orchestrator.app.state_machine import State

        # IDLE과 READY의 값이 같은지 확인
        assert State.IDLE.value == State.READY.value
        assert State.IDLE.value == "ready"

    def test_timeout_returns_to_idle_or_ready(self):
        """타임아웃 시 IDLE/READY로 돌아가야 한다"""
        from services.orchestrator.app.state_machine import OrchestratorStateMachine, State

        sm = OrchestratorStateMachine()
        sm.transition_to(State.LISTENING)

        result = sm.handle_timeout()

        assert result is True
        # IDLE과 READY는 같은 값이므로 둘 다 허용
        assert sm.current_state.value == "ready"


class TestProcessingStateRemoved:
    """PROCESSING 상태가 STT/LLM으로 분리되었는지 테스트"""

    def test_old_processing_state_is_alias(self):
        """PROCESSING은 LLM_PROCESSING의 별칭이어야 한다"""
        from services.orchestrator.app.state_machine import State

        assert State.PROCESSING.value == State.LLM_PROCESSING.value
        assert State.PROCESSING.value == "llm_processing"

    def test_processing_logic_uses_new_states(self):
        """처리 로직이 새로운 상태를 사용해야 한다"""
        from services.orchestrator.app.state_machine import OrchestratorStateMachine, State

        sm = OrchestratorStateMachine()
        sm.transition_to(State.LISTENING)

        # STT_PROCESSING → LLM_PROCESSING 흐름
        result1 = sm.transition_to(State.STT_PROCESSING)
        assert result1 is True
        assert sm.current_state == State.STT_PROCESSING

        result2 = sm.transition_to(State.LLM_PROCESSING)
        assert result2 is True
        assert sm.current_state == State.LLM_PROCESSING

    def test_stt_processing_exists(self):
        """STT_PROCESSING 상태가 존재해야 한다"""
        from services.orchestrator.app.state_machine import State

        assert hasattr(State, "STT_PROCESSING")
        assert State.STT_PROCESSING.value == "stt_processing"

    def test_llm_processing_exists(self):
        """LLM_PROCESSING 상태가 존재해야 한다"""
        from services.orchestrator.app.state_machine import State

        assert hasattr(State, "LLM_PROCESSING")
        assert State.LLM_PROCESSING.value == "llm_processing"


class TestTTSProcessingReplacesSpeaking:
    """TTS_PROCESSING이 SPEAKING을 대체했는지 테스트"""

    def test_tts_processing_replaces_speaking(self):
        """TTS_PROCESSING이 SPEAKING을 대체해야 한다"""
        from services.orchestrator.app.state_machine import State

        assert hasattr(State, "TTS_PROCESSING")
        assert State.TTS_PROCESSING.value == "tts_processing"

    def test_speaking_alias_points_to_tts_processing(self):
        """SPEAKING은 TTS_PROCESSING의 별칭이어야 한다"""
        from services.orchestrator.app.state_machine import State

        assert State.SPEAKING.value == State.TTS_PROCESSING.value
        assert State.SPEAKING.value == "tts_processing"

    def test_barge_in_works_with_tts_processing(self):
        """Barge-in이 TTS_PROCESSING 상태에서 동작해야 한다"""
        from services.orchestrator.app.state_machine import OrchestratorStateMachine, State

        sm = OrchestratorStateMachine()
        sm.transition_to(State.LISTENING)
        sm.transition_to(State.STT_PROCESSING)
        sm.transition_to(State.LLM_PROCESSING)
        sm.transition_to(State.TTS_PROCESSING)

        assert sm.current_state == State.TTS_PROCESSING

        result = sm.handle_barge_in()

        assert result is True
        assert sm.current_state == State.LISTENING


class TestLegacyStateComparison:
    """레거시 상태 비교 테스트"""

    def test_can_compare_idle_with_ready(self):
        """IDLE과 READY를 비교할 수 있어야 한다"""
        from services.orchestrator.app.state_machine import OrchestratorStateMachine, State

        sm = OrchestratorStateMachine()

        # IDLE과 READY는 같은 값
        assert sm.current_state.value == State.IDLE.value
        assert sm.current_state.value == State.READY.value

    def test_can_check_state_in_list(self):
        """상태를 리스트에서 확인할 수 있어야 한다"""
        from services.orchestrator.app.state_machine import OrchestratorStateMachine, State

        sm = OrchestratorStateMachine()
        sm.transition_to(State.LISTENING)
        sm.transition_to(State.STT_PROCESSING)
        sm.transition_to(State.LLM_PROCESSING)
        sm.transition_to(State.TTS_PROCESSING)

        # 레거시와 새 상태 모두 리스트에서 확인
        valid_states = [State.TTS_PROCESSING, State.SPEAKING]
        assert sm.current_state in valid_states

    def test_legacy_state_valid_transitions_work(self):
        """레거시 상태에서도 전이가 동작해야 한다"""
        from services.orchestrator.app.state_machine import OrchestratorStateMachine, State

        sm = OrchestratorStateMachine()

        # IDLE(=READY)에서 LISTENING으로 전이
        sm._current_state = State.IDLE
        result = sm.transition_to(State.LISTENING)
        assert result is True

        # LISTENING에서 PROCESSING(=LLM_PROCESSING)으로 전이
        sm._current_state = State.LISTENING
        sm.transition_to(State.STT_PROCESSING)  # 먼저 STT_PROCESSING을 거쳐야 함
        result = sm.transition_to(State.PROCESSING)
        assert result is True

        # PROCESSING(=LLM_PROCESSING)에서 SPEAKING(=TTS_PROCESSING)으로 전이
        result = sm.transition_to(State.SPEAKING)
        assert result is True


class TestOrchestratorLegacyCompatibility:
    """Orchestrator 클래스의 레거시 호환성 테스트"""

    @pytest.mark.asyncio
    async def test_orchestrator_accepts_legacy_state_checks(self):
        """Orchestrator가 레거시 상태 검사를 수용해야 한다"""
        from services.orchestrator.app.orchestrator import Orchestrator
        from services.orchestrator.app.state_machine import State

        with patch.object(Orchestrator, "_setup_redis", return_value=AsyncMock()):
            orchestrator = Orchestrator()

            # IDLE/READY 상태에서 wake word 처리 가능
            assert orchestrator.state_machine.current_state in [State.IDLE, State.READY]

            await orchestrator.handle_wake_word()

            assert orchestrator.state_machine.current_state == State.LISTENING

    @pytest.mark.asyncio
    async def test_orchestrator_handle_speaking_complete_works(self):
        """handle_speaking_complete가 TTS_PROCESSING 상태에서 동작해야 한다"""
        from services.orchestrator.app.orchestrator import Orchestrator
        from services.orchestrator.app.state_machine import State

        with patch.object(Orchestrator, "_setup_redis", return_value=AsyncMock()):
            orchestrator = Orchestrator()
            orchestrator.state_machine.transition_to(State.LISTENING)
            orchestrator.state_machine.transition_to(State.STT_PROCESSING)
            orchestrator.state_machine.transition_to(State.LLM_PROCESSING)
            orchestrator.state_machine.transition_to(State.TTS_PROCESSING)

            result = await orchestrator.handle_speaking_complete()

            assert result is True
            # READY 또는 IDLE(=READY의 별칭)
            assert orchestrator.state_machine.current_state.value == "ready"
