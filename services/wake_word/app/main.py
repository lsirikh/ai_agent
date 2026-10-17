"""
Wake Word Service Main

Phase 3.1: OpenWakeWord 기반 Wake Word 감지 서비스
HTTP health endpoint + Redis Stream Processor

Phase 17.1: Pipeline Logging 추가
Phase 17.2: Service Heartbeat Logging (10초 간격)
Phase 40: OpenWakeWord 실제 모델 통합, 동적 Wake Word 변경
"""
import asyncio
import json
import os
import time
from contextlib import asynccontextmanager
from typing import Optional

import numpy as np
import redis.asyncio as redis
import uvicorn
from fastapi import FastAPI

from .detector import WakeWordDetector, WAKE_WORD_MODELS
from .pipeline_logger import get_logger, HEARTBEAT_INTERVAL
from .stt_check import make_verifier


ORCHESTRATOR_STATE_CHANNEL = "edgevoice:orchestrator:state"
# 이 상태에서 들린 호출어는 끼어들기다
ANSWERING_STATES = {"STT_PROCESSING", "LLM_PROCESSING", "TTS_PROCESSING", "SPEAKING"}


class WakeWordService:
    """
    Wake Word 감지 서비스

    오디오 스트림에서 Wake Word를 감지하고 Redis로 이벤트를 발행합니다.
    """

    def __init__(
        self,
        detector: Optional[WakeWordDetector] = None,
        redis_client: Optional[redis.Redis] = None,
        audio_channel: str = "edgevoice:audio:input",
        chunk_size: int = 1600,  # 100ms at 16kHz
    ):
        """
        WakeWordService 초기화

        Args:
            detector: WakeWordDetector 인스턴스
            redis_client: Redis 클라이언트
            audio_channel: 오디오 입력 채널
            chunk_size: 오디오 청크 크기
        """
        self.detector = detector
        self.redis_client = redis_client
        self.audio_channel = audio_channel
        self.chunk_size = chunk_size
        self._running = False
        self._logger = get_logger("wake_word")

    async def start(self) -> None:
        """서비스 시작"""
        if not self.detector:
            self.detector = WakeWordDetector(
                redis_client=self.redis_client
            )

        self._running = True
        print("Wake Word Service started")

        await self._logger.info(
            "wake_word_service_started",
            "Wake Word Service started, listening for wake words",
            metadata={"audio_channel": self.audio_channel}
        )

    async def stop(self) -> None:
        """서비스 중지"""
        self._running = False
        print("Wake Word Service stopped")

        await self._logger.info(
            "wake_word_service_stopped",
            "Wake Word Service stopped"
        )

    async def heartbeat_task(self) -> None:
        """
        하트비트 로그 태스크 (10초 간격)

        서비스 생존 확인을 위해 주기적으로 로그를 전송합니다.
        """
        start_time = time.time()
        while self._running:
            uptime_seconds = int(time.time() - start_time)
            await self._logger.info(
                "heartbeat",
                f"Wake Word Service alive (uptime: {uptime_seconds}s)",
                metadata={
                    "service": "wake_word",
                    "uptime_seconds": uptime_seconds,
                    "redis_connected": self.redis_client is not None
                }
            )
            await asyncio.sleep(HEARTBEAT_INTERVAL)

    def handle_state(self, data: dict) -> None:
        """오케스트레이터 상태 → 답하는 중인지(호출어 기준을 낮출지)."""
        state = data.get("new_state")
        if state and self.detector is not None:
            self.detector.answering = state in ANSWERING_STATES
            if state in ("LISTENING", "STT_PROCESSING"):
                # 듣는 동안 들어온 소리는 호출어가 아니다
                # (실측: 버퍼에 남은 '헤이 자…' 로 재감지돼 막 시작한 답을 취소했다)
                self.detector.clear_buffer()

    async def process_audio_stream(self) -> None:
        """
        오디오 스트림 처리 루프

        Redis에서 오디오 청크를 구독하고 Wake Word를 감지합니다.
        """
        if not self.redis_client:
            print("Warning: No Redis client configured")
            return

        pubsub = self.redis_client.pubsub()
        # 오케스트레이터 상태: 답하는 동안 호출어 기준을 낮춘다(끼어들기)
        await pubsub.subscribe(self.audio_channel, ORCHESTRATOR_STATE_CHANNEL)
        print(f"[WakeWord] Subscribed to {self.audio_channel}")

        chunk_count = 0
        try:
            while self._running:
                message = await pubsub.get_message(ignore_subscribe_messages=True)
                channel = message.get("channel") if message else None
                if isinstance(channel, bytes):
                    channel = channel.decode()
                if message and channel == ORCHESTRATOR_STATE_CHANNEL:
                    try:
                        self.handle_state(json.loads(message["data"]))
                    except (ValueError, TypeError):
                        pass
                elif message:
                    audio_data = message.get("data")
                    if isinstance(audio_data, bytes):
                        chunk_count += 1
                        # 첫 번째 청크 및 10 청크마다 로그
                        # Phase 43: log() 메서드 사용으로 event와 message 분리
                        if chunk_count == 1:
                            print(f"[WakeWord] First audio chunk received ({len(audio_data)} bytes)")
                            await self._logger.log(
                                event="audio_chunk_received",
                                data={
                                    "message": f"First audio chunk ({len(audio_data)} bytes)",
                                    "chunk_count": chunk_count,
                                    "bytes": len(audio_data)
                                },
                                level="debug"
                            )
                        elif chunk_count % 10 == 0:
                            print(f"[WakeWord] Received {chunk_count} audio chunks ({len(audio_data)} bytes)")
                            await self._logger.log(
                                event="audio_chunks_received",
                                data={
                                    "message": f"{chunk_count} chunks ({len(audio_data)} bytes)",
                                    "chunk_count": chunk_count,
                                    "bytes": len(audio_data)
                                },
                                level="debug"
                            )
                        # bytes를 numpy array로 변환
                        audio_chunk = np.frombuffer(audio_data, dtype=np.float32)
                        await self.detector.detect_and_publish(audio_chunk)

                await asyncio.sleep(0.01)  # 10ms 대기
        finally:
            await pubsub.unsubscribe(self.audio_channel)


