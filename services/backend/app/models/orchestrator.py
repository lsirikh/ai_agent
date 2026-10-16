"""
Orchestrator Models
Phase 18.1.1: Orchestrator 상태 정의

7개 상태:
- OFF: 서비스 미실행
- READY: 대기 상태 (초기화 완료)
- LISTENING: Wake Word 감지 후 음성 수신 중
- STT_PROCESSING: 음성->텍스트 변환 중
- LLM_PROCESSING: LLM 응답 생성 중
- TTS_PROCESSING: 텍스트->음성 변환 중
- ERROR: 에러 상태
"""
from enum import Enum


class OrchestratorState(str, Enum):
    """Orchestrator 파이프라인 상태"""

    OFF = "OFF"
    READY = "READY"
    LISTENING = "LISTENING"
    STT_PROCESSING = "STT_PROCESSING"
    LLM_PROCESSING = "LLM_PROCESSING"
    TTS_PROCESSING = "TTS_PROCESSING"
    ERROR = "ERROR"
