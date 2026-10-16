"""
Test: Logs API
Phase 21.2: 로그 수신 API

TDD Red Phase: 이 테스트는 처음에 실패해야 합니다.
"""
import pytest
from fastapi.testclient import TestClient


def test_post_logs_endpoint_exists():
    """POST /api/logs 엔드포인트가 존재하는지 확인"""
    from app.routes.logs import router

    # 라우터가 존재하는지 확인
    assert router is not None

    # POST /logs 라우트가 있는지 확인
    routes = [route.path for route in router.routes]
    assert "/" in routes or "/logs" in routes or any("log" in r for r in routes)


def test_logs_stream_endpoint_exists():
    """GET /api/logs/stream 엔드포인트가 존재하는지 확인"""
    from app.routes.logs import router, stream_logs

    # stream_logs 함수가 존재하는지 확인
    assert stream_logs is not None
    assert callable(stream_logs)