# Global service instance
service: Optional[WakeWordService] = None
redis_client: Optional[redis.Redis] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan handler"""
    global service, redis_client

    # Startup
    redis_host = os.environ.get("REDIS_HOST", "localhost")
    redis_port = int(os.environ.get("REDIS_PORT", "6379"))
    confidence_threshold = float(os.environ.get("WAKE_WORD_THRESHOLD", "0.3"))
    environment = os.environ.get("WAKE_WORD_ENVIRONMENT", "development")
    wake_word = os.environ.get("WAKE_WORD", "hey_jarvis")

    print(f"Connecting to Redis at {redis_host}:{redis_port}...")

    try:
        redis_client = redis.Redis(
            host=redis_host,
            port=redis_port,
            decode_responses=False
        )
        # Test connection
        await redis_client.ping()
        print("Redis connection established")
    except Exception as e:
        print(f"Warning: Redis connection failed: {e}")
        redis_client = None

    # Create detector with OpenWakeWord model (Phase 40)
    detector = WakeWordDetector(
        confidence_threshold=confidence_threshold,
        environment=environment,
        redis_client=redis_client,
        wake_word=wake_word
    )
    stt_url = os.environ.get("STT_URL")
    if stt_url:
        # 애매한 점수는 STT 로 '자비스' 가 있는지 확인한다
        detector.verifier = make_verifier(stt_url)

    # Update global settings
    _current_settings["wake_word"] = wake_word
    _current_settings["threshold"] = confidence_threshold

    # Create service
    service = WakeWordService(
        detector=detector,
        redis_client=redis_client
    )

    await service.start()

    # Start audio stream processing in background
    if redis_client:
        asyncio.create_task(service.process_audio_stream())

    # Start heartbeat task (Phase 17.2)
    asyncio.create_task(service.heartbeat_task())

    print("Wake Word Service is ready")

    yield

    # Shutdown
    if service:
        await service.stop()
    if redis_client:
        await redis_client.aclose()
    print("Wake Word Service shutdown complete")


# Create FastAPI app
app = FastAPI(
    title="Wake Word Service",
    description="OpenWakeWord 기반 Wake Word 감지 서비스",
    version="1.0.0",
    lifespan=lifespan
)


# ===== Settings Storage =====
_current_settings = {
    "wake_word": "hey_jarvis",
    "threshold": 0.3
}


from pydantic import BaseModel, Field
from typing import Optional


class WakeWordSettings(BaseModel):
    """Wake Word 설정 모델"""
    wake_word: Optional[str] = Field(default=None, description="Wake Word 이름")
    threshold: Optional[float] = Field(default=None, ge=0.1, le=0.9, description="감지 임계값")


class WakeWordSettingsResponse(BaseModel):
    """Wake Word 설정 응답"""
    wake_word: str
    threshold: float
    status: str = "applied"


@app.put("/settings", response_model=WakeWordSettingsResponse)
async def update_settings(settings: WakeWordSettings):
    """
    Wake Word 설정 업데이트

    Phase 40: Wake Word 변경 시 모델 교체
    Phase 47: Threshold 변경 시 Pipeline Log 발행

    Args:
        settings: 업데이트할 설정

    Returns:
        적용된 설정 상태
    """
    global _current_settings, service

    status = "applied"
    _logger = get_logger("wake_word")

    # Wake Word 변경 시 모델 교체 (Phase 40)
    if settings.wake_word is not None:
        if service and service.detector:
            success = service.detector.set_wake_word(settings.wake_word)
            if success:
                _current_settings["wake_word"] = settings.wake_word
            else:
                status = "wake_word_change_failed"
        else:
            _current_settings["wake_word"] = settings.wake_word

    # Threshold 변경 (Phase 47: Pipeline Log 발행)
    if settings.threshold is not None:
        old_threshold = _current_settings["threshold"]
        _current_settings["threshold"] = settings.threshold

        if service and service.detector:
            service.detector.set_confidence_threshold(settings.threshold)

            # Phase 47: settings_updated Pipeline Log 이벤트 발행
            await _logger.info(
                "settings_updated",
                f"Threshold updated: {old_threshold:.2f} → {settings.threshold:.2f}",
                metadata={
                    "old_threshold": old_threshold,
                    "new_threshold": settings.threshold,
                    "setting": "wake_word_threshold"
                }
            )

    return WakeWordSettingsResponse(
        wake_word=_current_settings["wake_word"],
        threshold=_current_settings["threshold"],
        status=status
    )


@app.get("/wake-words")
async def get_available_wake_words():
    """
    사용 가능한 Wake Word 목록 반환

    Phase 40: OpenWakeWord 지원 모델 목록

    Returns:
        사용 가능한 Wake Word 목록
    """
    return {
        "available": list(WAKE_WORD_MODELS.keys()),
        "models": WAKE_WORD_MODELS,
        "current": _current_settings.get("wake_word", "hey_jarvis")
    }


@app.get("/detector/status")
async def get_detector_status():
    """
    Detector 상세 상태 반환

    Phase 40: 디버깅 및 모니터링용

    Returns:
        Detector 상태 정보
    """
    if service and service.detector:
        return service.detector.get_status()

    return {
        "error": "Detector not initialized",
        "wake_word": _current_settings.get("wake_word", "hey_jarvis"),
        "use_mock": True
    }


@app.get("/health")
async def health_check():
    """Health check endpoint - 단순 생존 확인만"""
    return {
        "status": "healthy",
        "service": "wake-word"
    }


@app.get("/info")
async def get_service_info():
    """
    서비스 상세 정보 조회 (Phase 28.1, Phase 40)

    Dashboard에서 사용할 서비스 정보를 반환합니다.
    /health와 분리하여 상세 정보만 제공합니다.
    """
    environment = os.environ.get("WAKE_WORD_ENVIRONMENT", "development")
    wake_word = _current_settings.get("wake_word", "hey_jarvis")
    model_name = WAKE_WORD_MODELS.get(wake_word, "unknown")

    # Detector 상태 확인
    use_mock = True
    if service and service.detector:
        use_mock = service.detector._use_mock

    return {
        "service": "wake_word",
        "model": {
            "name": "openwakeword",
            "wake_word": wake_word,
            "model_file": model_name,
            "use_mock": use_mock
        },
        "settings": {
            "threshold": _current_settings.get("threshold", 0.5),
            "wake_word": wake_word
        },
        "available_wake_words": list(WAKE_WORD_MODELS.keys()),
        "stats": {
            "redis_connected": redis_client is not None,
            "running": service._running if service else False
        },
        "status": "ready" if service and service._running else "initializing"
    }


@app.get("/status")
async def get_status():
    """Get service status"""
    return {
        "service": "wake-word",
        "running": service._running if service else False,
        "redis_connected": redis_client is not None,
        "environment": os.environ.get("WAKE_WORD_ENVIRONMENT", "development")
    }


async def main():
    """메인 진입점"""
    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=11005,
        log_level="info"
    )
    server = uvicorn.Server(config)
    await server.serve()


if __name__ == "__main__":
    asyncio.run(main())
