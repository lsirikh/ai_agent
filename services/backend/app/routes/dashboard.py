"""
Backend API - Dashboard Routes

Phase 28.2: Dashboard Initialize + SSE API
- /api/dashboard/init: 페이지 로드 시 모든 서비스 정보 일괄 조회
- /api/dashboard/stream: SSE로 실시간 상태 업데이트 스트리밍

Phase 33.3: LLM Loading Progress Support
- get_llm_loading_progress: Docker logs에서 vLLM 로딩 진행률 조회
- get_container_start_time: 컨테이너 시작 시간 조회
"""
import asyncio
import json
import os
import re
import time
from typing import Any, Dict, Optional

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from ..services.state_manager import StateManager

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

# 서비스 URL 설정
SERVICE_URLS = {
    "stt": os.getenv("STT_SERVICE_URL", "http://stt:11001"),
    "tts": os.getenv("TTS_SERVICE_URL", "http://tts:11002"),
    "llm": os.getenv("VLLM_BASE_URL", "http://llm:11003"),
    "embedding": os.getenv("EMBEDDING_SERVICE_URL", "http://embedding:11004"),
    "wake_word": os.getenv("WAKE_WORD_SERVICE_URL", "http://wake-word:11005"),
    "rag": os.getenv("RAG_SERVICE_URL", "http://rag:11006"),
    "orchestrator": os.getenv("ORCHESTRATOR_URL", "http://orchestrator:11007"),
    "audio_gateway": os.getenv("AUDIO_GATEWAY_URL", "http://audio-gateway:11008"),
}

# Redis client (lifespan에서 주입)
_redis_client = None
_state_manager: Optional[StateManager] = None


def set_dashboard_redis_client(redis):
    """Redis 클라이언트 설정 (lifespan에서 호출)"""
    global _redis_client, _state_manager
    _redis_client = redis
    _state_manager = StateManager.get_instance(redis=redis)


async def fetch_health_status(url: str, timeout: float = 3.0) -> bool:
    """
    Health check - HTTP status code 기반 판단 (Phase 29.1.1)

    vLLM처럼 body 없이 200 OK만 반환하는 케이스 지원.
    curl -w "%{http_code}" 로 HTTP status code만 확인합니다.

    Args:
        url: Health check URL
        timeout: 타임아웃 (초)

    Returns:
        True if HTTP 200, False otherwise
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
            "--max-time", str(int(timeout)), "--connect-timeout", "1", url,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout + 2)
        if stdout:
            status_code = int(stdout.decode().strip())
            return status_code == 200
    except Exception:
        pass
    return False


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


async def fetch_service_info(service_name: str) -> Dict[str, Any]:
    """
    개별 서비스의 /info 엔드포인트에서 정보 가져오기

    Args:
        service_name: 서비스 이름

    Returns:
        서비스 정보 dict
    """
    if service_name not in SERVICE_URLS:
        return {"service": service_name, "status": "unknown", "error": "Unknown service"}

    base_url = SERVICE_URLS[service_name]
    start_time = time.time()

    # LLM은 vLLM 공식 이미지로 /info 없음 - 설정값 기반 구성
    if service_name == "llm":
        return await construct_llm_info()

    # /info 엔드포인트 호출
    info_url = f"{base_url}/info"
    info_data = await fetch_json(info_url, timeout=3.0)
    latency_ms = (time.time() - start_time) * 1000

    if info_data:
        info_data["latency_ms"] = round(latency_ms, 2)
        info_data["status"] = "healthy"
        return info_data

    # /info 실패 시 /health로 fallback
    health_url = f"{base_url}/health"
    health_data = await fetch_json(health_url, timeout=2.0)
    latency_ms = (time.time() - start_time) * 1000

    if health_data:
        return {
            "service": service_name,
            "status": "healthy",
            "latency_ms": round(latency_ms, 2),
            "error": "/info endpoint not available"
        }

    return {
        "service": service_name,
        "status": "offline",
        "latency_ms": None,
        "error": "Service unreachable"
    }


async def get_container_health_status(container_name: str) -> str:
    """
    Docker container health status 조회 (Phase 29.4.1)

    Returns:
        "healthy", "unhealthy", "starting", "none", "unknown"
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "docker", "inspect", container_name,
            "--format", "{{.State.Health.Status}}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
        if stdout:
            status = stdout.decode().strip()
            # 빈 문자열이거나 <no value>인 경우 none 반환
            if status and status != "<no value>":
                return status
            return "none"
    except Exception:
        pass
    return "unknown"


