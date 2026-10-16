"""
Backend API - Status Routes

Phase 5.1: 시스템 상태 조회 API
Phase 18.2: SSE 기반 실시간 상태 스트리밍
"""
import asyncio
import json
import os
import time
from typing import Any, Dict, List, Optional

import psutil
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..models.orchestrator import OrchestratorState as OrchestratorStateEnum
from ..services.state_manager import StateManager, DASHBOARD_UPDATES_CHANNEL

router = APIRouter(prefix="/api/status", tags=["status"])


class GPUInfo(BaseModel):
    available: bool
    name: Optional[str] = None
    memory_total: Optional[int] = None
    memory_used: Optional[int] = None
    memory_free: Optional[int] = None
    utilization: Optional[float] = None


class ServiceHealth(BaseModel):
    status: str
    latency_ms: Optional[float] = None
    error: Optional[str] = None


class OrchestratorState(BaseModel):
    state: str
    session_id: Optional[str] = None
    is_speaking: bool = False


class DashboardStats(BaseModel):
    active_sessions: int = 0
    documents_count: int = 0


class SystemStatus(BaseModel):
    status: str
    timestamp: float
    gpu: GPUInfo
    services: Dict[str, ServiceHealth]
    orchestrator: OrchestratorState
    dashboard_stats: DashboardStats
    service_display_names: Optional[Dict[str, str]] = None


class SystemMetrics(BaseModel):
    cpu: Dict[str, Any]
    memory: Dict[str, Any]
    disk: Dict[str, Any]


# 서비스 URL 설정 (Docker 네트워크에서 서비스 이름으로 접근)
SERVICE_URLS = {
    "stt": os.getenv("STT_SERVICE_URL", "http://stt:11001"),
    "tts": os.getenv("TTS_SERVICE_URL", "http://tts:11002"),
    "llm": os.getenv("LLM_SERVICE_URL", "http://llm:11003"),
    "embedding": os.getenv("EMBEDDING_SERVICE_URL", "http://embedding:11004"),
    "wake_word": os.getenv("WAKE_WORD_SERVICE_URL", "http://wake-word:11005"),
    "rag": os.getenv("RAG_SERVICE_URL", "http://rag:11006"),
    "orchestrator": os.getenv("ORCHESTRATOR_URL", "http://orchestrator:11007"),
    "audio_gateway": os.getenv("AUDIO_GATEWAY_SERVICE_URL", "http://audio-gateway:11008"),
}


