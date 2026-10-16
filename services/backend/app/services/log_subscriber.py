"""
Log Subscriber Service
Phase 26: Log Streaming 실시간 연동
Phase 31.3: DB 저장 로직 추가

Redis Pub/Sub을 통해 로그 메시지를 구독하고 DB에 저장합니다.
"""
import asyncio
import json
import os
from typing import Optional, Callable, Any
from uuid import UUID

import redis.asyncio as redis


# Redis 로그 채널 - shared/pipeline_logger와 동일한 채널 사용
# Phase 31.2: 채널 통합 (edgevoice:logs -> edgevoice:logs:pipeline)
from ..constants.redis_channels import RedisChannels
from ..repositories.pipeline_log_repository import PipelineLogRepository

LOGS_CHANNEL = RedisChannels.PIPELINE_LOGS  # "edgevoice:logs:pipeline"


class LogSubscriber:
    """
    Redis Pub/Sub 로그 구독자

    다른 서비스에서 발행하는 로그 메시지를 구독하고
    콜백 함수를 통해 처리합니다.
    """

    def __init__(
        self,
        redis_client: Optional[redis.Redis] = None,
        on_log: Optional[Callable[[dict], Any]] = None
    ):
        """
        LogSubscriber 초기화

        Args:
            redis_client: Redis 클라이언트 (없으면 환경변수로 연결)
            on_log: 로그 수신 시 호출할 콜백 함수
        """
        self._redis = redis_client
        self._on_log = on_log
        self._pubsub: Optional[redis.client.PubSub] = None
        self._running = False

    async def _ensure_redis(self) -> redis.Redis:
        """Redis 연결 확보"""
        if self._redis is None:
            host = os.getenv("REDIS_HOST", "localhost")
            port = int(os.getenv("REDIS_PORT", "6379"))
            self._redis = redis.Redis(host=host, port=port, decode_responses=False)
        return self._redis

    async def subscribe(self) -> None:
        """
        로그 채널 구독 시작

        LOGS_CHANNEL을 구독하고 메시지를 수신합니다.
        """
        redis_client = await self._ensure_redis()
        self._pubsub = redis_client.pubsub()
        await self._pubsub.subscribe(LOGS_CHANNEL)
        self._running = True

        print(f"[LogSubscriber] Subscribed to {LOGS_CHANNEL}")

    async def listen(self):
        """
        메시지 수신 루프

        Phase 31.3: 구독한 채널에서 메시지를 수신하고 DB에 저장합니다.
        """
        if self._pubsub is None:
            await self.subscribe()

        # Phase 31.3: DB 저장을 위한 Repository 인스턴스
        repo = PipelineLogRepository()

        async for message in self._pubsub.listen():
            if not self._running:
                break

            if message["type"] == "message":
                try:
                    data = message["data"]
                    if isinstance(data, bytes):
                        data = data.decode("utf-8")

                    log_data = json.loads(data)

                    # Phase 31.3: DB에 로그 저장
                    await self._save_log_to_db(repo, log_data)

                    if self._on_log:
                        await self._on_log(log_data)

                except json.JSONDecodeError as e:
                    print(f"[LogSubscriber] JSON decode error: {e}")
                except Exception as e:
                    print(f"[LogSubscriber] Error processing message: {e}")

    async def _save_log_to_db(self, repo: PipelineLogRepository, log_data: dict) -> None:
        """
        Phase 31.3: 로그 데이터를 DB에 저장

        PipelineLogger가 발행하는 로그 형식:
        {
            "timestamp": "2025-12-12T10:00:00",
            "service": "stt",
            "event": "heartbeat",
            "session_id": null,
            "data": {"message": "STT Service alive", ...},
            "level": "info"
        }
        """
        try:
            # 세션 ID 파싱 (UUID 문자열 → UUID 객체)
            session_id = None
            raw_session_id = log_data.get("session_id")
            if raw_session_id:
                try:
                    session_id = UUID(raw_session_id)
                except (ValueError, TypeError):
                    pass

            # 로그 데이터 추출
            service = log_data.get("service", "unknown")
            event = log_data.get("event", "general")
            level = log_data.get("level", "INFO").upper()
            data = log_data.get("data", {})

            # 메시지 추출 (data 내부 또는 직접)
            message = data.get("message", "") if isinstance(data, dict) else str(data)
            if not message:
                message = f"{service}:{event}"

            # duration_ms 추출
            duration_ms = None
            if isinstance(data, dict):
                duration_ms = data.get("duration_ms")

            # metadata 추출 (data에서 message, duration_ms 제외)
            metadata = {}
            if isinstance(data, dict):
                metadata = {k: v for k, v in data.items() if k not in ("message", "duration_ms")}
            metadata["timestamp"] = log_data.get("timestamp")

            # DB에 저장
            await repo.create(
                service=service,
                stage=event,
                message=message,
                level=level,
                session_id=session_id,
                duration_ms=duration_ms,
                metadata=metadata
            )

        except Exception as e:
            # DB 저장 실패해도 로그 수신은 계속
            print(f"[LogSubscriber] DB save failed: {e}")

    async def stop(self) -> None:
        """구독 중지"""
        self._running = False
        if self._pubsub:
            await self._pubsub.unsubscribe(LOGS_CHANNEL)
            await self._pubsub.close()
            self._pubsub = None
        print("[LogSubscriber] Stopped")

    async def close(self) -> None:
        """리소스 정리"""
        await self.stop()
        if self._redis:
            await self._redis.aclose()
            self._redis = None
