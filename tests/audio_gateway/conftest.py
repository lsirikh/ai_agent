"""
게이트웨이 세션 전역값(_listening_mode 등)을 테스트마다 되돌린다.

몇몇 테스트가 _listening_mode=True 로 남겨 두면, 듣는 중에는 답 음성을
보내지 않는 동작 때문에 뒤에 도는 테스트가 순서에 따라 실패했다.
"""

import sys

import pytest

_SESSION_GLOBALS = ("_listening_mode", "_is_recording", "_current_session")


@pytest.fixture(autouse=True)
def _restore_gateway_session():
    main = sys.modules.get("app.main")
    saved = {
        name: getattr(main, name)
        for name in _SESSION_GLOBALS
        if main is not None and hasattr(main, name)
    }
    yield
    for name, value in saved.items():
        setattr(main, name, value)
