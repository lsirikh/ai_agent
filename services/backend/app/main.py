"""
Backend API Main

Phase 5: Backend API FastAPI 애플리케이션
Phase 14.1: Database Lifespan 연동
Phase 16: Settings-Environment 동기화
Phase 26: Log Subscriber 백그라운드 태스크
"""
import asyncio
import os
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from .routes import chat, dashboard, debug, history, knowledge, logs, orchestrator, sessions, settings, status
from .routes.settings import (
    load_all_settings_from_db,
    propagate_all_settings_to_services,
    get_current_settings_as_dict,
)
from .database import get_db_manager
from .database.connection import connect_with_retry
from .services import conversation
from .services.settings_env_sync import sync_settings_to_env
from .services.log_subscriber import LogSubscriber
from .services.llm_loading_monitor import start_llm_monitor, stop_llm_monitor


# Database manager for health check
_db_connected = False

# Phase 26: Log Subscriber 인스턴스
_log_subscriber: Optional[LogSubscriber] = None
_log_subscriber_task: Optional[asyncio.Task] = None

# Phase 35: LLM Loading Monitor 인스턴스
_llm_monitor_task: Optional[asyncio.Task] = None


async def start_log_subscriber():
    """
    Log Subscriber 백그라운드 태스크 시작

    Phase 26.4: Redis Pub/Sub을 통해 로그를 구독합니다.
    """
    global _log_subscriber, _log_subscriber_task

    try:
        _log_subscriber = LogSubscriber()
        await _log_subscriber.subscribe()

        # 백그라운드에서 listen 실행
        _log_subscriber_task = asyncio.create_task(_log_subscriber.listen())
        print("[Backend] Log subscriber started")
    except Exception as e:
        print(f"[Backend] Log subscriber failed to start: {e}")


async def stop_log_subscriber():
    """Log Subscriber 중지"""
    global _log_subscriber, _log_subscriber_task

    if _log_subscriber_task:
        _log_subscriber_task.cancel()
        try:
            await _log_subscriber_task
        except asyncio.CancelledError:
            pass
        _log_subscriber_task = None

    if _log_subscriber:
        await _log_subscriber.close()
        _log_subscriber = None

    print("[Backend] Log subscriber stopped")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan with database connection management.

    Phase 14.1: DB 연결/해제 관리
    """
    global _db_connected

    # === Startup ===
    print("[Backend] Starting up...")

    # 1. Database 연결
    db_manager = get_db_manager()
    try:
        # 재시작 직후 Postgres 가 아직 준비 중일 수 있어 준비될 때까지 재시도한다
        await connect_with_retry(db_manager)
        _db_connected = True
        print("[Backend] Database connected")
        await conversation.ensure_schema()
    except Exception as e:
        print(f"[Backend] Database connection failed: {e}")
        print("[Backend] Running without database (in-memory fallback)")
        _db_connected = False

    # 2. 설정 로드 (Phase 16.1)
    try:
        await load_all_settings_from_db()
        print("[Backend] Settings loaded from DB")
    except Exception as e:
        print(f"[Backend] Settings load failed: {e}")

    # 3. 설정을 .env에 동기화 (Phase 16)
    try:
        settings_dict = get_current_settings_as_dict()
        sync_settings_to_env(settings_dict)
        print("[Backend] Settings synced to .env")
    except Exception as e:
        print(f"[Backend] .env sync failed: {e}")

    # 4. 설정 전파 (Phase 16.4)
    try:
        await propagate_all_settings_to_services()
        print("[Backend] Settings propagated to services")
    except Exception as e:
        print(f"[Backend] Settings propagation failed: {e}")

    # 5. Log Subscriber 시작 (Phase 26.4)
    try:
        await start_log_subscriber()
    except Exception as e:
        print(f"[Backend] Log subscriber start failed: {e}")

    # 6. LLM Loading Monitor 시작 (Phase 35)
    try:
        await start_llm_monitor()
        print("[Backend] LLM loading monitor started")
    except Exception as e:
        print(f"[Backend] LLM loading monitor start failed: {e}")

    # 7. MCP 서버 연결 (MCP_CONFIG_PATH 가 있을 때만)
    try:
        await chat.start_mcp()
    except Exception as e:
        print(f"[Backend] MCP start failed: {e}")

    yield

    # === Shutdown ===
    print("[Backend] Shutting down...")

    try:
        await chat.stop_mcp()
    except Exception as e:
        print(f"[Backend] MCP stop failed: {e}")

    # LLM Monitor 중지 (Phase 35)
    try:
        await stop_llm_monitor()
    except Exception as e:
        print(f"[Backend] LLM monitor stop error: {e}")

    # Log Subscriber 중지 (Phase 26.4)
    try:
        await stop_log_subscriber()
    except Exception as e:
        print(f"[Backend] Log subscriber stop error: {e}")

    # Database 연결 해제
    if _db_connected:
        try:
            await db_manager.disconnect()
            print("[Backend] Database disconnected")
        except Exception as e:
            print(f"[Backend] Database disconnect error: {e}")

    _db_connected = False
    print("[Backend] Shutdown complete")


# FastAPI 앱 생성 with lifespan
app = FastAPI(
    title="EdgeVoice Backend API",
    description="EdgeVoice Backend API Service",
    version="0.1.0",
    lifespan=lifespan
)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 라우터 등록
app.include_router(status.router)
app.include_router(settings.router)
app.include_router(settings.services_router)  # Phase 13.6: Service restart endpoints
app.include_router(knowledge.router)
app.include_router(history.router)
app.include_router(debug.router)
app.include_router(chat.router)
app.include_router(sessions.router)  # Phase 15.4: Session Context endpoints
app.include_router(logs.router)  # Phase 17: Pipeline Logging System
app.include_router(orchestrator.router)  # Phase 18.1: Orchestrator State API
app.include_router(dashboard.router)  # Phase 28.2: Dashboard Init + SSE API


# Static 파일 디렉토리 설정
STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# 루트 경로 - Dashboard
@app.get("/")
async def root():
    """웹 대시보드 메인 페이지"""
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "EdgeVoice Backend API", "docs": "/docs"}


# Health 엔드포인트
@app.get("/health")
async def health():
    """
    헬스 체크 엔드포인트

    Phase 14.1: 데이터베이스 상태 포함

    Returns:
        서비스 상태 정보 (database 상태 포함)
    """
    db_manager = get_db_manager()
    db_healthy = await db_manager.health_check() if db_manager.is_connected else False

    return {
        "status": "healthy" if db_healthy else "degraded",
        "service": "backend",
        "database": "connected" if db_healthy else "disconnected"
    }
