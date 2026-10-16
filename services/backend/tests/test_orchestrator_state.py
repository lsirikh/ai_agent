"""
Test: OrchestratorState Enum
Phase 18.1.1: Orchestrator 7개 상태 정의

TDD Red Phase: 이 테스트는 처음에 실패해야 합니다.
"""
import pytest


def test_orchestrator_state_enum_has_seven_states():
    """OrchestratorState enum이 정확히 7개의 상태를 가지는지 확인"""
    from app.models.orchestrator import OrchestratorState

    # 7개 상태가 존재해야 함
    expected_states = {"OFF", "READY", "LISTENING", "STT_PROCESSING", "LLM_PROCESSING", "TTS_PROCESSING", "ERROR"}
    actual_states = {state.value for state in OrchestratorState}

    assert actual_states == expected_states, f"Expected {expected_states}, got {actual_states}"
    assert len(OrchestratorState) == 7, f"Expected 7 states, got {len(OrchestratorState)}"


def test_orchestrator_state_enum_values_are_strings():
    """OrchestratorState enum의 값들이 문자열인지 확인"""
    from app.models.orchestrator import OrchestratorState

    for state in OrchestratorState:
        assert isinstance(state.value, str), f"State {state} value is not a string"


def test_orchestrator_state_is_str_enum():
    """OrchestratorState가 str 기반 Enum인지 확인 (JSON 직렬화 용이)"""
    from app.models.orchestrator import OrchestratorState

    # str Enum이면 직접 문자열 비교 가능
    assert OrchestratorState.READY == "READY"
    # .value로 문자열 값 접근 가능
    assert OrchestratorState.READY.value == "READY"
    # issubclass 확인
    assert issubclass(OrchestratorState, str)
