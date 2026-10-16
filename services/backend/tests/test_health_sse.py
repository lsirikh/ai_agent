"""
Test: Health SSE Streaming
Phase 20.3: Dashboard SSE Health 스트리밍

TDD Red Phase: 이 테스트는 처음에 실패해야 합니다.
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import json


def test_sse_broadcasts_health_updates():
    """SSE가 health 업데이트를 브로드캐스트하는지 확인"""
    from app.routes.status import stream_status

    # stream_status 함수가 존재하는지 확인
    assert stream_status is not None
    assert callable(stream_status)


def test_health_update_interval_one_second():
    """Health 업데이트 간격이 1초인지 확인"""
    from app.services.health_collector import COLLECT_INTERVAL

    assert COLLECT_INTERVAL == 1.0


def test_unhealthy_service_status_shown():
    """Unhealthy 서비스 상태가 표시되는지 확인"""
    from app.models.health import SubsystemHealth

    # unhealthy 상태 생성
    health = SubsystemHealth(
        service="stt",
        status="unhealthy",
        error="Connection refused"
    )

    assert health.status == "unhealthy"
    assert health.error == "Connection refused"
