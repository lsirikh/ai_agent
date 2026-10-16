"""
Test: Health Collector
Phase 20.1: HealthCollector 백그라운드 서비스

TDD Red Phase: 이 테스트는 처음에 실패해야 합니다.
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import asyncio


def test_health_collector_class_exists():
    """HealthCollector 클래스가 존재하는지 확인"""
    from app.services.health_collector import HealthCollector
    assert HealthCollector is not None


def test_health_collector_collects_all_services():
    """HealthCollector가 모든 서비스의 health를 수집하는지 확인"""
    from app.services.health_collector import HealthCollector

    collector = HealthCollector()

    # 수집 대상 서비스 목록이 있어야 함
    assert hasattr(collector, "service_urls") or hasattr(collector, "services")

    # collect_all 메서드가 있어야 함
    assert hasattr(collector, "collect_all"), "HealthCollector에 collect_all 메서드가 없습니다"


@pytest.mark.asyncio
async def test_health_collector_collect_returns_dict():
    """collect_all이 서비스별 health 딕셔너리를 반환하는지 확인"""
    from app.services.health_collector import HealthCollector

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "healthy",
            "service": "stt"
        }
        mock_client.get.return_value = mock_response

        collector = HealthCollector()
        result = await collector.collect_all()

        # 결과가 딕셔너리여야 함
        assert isinstance(result, dict)


@pytest.mark.asyncio
async def test_health_collector_handles_timeout():
    """HealthCollector가 타임아웃을 처리하는지 확인"""
    from app.services.health_collector import HealthCollector
    import httpx

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        # 타임아웃 예외 발생
        mock_client.get.side_effect = httpx.TimeoutException("Timeout")

        collector = HealthCollector()
        result = await collector.collect_all()

        # 타임아웃 시에도 결과가 반환되어야 함 (unhealthy 상태)
        assert isinstance(result, dict)
