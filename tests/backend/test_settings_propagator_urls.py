"""
설정 전파 주소 테스트

말 끝 판단 무음(end_pause_seconds)은 오케스트레이터 → 게이트웨이로 전달된다.
전파기는 compose 가 넣지 않는 ORCHESTRATOR_SERVICE_URL 만 읽어 기본값
http://orchestrator:11007(호스트 포트)로 보냈고, 컨테이너 안에서는 연결이 실패해
설정 화면에서 값을 바꿔도 적용되지 않았다.
"""

import importlib


def _reload_with_env(monkeypatch, **env):
    for key in ("ORCHESTRATOR_SERVICE_URL", "ORCHESTRATOR_URL"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    import services.backend.app.services.settings_propagator as module

    return importlib.reload(module)


def test_should_use_orchestrator_url_set_by_compose(monkeypatch) -> None:
    module = _reload_with_env(monkeypatch, ORCHESTRATOR_URL="http://orchestrator:8007")

    assert module.SERVICE_URLS["orchestrator"] == "http://orchestrator:8007"


def test_should_default_to_container_port(monkeypatch) -> None:
    module = _reload_with_env(monkeypatch)

    assert module.SERVICE_URLS["orchestrator"] == "http://orchestrator:8007"
