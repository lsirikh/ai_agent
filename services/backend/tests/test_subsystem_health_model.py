"""
Test: Subsystem Health Model
Phase 20.2: 서브시스템 Health 표준화

TDD Red Phase: 이 테스트는 처음에 실패해야 합니다.
"""
import pytest


def test_subsystem_health_model_exists():
    """SubsystemHealth 모델이 존재하는지 확인"""
    from app.models.health import SubsystemHealth
    assert SubsystemHealth is not None


def test_health_includes_model_info():
    """Health 모델이 model_info 필드를 포함하는지 확인"""
    from app.models.health import SubsystemHealth

    # SubsystemHealth 인스턴스 생성
    health = SubsystemHealth(
        service="stt",
        status="healthy",
        model_info={"name": "whisper", "version": "large-v3"}
    )

    assert health.model_info is not None
    assert health.model_info["name"] == "whisper"


def test_health_includes_settings():
    """Health 모델이 settings 필드를 포함하는지 확인"""
    from app.models.health import SubsystemHealth

    health = SubsystemHealth(
        service="tts",
        status="healthy",
        settings={"voice": "ko-KR", "speed": 1.0}
    )

    assert health.settings is not None
    assert health.settings["voice"] == "ko-KR"
