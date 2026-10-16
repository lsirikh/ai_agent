"""
Test: Extended Health Model
Phase 18.5: Health 정보 확장

TDD Red Phase: 이 테스트는 처음에 실패해야 합니다.
"""
import pytest


def test_extended_health_model_exists():
    """ExtendedHealthResponse 모델이 존재하는지 확인"""
    from app.models.health import ExtendedHealthResponse
    assert ExtendedHealthResponse is not None


def test_health_response_includes_model_info():
    """Health 응답에 model_info 필드가 포함되는지 확인"""
    from app.models.health import ExtendedHealthResponse

    # 모델 필드 확인
    fields = ExtendedHealthResponse.model_fields
    assert "model_info" in fields, "ExtendedHealthResponse에 model_info 필드가 없습니다"


def test_health_response_includes_settings():
    """Health 응답에 settings 필드가 포함되는지 확인"""
    from app.models.health import ExtendedHealthResponse

    # 모델 필드 확인
    fields = ExtendedHealthResponse.model_fields
    assert "settings" in fields, "ExtendedHealthResponse에 settings 필드가 없습니다"


def test_services_endpoint_returns_extended_health():
    """GET /api/status/services가 확장된 health 정보를 반환하는지 확인"""
    from app.routes.status import router

    # 라우터에서 /services 경로 확인
    routes = [route.path for route in router.routes]
    assert "/services" in routes or any("/services" in r for r in routes), \
        "status 라우터에 /services 엔드포인트가 없습니다"
