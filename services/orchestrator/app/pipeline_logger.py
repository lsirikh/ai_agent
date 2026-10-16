"""
Pipeline Logger Wrapper for Orchestrator Service

Phase 31.1.5: shared/pipeline_logger 모듈을 사용하는 wrapper
Phase 31.5: HEARTBEAT_INTERVAL 중앙 관리

Note: Orchestrator는 PipelineLogger 클래스도 직접 import하므로 re-export 필요
"""
import sys
import os

# shared 모듈 경로 추가
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

from shared.pipeline_logger import PipelineLogger, HEARTBEAT_INTERVAL, DEFAULT_LOG_CHANNEL

# PipelineLogger 클래스를 re-export (orchestrator에서 직접 import하는 코드 호환)
__all__ = ['PipelineLogger', 'get_logger', 'reset_loggers', 'HEARTBEAT_INTERVAL', 'DEFAULT_LOG_CHANNEL']

_loggers = {}


def get_logger(service_name: str, redis_client=None) -> PipelineLogger:
    """
    서비스용 PipelineLogger 인스턴스 반환

    Args:
        service_name: 서비스 이름 (예: "orchestrator")
        redis_client: Redis 클라이언트 (옵션)

    Returns:
        PipelineLogger 인스턴스
    """
    if service_name not in _loggers:
        _loggers[service_name] = PipelineLogger(
            service_name=service_name,
            redis_client=redis_client
        )
    elif redis_client is not None and _loggers[service_name].redis is None:
        # Redis 클라이언트가 나중에 제공된 경우 업데이트
        _loggers[service_name].redis = redis_client

    return _loggers[service_name]


def reset_loggers():
    """테스트용: 모든 로거 인스턴스 초기화"""
    global _loggers
    _loggers = {}