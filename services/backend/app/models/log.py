"""
Log Models
Phase 21.1: 파이프라인 로그 모델

파이프라인 서비스들의 로그를 저장하기 위한 모델 정의
"""
from typing import Any, Dict, Optional

from pydantic import BaseModel


class PipelineLog(BaseModel):
    """파이프라인 로그 모델

    각 서브시스템(STT, TTS, LLM 등)에서 발생하는 로그 정보
    """
    service: str  # 서비스 이름 (stt, tts, llm, orchestrator 등)
    level: str  # 로그 레벨 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    message: str  # 로그 메시지
    timestamp: str  # ISO 형식 타임스탬프

    # 선택적 필드
    session_id: Optional[str] = None  # 관련 세션 ID
    metadata: Optional[Dict[str, Any]] = None  # 추가 메타데이터
    log_id: Optional[str] = None  # 고유 로그 ID


class LogCreateRequest(BaseModel):
    """로그 생성 요청 모델"""
    service: str
    level: str
    message: str
    session_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class LogResponse(BaseModel):
    """로그 생성 응답 모델"""
    log_id: str
    status: str = "created"
