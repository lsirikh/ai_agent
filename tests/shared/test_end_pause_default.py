"""
말 끝 판단 무음 기본값 테스트 (사용자 요청 2026-10-17: 말이 멈추고 2초 뒤 답한다)

기본값이 백엔드 설정·오케스트레이터·게이트웨이 세 곳에 따로 있어 셋 다 2초여야 한다.
"""

import os
import sys

sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "../../services/audio_gateway")
)


def test_backend_general_settings_default_is_two_seconds() -> None:
    from services.backend.app.routes.settings import GeneralSettings

    assert GeneralSettings().end_pause_seconds == 2.0


def test_orchestrator_default_is_two_seconds() -> None:
    import inspect

    from services.orchestrator.app.orchestrator import Orchestrator

    default = inspect.signature(Orchestrator.__init__).parameters["end_pause_seconds"]
    assert default.default == 2.0


def test_gateway_default_is_two_seconds() -> None:
    from app import main

    assert main.DEFAULT_END_PAUSE_SECONDS == 2.0
