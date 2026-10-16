"""
Phase 35: LLM Loading Progress Monitor

LLM 컨테이너의 로딩 진행률을 모니터링하고 Pipeline Logs에 발행합니다.
Docker SDK를 사용하여 컨테이너 로그를 읽습니다.
"""
import asyncio
import json
import os
import re
from datetime import datetime
from typing import Optional

import redis.asyncio as redis

try:
    import docker
    DOCKER_SDK_AVAILABLE = True
except ImportError:
    DOCKER_SDK_AVAILABLE = False
    print("[LLM Monitor] Warning: docker SDK not available")


# Redis 채널 설정
LOGS_CHANNEL = "edgevoice:logs:pipeline"


class LLMLoadingMonitor:
    """
    LLM 로딩 진행률 모니터

    Docker SDK를 사용하여 로그를 파싱하고 진행률을 추출하여 Redis에 발행합니다.
    """

    def __init__(self):
        self.redis_client: Optional[redis.Redis] = None
        self.docker_client = None
        self._running = False
        self._last_progress = -1  # 마지막으로 발행한 진행률 (중복 방지)
        self._last_stage = ""

    async def connect(self):
        """Redis 및 Docker 연결"""
        # Redis 연결
        redis_host = os.getenv("REDIS_HOST", "redis")
        redis_port = int(os.getenv("REDIS_PORT", "6379"))

        self.redis_client = redis.Redis(
            host=redis_host,
            port=redis_port,
            decode_responses=True
        )
        print("[LLM Monitor] Redis connected")

        # Docker 연결
        if DOCKER_SDK_AVAILABLE:
            try:
                self.docker_client = docker.from_env()
                print("[LLM Monitor] Docker SDK connected")
            except Exception as e:
                print(f"[LLM Monitor] Docker SDK connection failed: {e}")
                self.docker_client = None

    async def close(self):
        """연결 종료"""
        self._running = False
        if self.redis_client:
            await self.redis_client.aclose()
            self.redis_client = None
        if self.docker_client:
            self.docker_client.close()
            self.docker_client = None
        print("[LLM Monitor] Closed")

    async def publish_progress(self, progress_percent: int, stage: str, message: str):
        """
        진행률을 Pipeline Logs에 발행

        Args:
            progress_percent: 진행률 (0-100)
            stage: 로딩 단계
            message: 로그 메시지
        """
        if not self.redis_client:
            print(f"[LLM Monitor] Failed to publish: Redis not connected")
            return

        # 중복 발행 방지 (같은 진행률과 단계면 스킵)
        if progress_percent == self._last_progress and stage == self._last_stage:
            return

        self._last_progress = progress_percent
        self._last_stage = stage

        log_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "service": "llm",
            "event": "llm_loading_progress",
            "session_id": f"llm-loading-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}",
            "data": {
                "message": message,
                "progress_percent": progress_percent,
                "stage": stage
            },
            "level": "info"
        }

        try:
            await self.redis_client.publish(LOGS_CHANNEL, json.dumps(log_data))
            print(f"[LLM Monitor] Published: {stage} - {progress_percent}% - {message}")
        except Exception as e:
            print(f"[LLM Monitor] Failed to publish: {e}")

    def _get_docker_logs(self, container_name: str = "ev-llm", tail: int = 100) -> str:
        """
        Docker SDK를 사용하여 컨테이너 로그 조회

        Args:
            container_name: 컨테이너 이름
            tail: 마지막 N줄

        Returns:
            로그 텍스트
        """
        if not self.docker_client:
            return ""

        try:
            container = self.docker_client.containers.get(container_name)
            logs = container.logs(tail=tail, timestamps=False)
            if isinstance(logs, bytes):
                return logs.decode("utf-8", errors="ignore")
            return str(logs)
        except docker.errors.NotFound:
            print(f"[LLM Monitor] Container '{container_name}' not found")
            return ""
        except Exception as e:
            print(f"[LLM Monitor] Error getting docker logs: {e}")
            return ""

    async def get_llm_loading_progress(self) -> dict:
        """
        Docker logs에서 vLLM 로딩 진행률 조회

        Returns:
            진행률 정보 딕셔너리
        """
        default_result = {
            "progress_percent": 0,
            "stage": "unknown",
            "message": "Unable to determine loading progress"
        }

        try:
            # Docker SDK를 사용하여 로그 조회 (동기 호출을 별도 스레드에서 실행)
            loop = asyncio.get_event_loop()
            logs = await loop.run_in_executor(None, self._get_docker_logs, "ev-llm", 100)

            if not logs:
                return default_result

            # 로그를 줄 단위로 역순 파싱
            lines = logs.strip().split("\n")
            for line in reversed(lines):
                result = self._parse_progress(line)
                if result:
                    return result

            return default_result

        except Exception as e:
            print(f"[LLM Monitor] Error getting logs: {e}")
            return default_result

    def _parse_progress(self, log_text: str) -> Optional[dict]:
        """vLLM 로그 파싱"""
        if not log_text:
            return None

        # 패턴 1: Application startup complete
        if "application startup complete" in log_text.lower():
            print(f"[LLM Monitor] Pattern matched: startup complete")
            return {
                "progress_percent": 100,
                "stage": "complete",
                "message": "Model loaded successfully"
            }

        # 패턴 2: safetensors checkpoint shards
        match = re.search(r"Loading safetensors checkpoint shards:\s*(\d+)%", log_text)
        if match:
            percent = int(match.group(1))
            print(f"[LLM Monitor] Pattern matched: safetensors {percent}%")
            return {
                "progress_percent": percent,
                "stage": "loading_weights",
                "message": f"Loading: {percent}%"
            }

        # 패턴 3: 모델 가중치 로딩 (기존 패턴)
        match = re.search(r"Loading model weights:\s*(\d+)%", log_text)
        if match:
            percent = int(match.group(1))
            print(f"[LLM Monitor] Pattern matched: weights {percent}%")
            return {
                "progress_percent": percent,
                "stage": "loading_weights",
                "message": f"Loading: {percent}%"
            }

        # 패턴 4: CUDA graphs
        match = re.search(r"Capturing CUDA graphs.*?:\s*(\d+)%", log_text)
        if match:
            percent = int(match.group(1))
            adjusted = 90 + int(percent * 0.1)
            print(f"[LLM Monitor] Pattern matched: CUDA graphs {percent}% -> {adjusted}%")
            return {
                "progress_percent": adjusted,
                "stage": "cuda_graphs",
                "message": f"Optimizing: {adjusted}%"
            }

        # 패턴 5: Starting to load
        if "starting to load model" in log_text.lower():
            print(f"[LLM Monitor] Pattern matched: starting to load")
            return {
                "progress_percent": 5,
                "stage": "starting",
                "message": "Starting..."
            }

        # 패턴 6: Initializing
        if "initializing" in log_text.lower() or "init engine" in log_text.lower():
            print(f"[LLM Monitor] Pattern matched: initializing")
            return {
                "progress_percent": 0,
                "stage": "initializing",
                "message": "Starting..."
            }

        return None

    async def check_llm_health(self) -> bool:
        """LLM 서비스 health check (HTTP 사용)"""
        import aiohttp

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "http://llm:11003/health",
                    timeout=aiohttp.ClientTimeout(total=3)
                ) as response:
                    return response.status == 200
        except Exception:
            pass
        return False

    async def monitor(self):
        """
        LLM 로딩 모니터링 메인 루프

        LLM이 healthy가 될 때까지 진행률을 모니터링하고 발행합니다.
        """
        self._running = True

        try:
            await self.connect()

            # 초기 상태 발행
            await self.publish_progress(0, "initializing", "Starting LLM service...")

            while self._running:
                # LLM health check
                is_healthy = await self.check_llm_health()

                if is_healthy:
                    # 로딩 완료
                    await self.publish_progress(100, "complete", "Model loaded successfully")
                    print("[LLM Monitor] LLM is healthy, monitoring complete")
                    break

                # 진행률 조회 및 발행
                progress = await self.get_llm_loading_progress()
                await self.publish_progress(
                    progress["progress_percent"],
                    progress["stage"],
                    progress["message"]
                )

                # 2초 대기
                await asyncio.sleep(2)

        except asyncio.CancelledError:
            print("[LLM Monitor] Cancelled")
        except Exception as e:
            print(f"[LLM Monitor] Error: {e}")
        finally:
            await self.close()


# 모니터 인스턴스
_monitor: Optional[LLMLoadingMonitor] = None
_monitor_task: Optional[asyncio.Task] = None


async def start_llm_monitor():
    """LLM 로딩 모니터 시작"""
    global _monitor, _monitor_task

    _monitor = LLMLoadingMonitor()
    _monitor_task = asyncio.create_task(_monitor.monitor())
    print("[LLM Monitor] Started")


async def stop_llm_monitor():
    """LLM 로딩 모니터 중지"""
    global _monitor, _monitor_task

    if _monitor:
        _monitor._running = False

    if _monitor_task:
        _monitor_task.cancel()
        try:
            await _monitor_task
        except asyncio.CancelledError:
            pass
        _monitor_task = None

    _monitor = None
    print("[LLM Monitor] Stopped")