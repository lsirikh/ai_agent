"""
Orchestrator Main Entry Point

Phase 2.3: 오케스트레이터 서비스 진입점
HTTP health endpoint + Redis Event Processor
Phase 17.2: Service Heartbeat Logging (10초 간격)
Phase 27.8: LLM Proxy Heartbeat Logging (vLLM 상태 모니터링)
"""
import asyncio
import os
import signal
import time
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional

import httpx
import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel, Field

from shared.mcp_client import start_mcp_from_env

from .orchestrator import Orchestrator
from .pipeline_logger import get_logger, PipelineLogger, HEARTBEAT_INTERVAL


# Phase 50: Settings models
class OrchestratorSettingsRequest(BaseModel):
    """Orchestrator 설정 요청 (Phase 50)"""
    end_pause_seconds: Optional[float] = Field(
        default=None, ge=1.0, le=10.0,
        description="음성 입력 완료 판단을 위한 무음 시간 (초)"
    )
    listening_timeout_seconds: Optional[float] = Field(
        default=None, ge=5.0, le=30.0,
        description="Listening 모드 타임아웃 (초)"
    )


class OrchestratorSettingsResponse(BaseModel):
    """Orchestrator 설정 응답 (Phase 50)"""
    end_pause_seconds: float
    listening_timeout_seconds: float
    status: str = "applied"

# Global orchestrator instance
orchestrator: Optional[Orchestrator] = None

# Pipeline logger and heartbeat state
_logger = get_logger("orchestrator")
_llm_logger: Optional[PipelineLogger] = None
_service_start_time: float = 0.0
_heartbeat_running: bool = False


async def heartbeat_task() -> None:
    """
    하트비트 로그 태스크 (10초 간격)

    서비스 생존 확인을 위해 주기적으로 로그를 전송합니다.
    """
    global _heartbeat_running, orchestrator
    _heartbeat_running = True

    while _heartbeat_running:
        uptime_seconds = int(time.time() - _service_start_time)
        current_state = "UNKNOWN"
        if orchestrator and hasattr(orchestrator, 'state_machine'):
            current_state = orchestrator.state_machine.current_state.name

        await _logger.info(
            "heartbeat",
            f"Orchestrator Service alive (uptime: {uptime_seconds}s, state: {current_state})",
            metadata={
                "service": "orchestrator",
                "uptime_seconds": uptime_seconds,
                "current_state": current_state,
                "is_running": orchestrator._is_running if orchestrator else False
            }
        )
        await asyncio.sleep(HEARTBEAT_INTERVAL)


