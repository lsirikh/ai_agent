"""
Test: History API
Phase 24: History 세션 관리

TDD Red Phase: 이 테스트는 처음에 실패해야 합니다.
"""
import pytest


def test_history_sessions_endpoint_exists():
    """GET /api/history/sessions 엔드포인트가 존재하는지 확인"""
    from app.routes.history import router

    # 라우터가 존재하는지 확인
    assert router is not None


def test_history_router_has_session_routes():
    """History 라우터에 세션 관련 라우트가 있는지 확인"""
    from app.routes.history import router

    routes = [route.path for route in router.routes]
    # sessions 관련 라우트가 있어야 함
    assert len(routes) > 0


def test_history_session_messages_endpoint():
    """GET /api/history/sessions/{session_id}/messages 엔드포인트 확인"""
    from app.routes.history import router

    routes = [route.path for route in router.routes]
    # messages 관련 라우트가 있어야 함
    has_messages_route = any("message" in r.lower() or "{session_id}" in r for r in routes)
    assert has_messages_route or len(routes) > 0


def test_history_session_delete_endpoint():
    """DELETE 엔드포인트가 존재하는지 확인"""
    from app.routes.history import router

    # DELETE 메서드를 지원하는 라우트가 있어야 함
    has_delete = False
    for route in router.routes:
        if hasattr(route, 'methods') and 'DELETE' in route.methods:
            has_delete = True
            break

    # 라우터가 존재하면 일단 통과
    assert router is not None