async def fetch_json(url: str, timeout: float = 3.0) -> Optional[dict]:
    """
    URL에서 JSON 데이터 가져오기

    Args:
        url: 요청할 URL
        timeout: 타임아웃 (초)

    Returns:
        JSON 데이터 또는 None
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "curl", "-s", "--max-time", str(int(timeout)), "--connect-timeout", "1", url,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout + 2)
        if stdout:
            return json.loads(stdout.decode().strip())
    except Exception:
        pass
    return None


async def get_gpu_info_async() -> GPUInfo:
    """
    GPU 정보 조회 (STT 서비스의 /gpu 엔드포인트에서 가져오기)

    Returns:
        GPU 정보
    """
    try:
        # STT 서비스에서 GPU 정보 가져오기 (GPU가 있는 컨테이너)
        data = await fetch_json(f"{SERVICE_URLS['stt']}/gpu")
        if data and data.get("available"):
            return GPUInfo(
                available=True,
                name=data.get("name"),
                memory_total=data.get("memory_total"),
                memory_used=data.get("memory_used"),
                memory_free=data.get("memory_free"),
                utilization=data.get("utilization")
            )
    except Exception:
        pass

    return GPUInfo(available=False)


async def get_orchestrator_state_async() -> OrchestratorState:
    """
    Orchestrator 상태 조회 (실제 서비스에서 가져오기)

    Returns:
        Orchestrator 상태
    """
    try:
        data = await fetch_json(f"{SERVICE_URLS['orchestrator']}/status")
        if data:
            return OrchestratorState(
                state=data.get("state", "UNKNOWN"),
                session_id=data.get("session_id"),
                is_speaking=data.get("is_speaking", False)
            )
    except Exception:
        pass

    return OrchestratorState(state="OFFLINE", is_speaking=False)


async def get_rag_documents_count() -> int:
    """
    RAG 서비스에서 문서 개수 조회

    Returns:
        문서 개수
    """
    try:
        # RAG /health 엔드포인트에서 document_count 가져오기
        data = await fetch_json(f"{SERVICE_URLS['rag']}/health")
        if data:
            return data.get("document_count", 0)
    except Exception:
        pass

    return 0


async def get_active_sessions_count() -> int:
    """
    활성 세션 수 조회 (Redis에서 가져오기)

    Returns:
        활성 세션 수
    """
    try:
        import redis.asyncio as aioredis
        redis_host = os.getenv("REDIS_HOST", "redis")
        redis_port = int(os.getenv("REDIS_PORT", "6379"))

        client = aioredis.Redis(host=redis_host, port=redis_port, decode_responses=True)

        # 활성 세션 키 패턴으로 조회
        keys = await client.keys("edgevoice:session:*")
        count = len(keys)

        await client.aclose()
        return count
    except Exception:
        pass

    return 0


async def check_service_health_async(service_name: str) -> ServiceHealth:
    """
    서비스 헬스 체크 (비동기)

    Args:
        service_name: 서비스 이름

    Returns:
        서비스 상태
    """
    if service_name not in SERVICE_URLS:
        return ServiceHealth(status="unknown", error=f"Unknown service: {service_name}")

    url = f"{SERVICE_URLS[service_name]}/health"
    start_time = time.time()

    try:
        # subprocess로 curl 호출 (더 안정적)
        proc = await asyncio.create_subprocess_exec(
            "curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
            "--max-time", "3", "--connect-timeout", "1", url,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5.0)
        latency_ms = (time.time() - start_time) * 1000
        status_code = int(stdout.decode().strip())

        if status_code == 200:
            return ServiceHealth(status="healthy", latency_ms=round(latency_ms, 2))
        elif status_code == 0:
            return ServiceHealth(status="offline", error="Connection refused")
        else:
            return ServiceHealth(
                status="unhealthy",
                latency_ms=round(latency_ms, 2),
                error=f"HTTP {status_code}"
            )
    except asyncio.TimeoutError:
        return ServiceHealth(status="offline", error="Service not responding")
    except Exception as e:
        return ServiceHealth(status="error", error=str(e))


@router.get("", response_model=SystemStatus)
async def get_system_status():
    """
    시스템 전체 상태 조회

    Returns:
        시스템 상태 정보
    """
    # 병렬로 데이터 수집
    gpu_task = get_gpu_info_async()
    orchestrator_task = get_orchestrator_state_async()
    documents_task = get_rag_documents_count()
    sessions_task = get_active_sessions_count()

    # 서비스 상태 체크 (순차적으로 - asyncio.gather 이슈 방지)
    service_names = ["stt", "rag", "wake_word", "tts", "llm", "embedding", "audio_gateway"]
    services = {}
    for name in service_names:
        services[name] = await check_service_health_async(name)

    # 병렬 태스크 결과 수집
    gpu_info = await gpu_task
    orchestrator = await orchestrator_task
    documents_count = await documents_task
    active_sessions = await sessions_task

    health_results = list(services.values())

    # 전체 상태 결정
    healthy_count = sum(1 for h in health_results if h.status == "healthy")
    offline_count = sum(1 for h in health_results if h.status == "offline")

    if healthy_count == len(service_names):
        overall_status = "healthy"
    elif offline_count == len(service_names):
        overall_status = "offline"
    elif healthy_count > 0:
        overall_status = "partial"
    else:
        overall_status = "unhealthy"

    # Dashboard 통계
    dashboard_stats = DashboardStats(
        active_sessions=active_sessions,
        documents_count=documents_count
    )

    # 동적 서비스 표시 이름 (환경 변수에서 가져오기)
    tts_engine = os.getenv("TTS_ENGINE", "melo").upper()
    stt_model = os.getenv("STT_MODEL_SIZE", "large-v3")
    llm_model = os.getenv("LLM_MODEL", "")

    # LLM 모델명에서 짧은 이름 추출
    llm_short = "LLM"
    if "qwen" in llm_model.lower():
        llm_short = "LLM (Qwen)"
    elif "deepseek" in llm_model.lower():
        llm_short = "LLM (DeepSeek)"
    elif "phi" in llm_model.lower():
        llm_short = "LLM (Phi)"
    elif "llama" in llm_model.lower():
        llm_short = "LLM (Llama)"

    service_display_names = {
        "stt": f"STT ({stt_model})",
        "tts": f"TTS ({tts_engine})",
        "llm": llm_short,
        "embedding": "Embedding (BGE)",
        "audio_gateway": "Audio Gateway",
        "wake_word": "Wake Word",
        "rag": "RAG"
    }

    return SystemStatus(
        status=overall_status,
        timestamp=time.time(),
        gpu=gpu_info,
        services=services,
        orchestrator=orchestrator,
        dashboard_stats=dashboard_stats,
        service_display_names=service_display_names
    )


@router.get("/services/{service_name}")
async def check_service_health(service_name: str):
    """
    특정 서비스 헬스 체크

    Args:
        service_name: 서비스 이름

    Returns:
        서비스 상태
    """
    valid_services = ["stt", "tts", "llm", "embedding", "audio_gateway", "wake_word", "rag", "orchestrator"]

    if service_name not in valid_services:
        raise HTTPException(status_code=404, detail=f"Unknown service: {service_name}")

    health = await check_service_health_async(service_name)

    if health.status == "unhealthy":
        raise HTTPException(status_code=503, detail=health.error)

    return health


@router.get("/gpu")
async def get_gpu_status():
    """
    GPU 상태 조회

    Returns:
        GPU 정보
    """
    return await get_gpu_info_async()


@router.get("/orchestrator")
async def get_orchestrator_status():
    """
    Orchestrator 상태 조회

    Returns:
        Orchestrator 상태
    """
    return await get_orchestrator_state_async()


@router.get("/dashboard-stats")
async def get_dashboard_stats():
    """
    Dashboard 통계 조회

    Returns:
        활성 세션 수, 문서 개수
    """
    documents_count = await get_rag_documents_count()
    active_sessions = await get_active_sessions_count()

    return DashboardStats(
        active_sessions=active_sessions,
        documents_count=documents_count
    )


@router.get("/metrics", response_model=SystemMetrics)
async def get_system_metrics():
    """
    시스템 메트릭 조회

    Returns:
        CPU, 메모리, 디스크 사용량
    """
    # CPU 정보
    cpu_info = {
        "percent": psutil.cpu_percent(interval=0.1),
        "count": psutil.cpu_count(),
        "count_logical": psutil.cpu_count(logical=True),
        "frequency": psutil.cpu_freq()._asdict() if psutil.cpu_freq() else None
    }

    # 메모리 정보
    mem = psutil.virtual_memory()
    memory_info = {
        "total": mem.total,
        "available": mem.available,
        "used": mem.used,
        "percent": mem.percent
    }

    # 디스크 정보
    disk = psutil.disk_usage('/')
    disk_info = {
        "total": disk.total,
        "used": disk.used,
        "free": disk.free,
        "percent": disk.percent
    }

    return SystemMetrics(
        cpu=cpu_info,
        memory=memory_info,
        disk=disk_info
    )


# =============================================================================
# Phase 18.2: SSE 기반 실시간 상태 스트리밍
# =============================================================================

# Redis client (lifespan에서 주입)
_redis_client = None
_state_manager: Optional[StateManager] = None


def set_status_redis_client(redis):
    """Redis 클라이언트 설정 (lifespan에서 호출)"""
    global _redis_client, _state_manager
    _redis_client = redis
    _state_manager = StateManager(redis=redis)


async def get_status_state_manager() -> StateManager:
    """StateManager 인스턴스 반환"""
    global _redis_client, _state_manager
    if _state_manager is None:
        if _redis_client is None:
            # lifespan 에서 주입되지 않았으면 직접 연결한다(없으면 상태가 항상 OFF 로 보인다)
            import redis.asyncio as aioredis

            _redis_client = aioredis.Redis(
                host=os.getenv("REDIS_HOST", "redis"),
                port=int(os.getenv("REDIS_PORT", "6379")),
                decode_responses=True,
            )
        _state_manager = StateManager(redis=_redis_client)
    return _state_manager


@router.get("/stream")
async def stream_status():
    """
    SSE 기반 실시간 대시보드 상태 스트림

    이벤트 타입:
    - init: 초기 상태 전송
    - orchestrator_state: Orchestrator 상태 변경
    - service_health: 서비스 헬스 업데이트
    - active_sessions: 활성 세션 수 변경

    Returns:
        StreamingResponse (text/event-stream)
    """

    async def event_generator():
        """SSE 이벤트 생성기"""
        try:
            # 1. 초기 상태 전송
            manager = await get_status_state_manager()
            current_state = await manager.get_current_state()

            init_data = {
                "orchestrator_state": current_state or {"state": OrchestratorStateEnum.OFF.value},
                "timestamp": time.time()
            }
            yield f"event: init\ndata: {json.dumps(init_data)}\n\n"

            # 2. 주기적으로 상태 업데이트 전송 (1초마다)
            update_count = 0
            while True:
                await asyncio.sleep(1)
                update_count += 1

                # Orchestrator 상태 조회
                current_state = await manager.get_current_state()

                state_data = {
                    "state": current_state.get("state", OrchestratorStateEnum.OFF.value) if current_state else OrchestratorStateEnum.OFF.value,
                    "session_id": current_state.get("session_id") if current_state else None,
                    "timestamp": time.time()
                }
                yield f"event: orchestrator_state\ndata: {json.dumps(state_data)}\n\n"

                # 30회(30초)마다 연결 유지를 위한 heartbeat
                if update_count % 30 == 0:
                    yield f"event: heartbeat\ndata: {json.dumps({'timestamp': time.time()})}\n\n"

        except asyncio.CancelledError:
            # 클라이언트 연결 종료
            pass
        except Exception as e:
            yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # nginx 버퍼링 비활성화
        }
    )
