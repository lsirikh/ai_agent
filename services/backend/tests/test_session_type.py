"""
Test: Session Type Enum
Phase 18.3.1: 세션 타입 확장

TDD Red Phase: 이 테스트는 처음에 실패해야 합니다.
"""
import pytest


def test_session_type_enum_has_three_types():
    """SessionType enum이 정확히 3개의 타입을 가지는지 확인"""
    from app.models.session import SessionType

    # 3개 타입이 존재해야 함
    expected_types = {"web", "voice", "unified"}
    actual_types = {t.value for t in SessionType}

    assert actual_types == expected_types, f"Expected {expected_types}, got {actual_types}"
    assert len(SessionType) == 3, f"Expected 3 types, got {len(SessionType)}"


def test_session_type_is_str_enum():
    """SessionType이 str 기반 Enum인지 확인"""
    from app.models.session import SessionType

    assert SessionType.WEB == "web"
    assert SessionType.VOICE == "voice"
    assert SessionType.UNIFIED == "unified"
    assert issubclass(SessionType, str)
