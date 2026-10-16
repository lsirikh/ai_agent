"""
Test: Pipeline Log Model
Phase 21.1: 파이프라인 로그 모델

TDD Red Phase: 이 테스트는 처음에 실패해야 합니다.
"""
import pytest
from datetime import datetime


def test_pipeline_log_model_exists():
    """PipelineLog 모델이 존재하는지 확인"""
    from app.models.log import PipelineLog
    assert PipelineLog is not None


def test_pipeline_log_has_required_fields():
    """PipelineLog가 필수 필드를 가지는지 확인"""
    from app.models.log import PipelineLog

    # 필수 필드로 인스턴스 생성
    log = PipelineLog(
        service="stt",
        level="INFO",
        message="Audio received",
        timestamp=datetime.utcnow().isoformat()
    )

    assert log.service == "stt"
    assert log.level == "INFO"
    assert log.message == "Audio received"
    assert log.timestamp is not None
