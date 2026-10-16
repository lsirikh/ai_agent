"""
Pipeline Logger 공유 클래스

모든 서비스에서 동일한 방식으로 파이프라인 로그를 생성하고
Redis를 통해 전파합니다.

Phase 31.4: Redis 자동 연결 로직 추가
"""
from typing import Optional, Dict, Any
from datetime import datetime
import json
import os


class PipelineLogger:
    """
    파이프라인 로깅을 위한 공유 클래스

    모든 서비스에서 동일한 방식으로 파이프라인 로그를 생성하고
    Redis를 통해 전파합니다.
    """

    DEFAULT_CHANNEL = "edgevoice:logs:pipeline"

    def __init__(
        self,
        service_name: str,
        redis_client: Optional[Any] = None,
        channel: str = None,
        auto_connect: bool = True
    ):
        """
        PipelineLogger 초기화

        Args:
            service_name: 서비스 이름 (예: "orchestrator", "stt", "tts")
            redis_client: Redis 클라이언트 (옵션)
            channel: Redis Pub/Sub 채널 (기본값: edgevoice:logs:pipeline)
            auto_connect: True이면 redis_client가 없을 때 자동으로 Redis 연결
        """
        self.service_name = service_name
        self.redis = redis_client
        self.channel = channel or self.DEFAULT_CHANNEL
        self._auto_connect = auto_connect
        self._connection_attempted = False

    async def _ensure_redis(self) -> None:
        """
        Phase 31.4: Redis 연결 확보

        redis_client가 없고 auto_connect가 True이면 자동으로 연결을 시도합니다.
        """
        if self.redis is not None:
            return

        if not self._auto_connect or self._connection_attempted:
            return

        self._connection_attempted = True

        try:
            import redis.asyncio as redis_lib
            host = os.getenv("REDIS_HOST", "redis")
            port = int(os.getenv("REDIS_PORT", "6379"))
            self.redis = redis_lib.Redis(host=host, port=port, decode_responses=True)
            # 연결 테스트
            await self.redis.ping()
        except Exception as e:
            print(f"[PipelineLogger] Redis auto-connect failed: {e}")
            self.redis = None

    async def log(
        self,
        event: str,
        session_id: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
        level: str = "info"
    ) -> Dict[str, Any]:
        """
        파이프라인 이벤트 로깅

        Args:
            event: 이벤트 이름 (예: "stt_start", "llm_complete")
            session_id: 세션 ID
            data: 추가 데이터
            level: 로그 레벨 (info, warning, error)

        Returns:
            생성된 로그 엔트리
        """
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "service": self.service_name,
            "event": event,
            "session_id": session_id,
            "data": data or {},
            "level": level
        }

        # Phase 31.4: Redis 자동 연결
        await self._ensure_redis()

        if self.redis:
            try:
                await self.redis.publish(self.channel, json.dumps(log_entry))
            except Exception as e:
                print(f"[PipelineLogger] Redis publish failed: {e}")

        return log_entry

    async def log_stage_start(
        self,
        stage: str,
        session_id: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        파이프라인 스테이지 시작 로깅

        Args:
            stage: 스테이지 이름 (예: "stt", "llm", "tts")
            session_id: 세션 ID
            **kwargs: 추가 데이터

        Returns:
            생성된 로그 엔트리
        """
        return await self.log(
            event=f"{stage}_start",
            session_id=session_id,
            data={"stage": stage, **kwargs}
        )

    async def log_stage_complete(
        self,
        stage: str,
        session_id: str,
        duration_ms: Optional[float] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        파이프라인 스테이지 완료 로깅

        Args:
            stage: 스테이지 이름
            session_id: 세션 ID
            duration_ms: 처리 시간 (밀리초)
            **kwargs: 추가 데이터

        Returns:
            생성된 로그 엔트리
        """
        data = {"stage": stage, **kwargs}
        if duration_ms is not None:
            data["duration_ms"] = duration_ms

        return await self.log(
            event=f"{stage}_complete",
            session_id=session_id,
            data=data
        )

    async def log_error(
        self,
        error: str,
        session_id: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        에러 로깅

        Args:
            error: 에러 메시지
            session_id: 세션 ID
            **kwargs: 추가 데이터

        Returns:
            생성된 로그 엔트리
        """
        return await self.log(
            event="error",
            session_id=session_id,
            data={"error": error, **kwargs},
            level="error"
        )

    # ============================================
    # 표준 로깅 API 호환 메서드들
    # ============================================

    async def info(
        self,
        message: str,
        session_id: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        INFO 레벨 로깅 (표준 logging API 호환)

        Args:
            message: 로그 메시지
            session_id: 세션 ID
            **kwargs: 추가 데이터

        Returns:
            생성된 로그 엔트리
        """
        return await self.log(
            event="info",
            session_id=session_id,
            data={"message": message, **kwargs},
            level="info"
        )

    async def warning(
        self,
        message: str,
        session_id: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        WARNING 레벨 로깅 (표준 logging API 호환)

        Args:
            message: 로그 메시지
            session_id: 세션 ID
            **kwargs: 추가 데이터

        Returns:
            생성된 로그 엔트리
        """
        return await self.log(
            event="warning",
            session_id=session_id,
            data={"message": message, **kwargs},
            level="warning"
        )

    async def error(
        self,
        message: str,
        session_id: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        ERROR 레벨 로깅 (표준 logging API 호환)

        Args:
            message: 로그 메시지
            session_id: 세션 ID
            **kwargs: 추가 데이터

        Returns:
            생성된 로그 엔트리
        """
        return await self.log(
            event="error",
            session_id=session_id,
            data={"message": message, **kwargs},
            level="error"
        )

    async def debug(
        self,
        message: str,
        session_id: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        DEBUG 레벨 로깅 (표준 logging API 호환)

        Args:
            message: 로그 메시지
            session_id: 세션 ID
            **kwargs: 추가 데이터

        Returns:
            생성된 로그 엔트리
        """
        return await self.log(
            event="debug",
            session_id=session_id,
            data={"message": message, **kwargs},
            level="debug"
        )

    async def close(self) -> None:
        """
        Phase 31.4: Redis 연결 정리

        자동으로 생성된 Redis 연결을 닫습니다.
        """
        if self.redis and self._auto_connect:
            try:
                await self.redis.aclose()
            except Exception:
                pass
            self.redis = None