"""
Session Models
Phase 18.3.1: 세션 타입 정의

타입:
- web: 웹 채팅 세션
- voice: 음성 파이프라인 세션
- unified: 통합 세션 (웹 + 음성)
"""
from enum import Enum


class SessionType(str, Enum):
    """세션 타입"""

    WEB = "web"
    VOICE = "voice"
    UNIFIED = "unified"


class SessionSource(str, Enum):
    """세션 생성 소스"""

    WEB = "web"
    ORCHESTRATOR = "orchestrator"
    API = "api"
