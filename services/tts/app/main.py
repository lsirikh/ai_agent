"""
TTS Service FastAPI Application

Phase 1.3: Kokoro TTS API 서버
Phase 8.2: Redis Subscriber 통합
Phase 27.7: Pipeline Logging 추가
"""
import asyncio
import os
import time
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from .synthesizer import KokoroTTS
from .redis_subscriber import TTSRedisSubscriber
from .pipeline_logger import get_logger, HEARTBEAT_INTERVAL

# 환경 설정
ENVIRONMENT = os.getenv("TTS_ENVIRONMENT", "development")
REDIS_ENABLED = os.getenv("TTS_REDIS_ENABLED", "true").lower() == "true"

# Global Redis Subscriber
_redis_subscriber: Optional[TTSRedisSubscriber] = None
_subscriber_task: Optional[asyncio.Task] = None
_heartbeat_task: Optional[asyncio.Task] = None
_start_time: float = 0


async def heartbeat_loop():
    """Phase 27.7: 주기적으로 heartbeat 로그 전송"""
    logger = get_logger("tts")
    while True:
        try:
            uptime = int(time.time() - _start_time)
            await logger.info(
                "heartbeat",
                f"TTS Service alive (uptime: {uptime}s)",
                metadata={"uptime_seconds": uptime, "engine": _current_settings.get("engine", "unknown")}
            )
        except Exception as e:
            print(f"[TTS] Heartbeat failed: {e}")
        await asyncio.sleep(HEARTBEAT_INTERVAL)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan handler - Redis Subscriber 시작/종료"""
    global _redis_subscriber, _subscriber_task, _heartbeat_task, _start_time

    _start_time = time.time()

    # Synthesizer 초기화
    synthesizer = get_synthesizer()

    # Phase 27.7: 서비스 시작 로그
    logger = get_logger("tts")
    await logger.info("tts_service_started", "TTS Service started")

    # Redis Subscriber 시작 (환경 변수로 제어 가능)
    if REDIS_ENABLED:
        try:
            _redis_subscriber = TTSRedisSubscriber(synthesizer=synthesizer)
            await _redis_subscriber.connect()
            await _redis_subscriber.subscribe()

            # 백그라운드 태스크로 실행
            _subscriber_task = asyncio.create_task(_redis_subscriber.run())
            print("[TTS] Redis Subscriber started")
        except Exception as e:
            print(f"[TTS] Failed to start Redis Subscriber: {e}")

    # Phase 27.7: Heartbeat 태스크 시작
    _heartbeat_task = asyncio.create_task(heartbeat_loop())

    yield

    # Shutdown
    # Heartbeat 종료
    if _heartbeat_task:
        _heartbeat_task.cancel()
        try:
            await _heartbeat_task
        except asyncio.CancelledError:
            pass

    if _redis_subscriber:
        await _redis_subscriber.stop()
        if _subscriber_task:
            _subscriber_task.cancel()
            try:
                await _subscriber_task
            except asyncio.CancelledError:
                pass
        print("[TTS] Redis Subscriber stopped")

    # 로거 세션 종료
    await logger.close()


# FastAPI 앱 생성
app = FastAPI(
    title="EdgeVoice TTS Service",
    description="Kokoro 기반 음성 합성 서비스",
    version="1.0.0",
    lifespan=lifespan
)

# Synthesizer 인스턴스 (lazy loading)
_synthesizer: Optional[KokoroTTS] = None


def get_synthesizer() -> KokoroTTS:
    """Synthesizer 인스턴스 획득 (싱글톤)"""
    global _synthesizer
    if _synthesizer is None:
        _synthesizer = KokoroTTS(environment=ENVIRONMENT)
    return _synthesizer


class SynthesizeRequest(BaseModel):
    """합성 요청 모델"""
    text: str
    voice: Optional[str] = None
    speed: Optional[float] = 1.0


class HealthResponse(BaseModel):
    """헬스 체크 응답"""
    status: str
    service: str
    environment: str


class VoicesResponse(BaseModel):
    """음성 목록 응답"""
    voices: list[str]


class SettingsRequest(BaseModel):
    """설정 요청 모델"""
    engine: Optional[str] = None
    voice: Optional[str] = None
    speed: Optional[float] = None


class SettingsResponse(BaseModel):
    """설정 응답 모델"""
    status: str
    engine: Optional[str] = None
    voice: Optional[str] = None
    speed: Optional[float] = None


# 현재 TTS 설정 (in-memory)
_current_settings = {
    "engine": "melo",
    "voice": "af_heart",
    "speed": 1.0
}


@app.get("/")
async def root():
    """서비스 정보"""
    return {
        "name": "EdgeVoice TTS Synthesizer",
        "version": "1.0.0",
        "environment": ENVIRONMENT
    }


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """헬스 체크 엔드포인트 - 단순 생존 확인만"""
    return HealthResponse(
        status="healthy",
        service="tts",
        environment=ENVIRONMENT
    )


@app.get("/info")
async def get_service_info():
    """
    서비스 상세 정보 조회 (Phase 28.1)

    Dashboard에서 사용할 서비스 정보를 반환합니다.
    /health와 분리하여 상세 정보만 제공합니다.
    """
    uptime_seconds = int(time.time() - _start_time) if _start_time > 0 else 0
    device = os.getenv("DEVICE", "cpu")

    return {
        "service": "tts",
        "engine": {
            "name": _current_settings.get("engine", "kokoro"),
            "device": device
        },
        "settings": {
            "voice": _current_settings.get("voice", "af_heart"),
            "speed": _current_settings.get("speed", 1.0)
        },
        "stats": {
            "uptime_seconds": uptime_seconds,
            "redis_enabled": REDIS_ENABLED
        },
        "status": "ready"
    }


@app.post("/synthesize")
async def synthesize_text(request: SynthesizeRequest):
    """
    텍스트를 음성으로 합성

    Args:
        request: 합성 요청 (text, voice, speed)

    Returns:
        WAV 오디오 파일
    """
    if not request.text or not request.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty")

    try:
        synthesizer = get_synthesizer()

        # 음성 설정
        if request.voice:
            synthesizer.set_voice(request.voice)

        # 속도 설정
        if request.speed:
            synthesizer.speed = request.speed

        # 합성 수행
        audio = synthesizer.synthesize(request.text)

        # WAV 변환
        wav_bytes = synthesizer.to_wav_bytes(audio)

        return Response(
            content=wav_bytes,
            media_type="audio/wav",
            headers={
                "Content-Disposition": "attachment; filename=speech.wav"
            }
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Synthesis failed: {str(e)}")


@app.get("/voices", response_model=VoicesResponse)
async def get_voices():
    """사용 가능한 음성 목록 조회"""
    synthesizer = get_synthesizer()
    voices = synthesizer.get_available_voices()
    return VoicesResponse(voices=voices)


@app.put("/settings", response_model=SettingsResponse)
async def update_settings(request: SettingsRequest):
    """
    TTS 설정 업데이트 (Phase 12.3)

    설정 변경을 수신하고 현재 서비스에 적용.

    Args:
        request: 설정 요청 (engine, voice, speed)

    Returns:
        적용된 설정
    """
    global _current_settings

    try:
        synthesizer = get_synthesizer()

        # 엔진 변경 (향후 엔진 매니저 통합)
        if request.engine is not None:
            _current_settings["engine"] = request.engine
            # TODO: 엔진 매니저를 통한 실제 엔진 전환

        # 음성 변경
        if request.voice is not None:
            _current_settings["voice"] = request.voice
            synthesizer.set_voice(request.voice)

        # 속도 변경
        if request.speed is not None:
            _current_settings["speed"] = request.speed
            synthesizer.speed = request.speed

        return SettingsResponse(
            status="applied",
            engine=_current_settings["engine"],
            voice=_current_settings["voice"],
            speed=_current_settings["speed"]
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Settings update failed: {str(e)}")


@app.get("/settings", response_model=SettingsResponse)
async def get_settings():
    """현재 TTS 설정 조회"""
    return SettingsResponse(
        status="current",
        engine=_current_settings["engine"],
        voice=_current_settings["voice"],
        speed=_current_settings["speed"]
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=11004)