async def get_llm_loading_progress(container_name: str = "ev-llm") -> Dict[str, Any]:
    """
    Phase 33.3.1: Docker logs에서 vLLM 로딩 진행률 조회

    Args:
        container_name: Docker 컨테이너 이름 (기본: ev-llm)

    Returns:
        진행률 정보 딕셔너리
        {
            "progress_percent": int (0-100),
            "stage": str ("unknown" | "initializing" | "loading_weights" | "complete"),
            "message": str
        }
    """
    default_result = {
        "progress_percent": 0,
        "stage": "unknown",
        "message": "Unable to determine loading progress"
    }

    try:
        # Docker logs 조회 (최근 100줄)
        proc = await asyncio.create_subprocess_exec(
            "docker", "logs", "--tail", "100", container_name,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=5)

        # stdout과 stderr 모두 확인 (vLLM은 stderr에 진행률 출력)
        logs = stdout.decode("utf-8", errors="ignore")
        if stderr:
            logs += stderr.decode("utf-8", errors="ignore")

        if not logs:
            return default_result

        # 로그를 줄 단위로 역순 파싱 (최근 로그 우선)
        lines = logs.strip().split("\n")
        for line in reversed(lines):
            result = _parse_vllm_progress(line)
            if result:
                return result

        return default_result

    except Exception:
        return default_result


def _parse_vllm_progress(log_text: str) -> Optional[Dict[str, Any]]:
    """
    vLLM Docker 로그에서 진행률 정보를 파싱합니다.

    Args:
        log_text: Docker 로그 텍스트

    Returns:
        진행률 정보 딕셔너리 또는 None
    """
    if not log_text:
        return None

    # 패턴 1: 모델 로딩 완료 - Application startup complete
    if "application startup complete" in log_text.lower():
        print(f"[LLM Progress] Pattern matched: startup complete")
        return {
            "progress_percent": 100,
            "stage": "complete",
            "message": "Model loaded successfully"
        }

    # 패턴 2: 모델 로딩 완료 (기존 패턴)
    if "loaded successfully" in log_text.lower() or "model loaded" in log_text.lower():
        print(f"[LLM Progress] Pattern matched: loaded successfully")
        return {
            "progress_percent": 100,
            "stage": "complete",
            "message": "Model loaded successfully"
        }

    # 패턴 3: safetensors checkpoint shards 로딩 (vLLM 0.12+)
    safetensors_pattern = r"Loading safetensors checkpoint shards:\s*(\d+)%"
    match = re.search(safetensors_pattern, log_text)
    if match:
        percent = int(match.group(1))
        print(f"[LLM Progress] Pattern matched: safetensors {percent}%")
        return {
            "progress_percent": percent,
            "stage": "loading_weights",
            "message": f"Loading: {percent}%"
        }

    # 패턴 4: 모델 가중치 로딩 진행률 (기존 패턴)
    weight_pattern = r"Loading model weights:\s*(\d+)%"
    match = re.search(weight_pattern, log_text)
    if match:
        percent = int(match.group(1))
        print(f"[LLM Progress] Pattern matched: weights {percent}%")
        return {
            "progress_percent": percent,
            "stage": "loading_weights",
            "message": f"Loading: {percent}%"
        }

    # 패턴 5: CUDA graphs 캡처 단계
    cuda_pattern = r"Capturing CUDA graphs.*?:\s*(\d+)%"
    match = re.search(cuda_pattern, log_text)
    if match:
        percent = int(match.group(1))
        # CUDA graph는 전체의 마지막 10% 정도로 취급
        adjusted_percent = 90 + int(percent * 0.1)
        print(f"[LLM Progress] Pattern matched: CUDA graphs {percent}% -> {adjusted_percent}%")
        return {
            "progress_percent": adjusted_percent,
            "stage": "cuda_graphs",
            "message": f"Optimizing: {adjusted_percent}%"
        }

    # 패턴 6: 모델 로딩 시작
    if "starting to load model" in log_text.lower():
        print(f"[LLM Progress] Pattern matched: starting to load")
        return {
            "progress_percent": 5,
            "stage": "starting",
            "message": "Starting..."
        }

    # 패턴 7: 초기화 단계
    if "initializing" in log_text.lower() or "init engine" in log_text.lower():
        print(f"[LLM Progress] Pattern matched: initializing")
        return {
            "progress_percent": 0,
            "stage": "initializing",
            "message": "Starting..."
        }

    return None


