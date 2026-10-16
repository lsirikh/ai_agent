"""
Test: Main App Router Registration
Phase 18.1.4: Orchestrator 라우터 등록

TDD Red Phase: 이 테스트는 처음에 실패해야 합니다.
"""
import pytest


def test_orchestrator_router_registered():
    """main.py에 orchestrator 라우터가 등록되어 있는지 확인"""
    from app.main import app

    # 등록된 라우터 경로 확인
    routes = [route.path for route in app.routes]

    # /api/orchestrator/state 경로가 있어야 함
    orchestrator_routes = [r for r in routes if "/api/orchestrator" in r]

    assert len(orchestrator_routes) > 0, "Orchestrator router not registered"
    assert any("/api/orchestrator/state" in r for r in orchestrator_routes)