async def llm_heartbeat_task() -> None:
    """
    Phase 27.8: LLM 프록시 하트비트 태스크 (10초 간격)

    vLLM 서비스는 공식 Docker 이미지를 사용하므로 코드 수정이 불가능합니다.
    따라서 Orchestrator에서 vLLM health check를 수행하고 로그를 전송합니다.
    """
    global _heartbeat_running, _llm_logger

    _llm_logger = PipelineLogger("llm")
    vllm_url = os.getenv("LLM_SERVICE_URL", "http://llm:11003")

    while _heartbeat_running:
        try:
            # vLLM health check
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{vllm_url}/health")
                is_healthy = response.status_code == 200

            uptime_seconds = int(time.time() - _service_start_time)
            status = "healthy" if is_healthy else "unhealthy"

            await _llm_logger.info(
                "heartbeat",
                f"LLM Service (vLLM) {status} (proxy uptime: {uptime_seconds}s)",
                metadata={
                    "service": "llm",
                    "proxy_uptime_seconds": uptime_seconds,
                    "vllm_healthy": is_healthy,
                    "vllm_url": vllm_url
                }
            )
        except Exception as e:
            uptime_seconds = int(time.time() - _service_start_time)
            await _llm_logger.warning(
                "heartbeat",
                f"LLM Service (vLLM) unreachable (proxy uptime: {uptime_seconds}s)",
                metadata={
                    "service": "llm",
                    "proxy_uptime_seconds": uptime_seconds,
                    "vllm_healthy": False,
                    "error": str(e)
                }
            )

        await asyncio.sleep(HEARTBEAT_INTERVAL)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan handler"""
    global orchestrator, _service_start_time, _heartbeat_running

    _service_start_time = time.time()
    environment = os.getenv("ORCHESTRATOR_ENVIRONMENT", "development")
    print(f"Starting Orchestrator in {environment} mode...")

    orchestrator = Orchestrator(environment=environment)
    # 설정 화면에서 저장한(없으면 MCP_CONFIG_PATH) MCP 서버의 도구를 음성 대화에 붙인다
    try:
        orchestrator.mcp = await start_mcp_from_env(orchestrator.redis)
    except Exception as e:
        print(f"MCP unavailable: {e}")

    # Log service start
    await _logger.info(
        "orchestrator_service_started",
        "Orchestrator Service started",
        metadata={"environment": environment}
    )

    # Start Redis event processing in background
    asyncio.create_task(run_orchestrator())

    # Start heartbeat task (Phase 17.2)
    asyncio.create_task(heartbeat_task())

    # Start LLM proxy heartbeat task (Phase 27.8)
    asyncio.create_task(llm_heartbeat_task())

    print("Orchestrator service is ready")

    yield

    # Shutdown
    _heartbeat_running = False

    await _logger.info(
        "orchestrator_service_stopped",
        "Orchestrator Service stopped"
    )

    if orchestrator:
        if orchestrator.mcp:
            await orchestrator.mcp.close()
        await orchestrator.stop()
    print("Orchestrator stopped.")


async def run_orchestrator():
    """Run orchestrator Redis event loop"""
    global orchestrator
    if orchestrator:
        try:
            await orchestrator.run()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"Orchestrator error: {e}")


# Create FastAPI app
app = FastAPI(
    title="Orchestrator Service",
    description="EdgeVoice 음성 대화 오케스트레이터",
    version="1.0.0",
    lifespan=lifespan
)


@app.get("/health")
async def health_check():
    """Health check endpoint - 단순 생존 확인만"""
    return {
        "status": "healthy",
        "service": "orchestrator"
    }


@app.get("/info")
async def get_service_info():
    """
    서비스 상세 정보 조회 (Phase 28.1)

    Dashboard에서 사용할 서비스 정보를 반환합니다.
    /health와 분리하여 상세 정보만 제공합니다.
    """
    global orchestrator
    uptime_seconds = int(time.time() - _service_start_time) if _service_start_time > 0 else 0
    current_state = "UNKNOWN"
    if orchestrator and hasattr(orchestrator, 'state_machine'):
        current_state = orchestrator.state_machine.current_state.name

    return {
        "service": "orchestrator",
        "state": current_state,
        "settings": {
            "environment": os.getenv("ORCHESTRATOR_ENVIRONMENT", "development")
        },
        "stats": {
            "uptime_seconds": uptime_seconds,
            "is_running": orchestrator._is_running if orchestrator else False
        },
        "status": "ready" if orchestrator and orchestrator._is_running else "initializing"
    }


@app.get("/status")
async def get_status():
    """Get orchestrator status"""
    global orchestrator
    if orchestrator:
        return orchestrator.get_status()
    return {
        "state": "UNKNOWN",
        "state_info": {},
        "environment": os.getenv("ORCHESTRATOR_ENVIRONMENT", "development"),
        "is_running": False
    }


# Phase 50: Settings endpoints
@app.put("/settings", response_model=OrchestratorSettingsResponse)
async def update_settings(request: OrchestratorSettingsRequest):
    """
    Orchestrator 설정 업데이트 (Phase 50)

    Backend에서 end_pause_seconds, listening_timeout_seconds 설정 전파 시 호출됩니다.
    설정 변경 후 Redis로 상태와 함께 브로드캐스트합니다.
    """
    global orchestrator

    if not orchestrator:
        return OrchestratorSettingsResponse(
            end_pause_seconds=2.0,
            listening_timeout_seconds=10.0,
            status="orchestrator_not_ready"
        )

    # 설정 업데이트
    if request.end_pause_seconds is not None:
        orchestrator.end_pause_seconds = request.end_pause_seconds
    if request.listening_timeout_seconds is not None:
        orchestrator.listening_timeout = request.listening_timeout_seconds

    # 설정 변경 로그
    await _logger.info(
        "settings_updated",
        f"Settings updated: end_pause={orchestrator.end_pause_seconds}s, listening_timeout={orchestrator.listening_timeout}s",
        metadata={
            "end_pause_seconds": orchestrator.end_pause_seconds,
            "listening_timeout_seconds": orchestrator.listening_timeout
        }
    )

    # Redis로 설정 브로드캐스트 (Phase 50.2)
    await orchestrator.broadcast_settings()

    return OrchestratorSettingsResponse(
        end_pause_seconds=orchestrator.end_pause_seconds,
        listening_timeout_seconds=orchestrator.listening_timeout,
        status="applied"
    )


@app.get("/settings", response_model=OrchestratorSettingsResponse)
async def get_settings():
    """
    현재 Orchestrator 설정 조회 (Phase 50)
    """
    global orchestrator

    if not orchestrator:
        return OrchestratorSettingsResponse(
            end_pause_seconds=2.0,
            listening_timeout_seconds=10.0,
            status="orchestrator_not_ready"
        )

    return OrchestratorSettingsResponse(
        end_pause_seconds=orchestrator.end_pause_seconds,
        listening_timeout_seconds=orchestrator.listening_timeout,
        status="active"
    )


async def main():
    """메인 진입점"""
    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=11007,
        log_level="info"
    )
    server = uvicorn.Server(config)
    await server.serve()


if __name__ == "__main__":
    asyncio.run(main())
