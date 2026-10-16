"""
테스트 공통 설정

PipelineLogger 는 Redis 를 자동 연결하며 기본 호스트가 "redis"(compose 서비스 이름)다.
로컬 테스트에서는 그 이름의 DNS 조회가 로거마다 수 초씩 걸려 테스트가 수십 배 느려진다.
테스트 중에는 로거의 자동 연결만 끈다(REDIS_HOST 등 서비스 설정은 건드리지 않는다).
"""

import pytest


@pytest.fixture(autouse=True)
def _disable_pipeline_logger_auto_connect(monkeypatch: pytest.MonkeyPatch) -> None:
    try:
        from shared.pipeline_logger.logger import PipelineLogger
    except ImportError:
        return

    async def _no_auto_connect(self: PipelineLogger) -> None:
        return None

    monkeypatch.setattr(PipelineLogger, "_ensure_redis", _no_auto_connect)


@pytest.fixture(autouse=True)
def _disable_orchestrator_knowledge_search(monkeypatch: pytest.MonkeyPatch) -> None:
    """음성 턴의 지식 검색이 테스트마다 실제 rag:8006 이름 조회로
    수 초씩 기다리지 않게."""
    try:
        from services.orchestrator.app.orchestrator import Orchestrator
    except ImportError:
        return

    async def _no_results(self: Orchestrator, query: str) -> list:
        return []

    monkeypatch.setattr(Orchestrator, "_search_knowledge", _no_results)