async def get_container_start_time(container_name: str = "ev-llm") -> Optional[float]:
    """
    Phase 33.3.1: 컨테이너 시작 후 경과 시간 조회

    Args:
        container_name: Docker 컨테이너 이름 (기본: ev-llm)

    Returns:
        시작 후 경과 시간 (초), 실패 시 None
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "docker", "inspect", container_name,
            "--format", "{{.State.StartedAt}}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)

        if stdout:
            started_at = stdout.decode().strip()
            if started_at and started_at != "<no value>":
                # ISO 8601 형식 파싱: 2025-01-15T10:30:00.123456789Z
                from datetime import datetime
                # 나노초 제거 (.123456789Z → .123456Z)
                if "." in started_at:
                    base, frac = started_at.rsplit(".", 1)
                    # Z 제거 후 마이크로초로 자름
                    frac = frac.rstrip("Z")[:6]
                    started_at = f"{base}.{frac}Z"

                start_time = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
                now = datetime.now(start_time.tzinfo)
                elapsed = (now - start_time).total_seconds()
                return elapsed

    except Exception:
        pass

    return None


def estimate_progress_from_elapsed_time(elapsed_seconds: float, base_seconds: float = 120.0) -> int:
    """
    Phase 33.4.2: 경과 시간에서 진행률을 추정합니다.

    Docker logs 파싱 실패 시 시간 기반 fallback으로 사용.

    Args:
        elapsed_seconds: 컨테이너 시작 후 경과 시간 (초)
        base_seconds: 예상 완료 시간 (기본: 120초)

    Returns:
        추정 진행률 (0-99, 최대 99%)
    """
    if elapsed_seconds <= 0:
        return 0

    # 진행률 계산: (경과 시간 / 기본 시간) * 100
    progress = int((elapsed_seconds / base_seconds) * 100)

    # 최대 99%로 제한 (100%는 실제 완료 시에만)
    return min(progress, 99)


async def fetch_vllm_model_info(base_url: str) -> Dict[str, Any]:
    """
    vLLM /v1/models API로 실제 로딩된 모델 정보 조회 (Phase 29.2.1)

    Args:
        base_url: vLLM 서비스 URL

    Returns:
        모델 정보 dict {"name": "...", "owned_by": "..."}
    """
    models_url = f"{base_url}/v1/models"
    models_data = await fetch_json(models_url, timeout=3.0)

    if models_data and "data" in models_data and models_data["data"]:
        # vLLM은 한 개 모델만 로딩
        model = models_data["data"][0]
        return {
            "name": model.get("id", "unknown"),
            "owned_by": model.get("owned_by", "vllm"),
            "created": model.get("created")
        }

    # Fallback to env var
    return {
        "name": os.getenv("LLM_MODEL", "unknown")
    }


async def construct_llm_info() -> Dict[str, Any]:
    """
    LLM 서비스 정보 구성 (Phase 29.1.2 수정, Phase 33.3.1 확장)

    vLLM /health는 빈 body 반환 → fetch_health_status 사용
    Docker health status로 loading 상태 감지
    /v1/models API로 실제 로딩된 모델 정보 조회
    Phase 33.3.1: Docker logs에서 진행률 조회
    """
    base_url = SERVICE_URLS["llm"]
    start_time = time.time()

    # 1. Docker health check 상태 확인
    docker_health = await get_container_health_status("ev-llm")

    # 2. vLLM /health - HTTP status code 기반 판단 (빈 body 지원)
    health_url = f"{base_url}/health"
    is_healthy = await fetch_health_status(health_url, timeout=3.0)
    latency_ms = (time.time() - start_time) * 1000

    # 3. 실제 로딩된 모델 정보 (vLLM /v1/models API)
    model_info = await fetch_vllm_model_info(base_url)

    # 상태 결정 로직:
    # - is_healthy=True → healthy
    # - is_healthy=False && docker_health=starting → loading
    # - otherwise → offline
    if is_healthy:
        status = "healthy"
    elif docker_health == "starting":
        status = "loading"
    else:
        status = "offline"

    result = {
        "service": "llm",
        "model": model_info,
        "settings": {
            "temperature": 0.7,
            "max_tokens": 2048,
            "top_p": 0.95
        },
        "status": status,
        "docker_health": docker_health
    }

    if is_healthy:
        result["latency_ms"] = round(latency_ms, 2)
    else:
        result["latency_ms"] = None
        if status == "offline":
            result["error"] = "Service unreachable"

    # Phase 33.3.1: 로딩 중일 때 진행률 정보 추가
    if status == "loading":
        # Docker logs에서 진행률 조회
        progress_info = await get_llm_loading_progress("ev-llm")
        loading_stage = progress_info.get("stage", "unknown")

        # 컨테이너 시작 후 경과 시간 조회
        elapsed = await get_container_start_time("ev-llm")
        if elapsed is not None:
            result["elapsed_seconds"] = round(elapsed, 1)

        # Phase 33.4.2: Docker logs 파싱 실패 시 시간 기반 fallback
        if loading_stage == "unknown" and elapsed is not None:
            # 시간 기반 추정
            estimated_progress = estimate_progress_from_elapsed_time(elapsed)
            result["progress_percent"] = estimated_progress
            result["loading_stage"] = "estimated"
            result["loading_message"] = f"Loading... (estimated {estimated_progress}%)"
        else:
            result["progress_percent"] = progress_info.get("progress_percent", 0)
            result["loading_stage"] = loading_stage
            result["loading_message"] = progress_info.get("message", "")

    return result


async def get_gpu_info() -> Dict[str, Any]:
    """GPU 정보 조회 (STT 서비스에서)"""
    gpu_url = f"{SERVICE_URLS['stt']}/gpu"
    data = await fetch_json(gpu_url)

    if data and data.get("available"):
        memory_total = data.get("memory_total", 0)
        memory_used = data.get("memory_used", 0)

        return {
            "available": True,
            "name": data.get("name"),
            "used_gb": round(memory_used / (1024 ** 3), 1) if memory_used else 0,
            "total_gb": round(memory_total / (1024 ** 3), 1) if memory_total else 0,
            "utilization_percent": data.get("utilization", 0)
        }

    return {"available": False}


async def get_active_sessions() -> Dict[str, Any]:
    """활성 세션 수 조회"""
    try:
        import redis.asyncio as aioredis
        redis_host = os.getenv("REDIS_HOST", "redis")
        redis_port = int(os.getenv("REDIS_PORT", "6379"))

        client = aioredis.Redis(host=redis_host, port=redis_port, decode_responses=True)
        keys = await client.keys("edgevoice:session:*")
        count = len(keys)
        await client.aclose()

        return {"active": count, "total": count}
    except Exception:
        return {"active": 0, "total": 0}


async def get_document_count() -> Dict[str, Any]:
    """RAG 문서 수 조회"""
    info_url = f"{SERVICE_URLS['rag']}/info"
    data = await fetch_json(info_url)

    if data and "stats" in data:
        return {"count": data["stats"].get("document_count", 0)}

    # Fallback to /health (기존 방식)
    health_url = f"{SERVICE_URLS['rag']}/health"
    data = await fetch_json(health_url)

    if data:
        return {"count": data.get("document_count", 0)}

    return {"count": 0}


@router.get("/init")
async def dashboard_init():
    """
    Dashboard 초기화 - 모든 서비스 정보 일괄 수집

    페이지 로드 시 한 번 호출하여 모든 서비스 정보를 가져옵니다.

    Returns:
        services: 각 서비스별 상세 정보
        system: GPU, 세션, 문서 수 등 시스템 정보
    """
    # 병렬로 모든 서비스 info 호출
    service_names = ["stt", "tts", "llm", "embedding", "wake_word", "rag", "audio_gateway", "orchestrator"]

    service_tasks = [fetch_service_info(name) for name in service_names]
    gpu_task = get_gpu_info()
    sessions_task = get_active_sessions()
    documents_task = get_document_count()

    # 모든 태스크 병렬 실행
    results = await asyncio.gather(
        *service_tasks,
        gpu_task,
        sessions_task,
        documents_task,
        return_exceptions=True
    )

    # 결과 파싱
    services = {}
    for i, name in enumerate(service_names):
        result = results[i]
        if isinstance(result, Exception):
            services[name] = {
                "service": name,
                "status": "error",
                "error": str(result)
            }
        else:
            services[name] = result

    gpu_info = results[len(service_names)] if not isinstance(results[len(service_names)], Exception) else {"available": False}
    sessions_info = results[len(service_names) + 1] if not isinstance(results[len(service_names) + 1], Exception) else {"active": 0, "total": 0}
    documents_info = results[len(service_names) + 2] if not isinstance(results[len(service_names) + 2], Exception) else {"count": 0}

    return {
        "services": services,
        "system": {
            "gpu": gpu_info,
            "sessions": sessions_info,
            "documents": documents_info
        },
        "timestamp": time.time()
    }


@router.get("/stream")
async def dashboard_stream():
    """
    Dashboard 실시간 업데이트 SSE 스트림

    이벤트 타입:
    - orchestrator_state: Orchestrator 상태 변경
    - service_status: 서비스 상태 변경
    - gpu_update: GPU 메모리 변경
    - session_update: 세션 수 변경
    - heartbeat: 연결 유지용 (30초마다)

    Returns:
        StreamingResponse (text/event-stream)
    """

    async def event_generator():
        """SSE 이벤트 생성기"""
        try:
            update_count = 0
            # 이전 서비스 상태 추적 (상태 변경 시에만 전송)
            prev_service_status: Dict[str, str] = {}

            while True:
                await asyncio.sleep(1)
                update_count += 1

                # 5초마다 Orchestrator 상태 업데이트
                if update_count % 5 == 0:
                    try:
                        orch_info = await fetch_service_info("orchestrator")
                        if orch_info and "state" in orch_info:
                            state_data = {
                                "state": orch_info.get("state", "UNKNOWN"),
                                "timestamp": time.time()
                            }
                            yield f"event: orchestrator_state\ndata: {json.dumps(state_data)}\n\n"
                    except Exception:
                        pass

                # 5초마다 LLM 상태 체크 (Phase 29.3: 빠르게 변하는 서비스)
                if update_count % 5 == 0:
                    try:
                        llm_info = await construct_llm_info()
                        llm_status = llm_info.get("status", "unknown")
                        llm_progress = llm_info.get("progress_percent")
                        llm_stage = llm_info.get("loading_stage")

                        # 상태 변경 또는 로딩 중일 때 service_status 이벤트 전송
                        status_changed = prev_service_status.get("llm") != llm_status
                        is_loading = llm_status == "loading" or (llm_stage and llm_stage not in ["complete", "unknown"])

                        if status_changed or is_loading:
                            prev_service_status["llm"] = llm_status
                            service_data = {
                                "service": "llm",
                                "status": llm_status,
                                "docker_health": llm_info.get("docker_health"),
                                "model": llm_info.get("model"),
                                # Phase 35: progress 필드 추가
                                "progress_percent": llm_progress,
                                "loading_stage": llm_stage,
                                "loading_message": llm_info.get("loading_message"),
                                "elapsed_seconds": llm_info.get("elapsed_seconds"),
                                "latency_ms": llm_info.get("latency_ms"),
                                "timestamp": time.time()
                            }
                            print(f"[Dashboard SSE] LLM status update: status={llm_status}, progress={llm_progress}%, stage={llm_stage}")
                            yield f"event: service_status\ndata: {json.dumps(service_data)}\n\n"
                    except Exception as e:
                        print(f"[Dashboard SSE] LLM status check failed: {e}")

                # 10초마다 GPU 정보 업데이트
                if update_count % 10 == 0:
                    try:
                        gpu_info = await get_gpu_info()
                        if gpu_info.get("available"):
                            yield f"event: gpu_update\ndata: {json.dumps(gpu_info)}\n\n"
                    except Exception:
                        pass

                # 30초마다 안정 서비스 상태 체크 (STT, TTS, Embedding 등)
                if update_count % 30 == 0:
                    stable_services = ["stt", "tts", "embedding", "wake_word", "rag"]
                    for svc_name in stable_services:
                        try:
                            svc_info = await fetch_service_info(svc_name)
                            svc_status = svc_info.get("status", "unknown")

                            # 상태가 변경되었을 때만 전송
                            if prev_service_status.get(svc_name) != svc_status:
                                prev_service_status[svc_name] = svc_status
                                service_data = {
                                    "service": svc_name,
                                    "status": svc_status,
                                    "timestamp": time.time()
                                }
                                yield f"event: service_status\ndata: {json.dumps(service_data)}\n\n"
                        except Exception:
                            pass

                # 30초마다 heartbeat
                if update_count % 30 == 0:
                    yield f"event: heartbeat\ndata: {json.dumps({'timestamp': time.time()})}\n\n"

        except asyncio.CancelledError:
            pass
        except Exception as e:
            yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )