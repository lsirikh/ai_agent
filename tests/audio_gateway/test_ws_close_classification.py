"""
WebSocket 종료 분류 테스트

앱 종료(1005)·정상 종료(1000)·서비스 재시작(1012) 같은 정상 종료가
ERROR 'websocket_receive_error' 로 찍혀 대시보드에 버그처럼 보였다.
"""

import os
import sys

import pytest
from starlette.websockets import WebSocketDisconnect

sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "../../services/audio_gateway")
)


@pytest.mark.parametrize("code", [1000, 1001, 1005, 1012])
def test_should_treat_routine_close_codes_as_normal(code: int) -> None:
    from app import main

    assert main.is_normal_close(WebSocketDisconnect(code=code)) is True


@pytest.mark.parametrize(
    "error", [WebSocketDisconnect(code=1011), RuntimeError("boom"), ValueError("bad")]
)
def test_should_treat_other_failures_as_errors(error: Exception) -> None:
    from app import main

    assert main.is_normal_close(error) is False
