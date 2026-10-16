"""
Health Models
Phase 18.5: Health 정보 확장

확장된 Health 응답 모델 정의
"""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class ServiceHealth(BaseModel):
    """개별 서비스 health 정보"""
    name: str
    status: str  # "healthy", "unhealthy", "unknown"
    url: Optional[str] = None
    response_time_ms: Optional[float] = None
    error: Optional[str] = None


class ModelInfo(BaseModel):
    """LLM 모델 정보"""
    name: Optional[str] = None
    provider: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None


class SettingsInfo(BaseModel):
    """현재 설정 요약"""
    wake_word: Optional[str] = None
    language: Optional[str] = None
    context_enabled: Optional[bool] = None
    rag_enabled: Optional[bool] = None


class ExtendedHealthResponse(BaseModel):
    """확장된 Health 응답

    Phase 18.5: 모델 정보와 설정을 포함한 상세 health 정보
    """
    status: str  # "healthy", "degraded", "unhealthy"
    service: str = "backend"
    database: str  # "connected", "disconnected"
    services: List[ServiceHealth] = []
    model_info: Optional[ModelInfo] = None
    settings: Optional[SettingsInfo] = None
    timestamp: Optional[float] = None


class SubsystemHealth(BaseModel):
    """서브시스템 Health 정보

    Phase 20.2: 서브시스템 Health 표준화
    각 서브시스템(STT, TTS, LLM 등)의 상세 health 정보
    """
    service: str  # 서비스 이름 (stt, tts, llm, wake-word 등)
    status: str  # "healthy", "unhealthy", "unknown"
    url: Optional[str] = None
    model_info: Optional[Dict[str, Any]] = None  # 모델 이름, 버전 등
    settings: Optional[Dict[str, Any]] = None  # 현재 설정값
    error: Optional[str] = None
    response_time_ms: Optional[float] = None
    timestamp: Optional[str] = None
