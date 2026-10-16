"""
Log Broadcaster Service
Phase 26: Log Streaming 실시간 연동

로그를 Redis Pub/Sub을 통해 브로드캐스트합니다.
"""
import json
import os
from typing import Optional, Dict, Any

import redis.asyncio as redis
# Phase 31.2: 채널 통합 (edgevoice:logs -> edgevoice:logs:pipeline)
from ..constants.redis_channels import RedisChannels

# Redis 로그 채널 (log_subscriber.py와 동일)
LOGS_CHANNEL = RedisChannels.PIPELINE_LOGS  # "edgevoice:logs:pipeline"


class LogBroadcaster:
    """
    Redis Pub/Sub 로그 브로드캐스터

    로그 데이터를 Redis 채널로 발행하여
    구독자(SSE 클라이언트)에게 실시간 전달합니다.
    """

    def __init__(self, redis: Optional[redis.Redis] = None):
        """
        LogBroadcaster 초기화

        Args:
            redis: Redis 클라이언트 (없으면 환경변수로 연결)
        """
        self._redis = redis
        self._connected = False

    async def _ensure_redis(self) -> redis.Redis:
        """Redis 연결 확보"""
        if self._redis is None:
            host = os.getenv("REDIS_HOST", "localhost")
            port = int(os.getenv("REDIS_PORT", "6379"))
            self._redis = redis.Redis(host=host, port=port, decode_responses=True)
            self._connected = True
        return self._redis

    async def broadcast(self, log_data: Dict[str, Any]) -> bool:
        """
        로그 데이터를 Redis 채널로 발행

        Args:
            log_data: 로그 데이터 딕셔너리

        Returns:
            발행 성공 여부
        """
        try:
            redis_client = await self._ensure_redis()

            message = {
                "type": "log",
                "data": log_data
            }

            await redis_client.publish(LOGS_CHANNEL, json.dumps(message))
            return True

        except Exception as e:
            print(f"[LogBroadcaster] Failed to broadcast: {e}")
            return False

    async def close(self) -> None:
        """리소스 정리"""
        if self._connected and self._redis:
            await self._redis.aclose()
            self._redis = None
            self._connected = False


# 싱글톤 인스턴스 (앱 전역에서 사용)
_broadcaster: Optional[LogBroadcaster] = None


async def get_log_broadcaster() -> LogBroadcaster:
    """LogBroadcaster 싱글톤 인스턴스 반환"""
    global _broadcaster
    if _broadcaster is None:
        _broadcaster = LogBroadcaster()
    return _broadcaster


async def broadcast_log(log_data: Dict[str, Any]) -> bool:
    """
    편의 함수: 로그 브로드캐스트

    Args:
        log_data: 로그 데이터

    Returns:
        발행 성공 여부
    """
    broadcaster = await get_log_broadcaster()
    return await broadcaster.broadcast(log_data)
