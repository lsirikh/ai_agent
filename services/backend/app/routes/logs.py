"""
Backend API - Pipeline Logs Routes

Phase 17: Pipeline Logging System
Phase 26: Redis Pub/Sub 기반 실시간 로그 스트리밍
- Real-time log streaming via SSE with Redis Pub/Sub
- CRUD operations for pipeline logs
- Log filtering and statistics
"""
import asyncio
import json
import os
from datetime import datetime, timedelta
from typing import Optional, AsyncGenerator, Any
from uuid import UUID

import redis.asyncio as redis
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..repositories.pipeline_log_repository import PipelineLogRepository
from ..services.log_broadcaster import broadcast_log, LOGS_CHANNEL

router = APIRouter(prefix="/api/logs", tags=["logs"])


# Redis 연결 설정
def _get_redis_url() -> str:
    host = os.getenv("REDIS_HOST", "localhost")
    port = os.getenv("REDIS_PORT", "6379")
    return f"redis://{host}:{port}"


async def create_log_event_generator(
    pubsub: Optional[Any] = None,
    level: Optional[str] = None,
    service: Optional[str] = None
) -> AsyncGenerator[str, None]:
    """
    Redis Pub/Sub 기반 로그 이벤트 제너레이터

    Phase 26.3: Redis 구독을 통해 실시간 로그를 SSE로 전달
    Phase 34.5: 타임아웃 기반 heartbeat로 변경 (블로킹 방지)

    Args:
        pubsub: Redis PubSub 객체 (테스트용 mock 가능)
        level: 로그 레벨 필터
        service: 서비스 이름 필터

    Yields:
        SSE 형식의 로그 이벤트
    """
    own_pubsub = False
    redis_client = None

    # pubsub이 없으면 새로 생성
    if pubsub is None:
        try:
            redis_client = redis.from_url(_get_redis_url(), decode_responses=False)
            pubsub = redis_client.pubsub()
            await pubsub.subscribe(LOGS_CHANNEL)
            own_pubsub = True
        except Exception as e:
            yield f"event: error\ndata: {json.dumps({'error': f'Redis connection failed: {e}'})}\n\n"
            return

    # 연결 이벤트 전송
    yield f"event: connected\ndata: {json.dumps({'status': 'connected', 'channel': LOGS_CHANNEL})}\n\n"

    last_heartbeat = datetime.utcnow()
    heartbeat_interval = 5  # 5초마다 heartbeat

    try:
        while True:
            # Phase 34.5: Non-blocking 메시지 수신 + sleep으로 heartbeat 체크
            # get_message(timeout=0.5)은 최대 0.5초 대기 후 None 반환
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.5)

            if message and message["type"] == "message":
                try:
                    data = message["data"]
                    if isinstance(data, bytes):
                        data = data.decode("utf-8")

                    parsed = json.loads(data)

                    # Phase 34.5: 두 가지 형식 지원
                    # 형식 1: LogBroadcaster에서 발행 {"type": "log", "data": {...}}
                    # 형식 2: PipelineLogger에서 직접 발행 {"service": "...", "event": "...", ...}
                    if parsed.get("type") == "log":
                        log_data = parsed.get("data", {})
                    elif parsed.get("service") and parsed.get("event"):
                        # PipelineLogger 형식 -> LogResponse 호환 형식으로 변환
                        log_data = {
                            "id": "",
                            "session_id": parsed.get("session_id"),
                            "service": parsed.get("service", "unknown"),
                            "stage": parsed.get("event", "general"),
                            "level": (parsed.get("level") or "INFO").upper(),
                            "message": parsed.get("data", {}).get("message", f"{parsed.get('service')}:{parsed.get('event')}"),
                            "duration_ms": parsed.get("data", {}).get("duration_ms"),
                            "metadata": parsed.get("data", {}),
                            "created_at": parsed.get("timestamp", datetime.utcnow().isoformat())
                        }
                    else:
                        continue

                    # 필터 적용
                    log_level = (log_data.get("level") or "").upper()
                    log_service = log_data.get("service") or ""
                    if level and log_level != level.upper():
                        continue
                    if service and log_service != service:
                        continue

                    yield f"event: log\ndata: {json.dumps(log_data)}\n\n"

                except json.JSONDecodeError:
                    pass
                except Exception as e:
                    yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"

            # 주기적 heartbeat 전송
            now = datetime.utcnow()
            if (now - last_heartbeat).total_seconds() >= heartbeat_interval:
                yield f"event: heartbeat\ndata: {json.dumps({'timestamp': now.isoformat()})}\n\n"
                last_heartbeat = now

    except asyncio.CancelledError:
        pass
    except GeneratorExit:
        pass
    finally:
        if own_pubsub and pubsub:
            try:
                await pubsub.unsubscribe(LOGS_CHANNEL)
                await pubsub.close()
            except Exception:
                pass
        if own_pubsub and redis_client:
            try:
                await redis_client.aclose()
            except Exception:
                pass


