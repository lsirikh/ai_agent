"""
Backend API Debug Router

Phase 5.5: Debug/Testing API
"""
import asyncio
import base64
import time
from collections import deque
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/debug", tags=["debug"])


# ===== Pydantic Models =====

class STTTestRequest(BaseModel):
    """STT 테스트 요청"""
    audio_base64: str
    language: str = Field(default="ko")


class STTTestResponse(BaseModel):
    """STT 테스트 응답"""
    success: bool
    text: Optional[str] = None
    confidence: Optional[float] = None
    duration_ms: Optional[int] = None
    error: Optional[str] = None


class TTSTestRequest(BaseModel):
    """TTS 테스트 요청"""
    text: str
    voice: str = Field(default="af_heart")
    speed: float = Field(default=1.0)


class TTSTestResponse(BaseModel):
    """TTS 테스트 응답"""
    success: bool
    audio_base64: Optional[str] = None
    duration_ms: Optional[int] = None
    error: Optional[str] = None


class LLMTestRequest(BaseModel):
    """LLM 테스트 요청"""
    prompt: str
    max_tokens: int = Field(default=100)
    temperature: float = Field(default=0.7)


class LLMTestResponse(BaseModel):
    """LLM 테스트 응답"""
    success: bool
    response: Optional[str] = None
    tokens_used: Optional[int] = None
    duration_ms: Optional[int] = None
    error: Optional[str] = None


class ServiceHealthResponse(BaseModel):
    """서비스 헬스체크 응답"""
    service: str
    healthy: bool
    latency_ms: Optional[int] = None
    version: Optional[str] = None
    model: Optional[str] = None
    error: Optional[str] = None


# ===== Log Queue =====

_log_queue: deque = deque(maxlen=1000)


def get_log_queue() -> List[str]:
    """로그 큐 반환"""
    return list(_log_queue)


def add_log(message: str):
    """로그 추가"""
    _log_queue.append(message)


# ===== Service Test Functions =====

def test_stt_service(audio_base64: str, language: str = "ko") -> Dict[str, Any]:
    """STT 서비스 테스트"""
    try:
        start_time = time.time()

        # TODO: 실제 STT 서비스 호출
        # audio_bytes = base64.b64decode(audio_base64)
        # result = stt_client.transcribe(audio_bytes, language=language)

        # 모의 응답
        duration_ms = int((time.time() - start_time) * 1000)

        return {
            "success": True,
            "text": "테스트 음성입니다",
            "confidence": 0.95,
            "duration_ms": duration_ms
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


def test_tts_service(text: str, voice: str = "af_heart", speed: float = 1.0) -> Dict[str, Any]:
    """TTS 서비스 테스트"""
    try:
        start_time = time.time()

        # TODO: 실제 TTS 서비스 호출
        # audio_bytes = tts_client.synthesize(text, voice=voice, speed=speed)
        # audio_base64 = base64.b64encode(audio_bytes).decode("utf-8")

        # 모의 응답
        duration_ms = int((time.time() - start_time) * 1000)
        audio_base64 = base64.b64encode(b"mock audio data").decode("utf-8")

        return {
            "success": True,
            "audio_base64": audio_base64,
            "duration_ms": duration_ms
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


def test_llm_service(prompt: str, max_tokens: int = 100, temperature: float = 0.7) -> Dict[str, Any]:
    """LLM 서비스 테스트"""
    try:
        start_time = time.time()

        # TODO: 실제 LLM 서비스 호출
        # response = llm_client.generate(prompt, max_tokens=max_tokens, temperature=temperature)

        # 모의 응답
        duration_ms = int((time.time() - start_time) * 1000)

        return {
            "success": True,
            "response": "안녕하세요! 무엇을 도와드릴까요?",
            "tokens_used": 25,
            "duration_ms": duration_ms
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


def check_service_health(service_name: str) -> Dict[str, Any]:
    """서비스 헬스체크"""
    try:
        start_time = time.time()

        # TODO: 실제 서비스 헬스체크 호출
        # health = service_client.health_check()

        latency_ms = int((time.time() - start_time) * 1000)

        return {
            "service": service_name,
            "healthy": True,
            "latency_ms": latency_ms,
            "version": "1.0.0"
        }
    except Exception as e:
        return {
            "service": service_name,
            "healthy": False,
            "error": str(e)
        }


# ===== API Endpoints =====

@router.post("/stt/test", response_model=STTTestResponse)
async def test_stt(request: STTTestRequest):
    """
    STT 서비스 테스트

    Args:
        request: STT 테스트 요청

    Returns:
        STT 테스트 결과
    """
    result = test_stt_service(request.audio_base64, request.language)
    return STTTestResponse(**result)


@router.post("/tts/test", response_model=TTSTestResponse)
async def test_tts(request: TTSTestRequest):
    """
    TTS 서비스 테스트

    Args:
        request: TTS 테스트 요청

    Returns:
        TTS 테스트 결과
    """
    if not request.text or not request.text.strip():
        raise HTTPException(status_code=400, detail="텍스트를 입력해주세요")

    result = test_tts_service(request.text, request.voice, request.speed)
    return TTSTestResponse(**result)


@router.post("/llm/test", response_model=LLMTestResponse)
async def test_llm(request: LLMTestRequest):
    """
    LLM 서비스 테스트

    Args:
        request: LLM 테스트 요청

    Returns:
        LLM 테스트 결과
    """
    result = test_llm_service(request.prompt, request.max_tokens, request.temperature)
    return LLMTestResponse(**result)


@router.get("/health/{service_name}", response_model=ServiceHealthResponse)
async def check_health(service_name: str):
    """
    개별 서비스 헬스체크

    Args:
        service_name: 서비스 이름 (stt, tts, llm, embedding)

    Returns:
        서비스 헬스체크 결과
    """
    valid_services = ["stt", "tts", "llm", "embedding", "orchestrator"]

    if service_name not in valid_services:
        raise HTTPException(
            status_code=400,
            detail=f"알 수 없는 서비스입니다: {service_name}. 가능한 서비스: {', '.join(valid_services)}"
        )

    result = check_service_health(service_name)
    return ServiceHealthResponse(**result)


@router.websocket("/logs")
async def logs_websocket(websocket: WebSocket):
    """
    실시간 로그 WebSocket

    로그 메시지를 실시간으로 스트리밍합니다.
    """
    await websocket.accept()

    # 연결 확인 메시지 전송
    await websocket.send_json({
        "type": "connected",
        "message": "로그 스트리밍이 시작되었습니다"
    })

    try:
        last_index = 0
        while True:
            # 새 로그 메시지 전송
            logs = get_log_queue()
            if len(logs) > last_index:
                for log in logs[last_index:]:
                    await websocket.send_json({
                        "type": "log",
                        "message": log
                    })
                last_index = len(logs)

            # 잠시 대기
            await asyncio.sleep(0.1)

    except WebSocketDisconnect:
        pass
    except Exception:
        pass