class LogCreate(BaseModel):
    service: str
    stage: str
    message: str
    level: str = "INFO"
    session_id: Optional[str] = None
    duration_ms: Optional[int] = None
    metadata: Optional[dict] = None


class LogResponse(BaseModel):
    id: str
    session_id: Optional[str]
    service: str
    stage: str
    level: str
    message: str
    duration_ms: Optional[int]
    metadata: dict
    created_at: str


class LogStats(BaseModel):
    total: int
    by_service: dict
    by_level: dict
    period_hours: int


@router.get("", response_model=list[LogResponse])
async def list_logs(
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    level: Optional[str] = Query(default=None),
    service: Optional[str] = Query(default=None)
):
    """
    List recent pipeline logs with optional filtering.

    Args:
        limit: Maximum number of logs to return
        offset: Number of logs to skip (for pagination)
        level: Filter by log level (DEBUG, INFO, WARNING, ERROR)
        service: Filter by service name

    Returns:
        List of log entries
    """
    repo = PipelineLogRepository()
    logs = await repo.list_recent(
        limit=limit,
        offset=offset,
        level=level,
        service=service
    )
    return logs


@router.get("/stream")
async def stream_logs(
    level: Optional[str] = Query(default=None),
    service: Optional[str] = Query(default=None)
):
    """
    Stream logs in real-time via Server-Sent Events (SSE).

    Phase 26.3: Redis Pub/Sub 기반 실시간 스트리밍으로 변경

    Args:
        level: Filter by log level
        service: Filter by service name

    Returns:
        SSE stream of new log entries
    """
    return StreamingResponse(
        create_log_event_generator(level=level, service=service),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@router.get("/stats", response_model=LogStats)
async def get_log_stats(
    hours: int = Query(default=24, ge=1, le=168)
):
    """
    Get log statistics for the specified time period.

    Args:
        hours: Number of hours to look back (max 168 = 1 week)

    Returns:
        Statistics with counts by service and level
    """
    repo = PipelineLogRepository()
    stats = await repo.get_stats(hours=hours)
    return stats


@router.get("/session/{session_id}", response_model=list[LogResponse])
async def get_session_logs(
    session_id: UUID,
    limit: int = Query(default=100, ge=1, le=1000)
):
    """
    Get logs for a specific session.

    Args:
        session_id: Session UUID
        limit: Maximum number of logs to return

    Returns:
        List of log entries for the session
    """
    repo = PipelineLogRepository()
    logs = await repo.list_by_session(session_id, limit=limit)
    return logs


@router.get("/service/{service_name}", response_model=list[LogResponse])
async def get_service_logs(
    service_name: str,
    limit: int = Query(default=100, ge=1, le=1000)
):
    """
    Get logs for a specific service.

    Args:
        service_name: Service name (orchestrator, stt, tts, llm, etc.)
        limit: Maximum number of logs to return

    Returns:
        List of log entries for the service
    """
    valid_services = ["orchestrator", "stt", "tts", "llm", "embedding", "wake_word", "rag", "audio_gateway"]
    if service_name not in valid_services:
        raise HTTPException(status_code=404, detail=f"Unknown service: {service_name}")

    repo = PipelineLogRepository()
    logs = await repo.list_by_service(service_name, limit=limit)
    return logs


@router.post("", response_model=LogResponse, status_code=201)
async def create_log(log: LogCreate):
    """
    Create a new pipeline log entry.

    This endpoint is used by services to log pipeline events.

    Args:
        log: Log entry data

    Returns:
        Created log entry
    """
    repo = PipelineLogRepository()

    session_uuid = UUID(log.session_id) if log.session_id else None

    log_id = await repo.create(
        service=log.service,
        stage=log.stage,
        message=log.message,
        level=log.level,
        session_id=session_uuid,
        duration_ms=log.duration_ms,
        metadata=log.metadata
    )

    # Fetch and return the created log
    created_log = await repo.get_by_id(log_id)
    if not created_log:
        raise HTTPException(status_code=500, detail="Failed to create log")

    # Phase 26.2: 로그를 Redis로 브로드캐스트
    try:
        await broadcast_log(created_log)
    except Exception as e:
        # 브로드캐스트 실패해도 로그 생성은 성공으로 처리
        print(f"[logs] Failed to broadcast log: {e}")

    return created_log


@router.delete("/{log_id}", status_code=204)
async def delete_log(log_id: UUID):
    """
    Delete a specific log entry.

    Args:
        log_id: Log UUID
    """
    repo = PipelineLogRepository()
    deleted = await repo.delete(log_id)

    if not deleted:
        raise HTTPException(status_code=404, detail="Log not found")


@router.delete("/cleanup", status_code=200)
async def cleanup_old_logs(
    days: int = Query(default=7, ge=1, le=30)
):
    """
    Delete logs older than the specified number of days.

    Args:
        days: Number of days to keep logs

    Returns:
        Number of deleted logs
    """
    repo = PipelineLogRepository()
    deleted_count = await repo.delete_older_than(days=days)

    return {"deleted_count": deleted_count}
