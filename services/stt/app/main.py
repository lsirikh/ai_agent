"""
STT Service FastAPI Application

Phase 1.1: 음성 인식 API 서버
Phase 10.2: 동적 모델 관리 통합
Phase 17.1: Pipeline Logging 추가
Phase 17.2: Service Heartbeat Logging (10초 간격)
"""
import asyncio
import io
import os
import subprocess
import time
import wave
from contextlib import asynccontextmanager
from typing import Optional, List

import numpy as np
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from .transcriber import StreamingTranscriber
from .model_manager import STTModelManager
from .pipeline_logger import get_logger, HEARTBEAT_INTERVAL

# 환경 설정
ENVIRONMENT = os.getenv("STT_ENVIRONMENT", "development")
MODEL_SIZE = os.getenv("MODEL_SIZE", "small")
DEVICE = os.getenv("DEVICE", "cpu")
COMPUTE_TYPE = os.getenv("COMPUTE_TYPE", "int8")

# Pipeline logger
_logger = get_logger("stt")

# 서비스 시작 시간 및 하트비트 플래그
_service_start_time: float = 0.0
_heartbeat_running: bool = False
_transcription_count: int = 0


async def heartbeat_task() -> None:
    """
    하트비트 로그 태스크 (10초 간격)

    서비스 생존 확인을 위해 주기적으로 로그를 전송합니다.
    """
    global _heartbeat_running
    _heartbeat_running = True

    while _heartbeat_running:
        uptime_seconds = int(time.time() - _service_start_time)
        await _logger.info(
            "heartbeat",
            f"STT Service alive (uptime: {uptime_seconds}s)",
            metadata={
                "service": "stt",
                "uptime_seconds": uptime_seconds,
                "model": MODEL_SIZE,
                "device": DEVICE,
                "transcription_count": _transcription_count
            }
        )
        await asyncio.sleep(HEARTBEAT_INTERVAL)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan handler for startup/shutdown logging"""
    global _service_start_time, _heartbeat_running

    # Startup
    _service_start_time = time.time()

    await _logger.info(
        "stt_service_started",
        f"STT Service started with model: {MODEL_SIZE}",
        metadata={
            "model": MODEL_SIZE,
            "device": DEVICE,
            "compute_type": COMPUTE_TYPE,
            "environment": ENVIRONMENT
        }
    )

    # Start heartbeat task (Phase 17.2)
    asyncio.create_task(heartbeat_task())

    # 첫 음성 요청이 모델 로드를 기다리지 않도록 시작할 때 백그라운드에서 미리 불러온다
    asyncio.create_task(asyncio.to_thread(get_transcriber))

    yield

    # Shutdown
    _heartbeat_running = False

    await _logger.info(
        "stt_service_stopped",
        "STT Service stopped"
    )
    await _logger.close()


# FastAPI 앱 생성
app = FastAPI(
    title="EdgeVoice STT Service",
    description="Faster-Whisper 기반 음성 인식 서비스",
    version="1.0.0",
    lifespan=lifespan
)

# Transcriber 인스턴스 (lazy loading)
_transcriber: Optional[StreamingTranscriber] = None

# Model Manager 인스턴스 (싱글톤)
_model_manager: Optional[STTModelManager] = None


def get_model_manager() -> STTModelManager:
    """ModelManager 인스턴스 획득 (싱글톤)"""
    global _model_manager
    if _model_manager is None:
        _model_manager = STTModelManager(
            default_model=MODEL_SIZE,
            device=DEVICE,
            compute_type=COMPUTE_TYPE
        )
    return _model_manager


def get_transcriber() -> StreamingTranscriber:
    """Transcriber 인스턴스 획득 (싱글톤)"""
    global _transcriber
    if _transcriber is None:
        _transcriber = StreamingTranscriber(environment=ENVIRONMENT)
    return _transcriber


class TranscribeResponse(BaseModel):
    """전사 응답 모델"""
    text: str
    confidence: float
    language: str
    segments: list = []


class HealthResponse(BaseModel):
    """헬스 체크 응답"""
    status: str
    service: str
    environment: str


class GPUInfoResponse(BaseModel):
    """GPU 정보 응답"""
    available: bool
    name: Optional[str] = None
    memory_total: Optional[int] = None
    memory_used: Optional[int] = None
    memory_free: Optional[int] = None
    utilization: Optional[float] = None


class ModelInfo(BaseModel):
    """모델 정보"""
    id: str
    display_name: str
    size_mb: int
    vram_gb: int
    relative_speed: float
    korean_quality: str
    recommended_for: str
    is_current: bool


class ModelsResponse(BaseModel):
    """모델 목록 응답"""
    models: List[ModelInfo]
    current_model: str


class ModelSwitchRequest(BaseModel):
    """모델 전환 요청"""
    model: str


class ModelSwitchResponse(BaseModel):
    """모델 전환 응답"""
    success: bool
    previous_model: str
    current_model: str
    message: str


class SettingsRequest(BaseModel):
    """설정 요청 모델 (Phase 12.3)"""
    model: Optional[str] = None
    language: Optional[str] = None


class SettingsResponse(BaseModel):
    """설정 응답 모델 (Phase 12.3)"""
    status: str
    model: Optional[str] = None
    language: Optional[str] = None


# 현재 STT 설정 (in-memory)
_current_settings = {
    "model": MODEL_SIZE,
    "language": "ko"
}


@app.get("/")
async def root():
    """서비스 정보"""
    return {
        "name": "EdgeVoice STT Transcriber",
        "version": "1.0.0",
        "environment": ENVIRONMENT
    }


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """헬스 체크 엔드포인트 - 단순 생존 확인만"""
    return HealthResponse(
        status="healthy",
        service="stt",
        environment=ENVIRONMENT
    )


@app.get("/info")
async def get_service_info():
    """
    서비스 상세 정보 조회 (Phase 28.1)

    Dashboard에서 사용할 서비스 정보를 반환합니다.
    /health와 분리하여 상세 정보만 제공합니다.
    """
    manager = get_model_manager()
    uptime_seconds = int(time.time() - _service_start_time) if _service_start_time > 0 else 0

    return {
        "service": "stt",
        "model": {
            "name": "whisper",
            "size": manager.get_current_model_name(),
            "compute_type": COMPUTE_TYPE,
            "device": DEVICE
        },
        "settings": {
            "language": _current_settings.get("language", "ko"),
            "model": _current_settings.get("model", MODEL_SIZE)
        },
        "stats": {
            "uptime_seconds": uptime_seconds,
            "transcription_count": _transcription_count
        },
        "status": "ready"
    }


@app.get("/models", response_model=ModelsResponse)
async def get_models():
    """
    사용 가능한 STT 모델 목록 조회

    Returns:
        ModelsResponse: 모델 목록과 현재 모델 정보
    """
    manager = get_model_manager()
    models = manager.get_available_models()

    return ModelsResponse(
        models=[ModelInfo(**m) for m in models],
        current_model=manager.get_current_model_name()
    )


@app.post("/models/switch", response_model=ModelSwitchResponse)
async def switch_model(request: ModelSwitchRequest):
    """
    STT 모델 전환

    Args:
        request: 전환할 모델 정보

    Returns:
        ModelSwitchResponse: 전환 결과
    """
    manager = get_model_manager()
    previous_model = manager.get_current_model_name()

    success = manager.switch_model(request.model)

    if not success:
        await _logger.warning(
            "model_switch_failed",
            f"Model switch failed: invalid model '{request.model}'",
            metadata={"requested_model": request.model, "current_model": previous_model}
        )
        raise HTTPException(
            status_code=400,
            detail=f"Invalid model: {request.model}. Available models: {list(manager.MODEL_INFO.keys())}"
        )

    # Log model switch
    await _logger.info(
        "model_switched",
        f"STT model switched: {previous_model} -> {request.model}",
        metadata={
            "previous_model": previous_model,
            "new_model": request.model
        }
    )

    return ModelSwitchResponse(
        success=True,
        previous_model=previous_model,
        current_model=manager.get_current_model_name(),
        message=f"Model switched from {previous_model} to {request.model}"
    )


@app.get("/gpu", response_model=GPUInfoResponse)
async def get_gpu_info():
    """
    GPU 정보 조회 엔드포인트

    nvidia-smi를 사용하여 GPU 상태를 조회합니다.
    """
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total,memory.used,memory.free,utilization.gpu",
             "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=5
        )

        if result.returncode == 0 and result.stdout.strip():
            parts = [p.strip() for p in result.stdout.strip().split(",")]
            if len(parts) >= 5:
                return GPUInfoResponse(
                    available=True,
                    name=parts[0],
                    memory_total=int(float(parts[1])) * 1024 * 1024,  # MB to bytes
                    memory_used=int(float(parts[2])) * 1024 * 1024,
                    memory_free=int(float(parts[3])) * 1024 * 1024,
                    utilization=float(parts[4])
                )
    except Exception:
        pass

    return GPUInfoResponse(available=False)


@app.post("/transcribe", response_model=TranscribeResponse)
async def transcribe_audio(
    audio: UploadFile = File(...),
    language: Optional[str] = Form(None)
):
    """
    오디오 파일을 텍스트로 변환

    Args:
        audio: WAV 오디오 파일 (16kHz, mono, int16)
        language: 언어 코드 (예: "ko", "en"). None이면 자동 감지

    Returns:
        TranscribeResponse: 전사 결과
    """
    start_time = time.time()

    try:
        # 오디오 파일 읽기
        content = await audio.read()

        # WAV 파일 파싱
        audio_data = parse_wav_file(content)
        audio_length_seconds = len(audio_data) / 16000.0  # 16kHz 기준

        # Log transcription started
        await _logger.info(
            "transcription_started",
            f"Transcription started (audio: {audio_length_seconds:.1f}s)",
            metadata={
                "audio_length_seconds": audio_length_seconds,
                "language": language or "auto",
                "model": _current_settings["model"]
            }
        )

        # 전사 수행
        # 모델 로드·전사는 무겁고 동기라 스레드에서 돌려 /health 가 계속 응답하게 한다
        transcriber = await asyncio.to_thread(get_transcriber)
        result = await asyncio.to_thread(
            transcriber.transcribe, audio_data, language=language
        )

        duration_ms = int((time.time() - start_time) * 1000)

        # Log transcription completed
        text_preview = result["text"][:50] + "..." if len(result["text"]) > 50 else result["text"]
        await _logger.info(
            "transcription_completed",
            f"Transcription completed ({duration_ms}ms): {text_preview}",
            duration_ms=duration_ms,
            metadata={
                "text_length": len(result["text"]),
                "confidence": result["confidence"],
                "language": result["language"],
                "audio_length_seconds": audio_length_seconds
            }
        )

        return TranscribeResponse(
            text=result["text"],
            confidence=result["confidence"],
            language=result["language"],
            segments=result.get("segments", [])
        )

    except ValueError as e:
        await _logger.error(
            "transcription_error",
            f"Transcription failed: {str(e)}",
            metadata={"error": str(e), "error_type": "ValueError"}
        )
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        await _logger.error(
            "transcription_error",
            f"Transcription failed: {str(e)}",
            metadata={"error": str(e), "error_type": type(e).__name__}
        )
        raise HTTPException(status_code=500, detail=f"Transcription failed: {str(e)}")


@app.put("/settings", response_model=SettingsResponse)
async def update_settings(request: SettingsRequest):
    """
    STT 설정 업데이트 (Phase 12.3)

    설정 변경을 수신하고 현재 서비스에 적용.

    Args:
        request: 설정 요청 (model, language)

    Returns:
        적용된 설정
    """
    global _current_settings

    try:
        manager = get_model_manager()

        # 모델 변경
        if request.model is not None:
            if manager.switch_model(request.model):
                _current_settings["model"] = request.model
            else:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid model: {request.model}"
                )

        # 언어 변경
        if request.language is not None:
            _current_settings["language"] = request.language

        return SettingsResponse(
            status="applied",
            model=_current_settings["model"],
            language=_current_settings["language"]
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Settings update failed: {str(e)}")


@app.get("/settings", response_model=SettingsResponse)
async def get_settings():
    """현재 STT 설정 조회"""
    return SettingsResponse(
        status="current",
        model=_current_settings["model"],
        language=_current_settings["language"]
    )


def parse_wav_file(content: bytes) -> np.ndarray:
    """
    WAV 파일을 numpy 배열로 변환

    Args:
        content: WAV 파일 바이트

    Returns:
        np.ndarray: float32 오디오 데이터 (16kHz)
    """
    try:
        wav_buffer = io.BytesIO(content)
        with wave.open(wav_buffer, "rb") as wav_file:
            # 파라미터 확인
            n_channels = wav_file.getnchannels()
            sample_width = wav_file.getsampwidth()
            frame_rate = wav_file.getframerate()
            n_frames = wav_file.getnframes()

            # 오디오 데이터 읽기
            raw_data = wav_file.readframes(n_frames)

            # numpy 배열로 변환
            if sample_width == 2:  # int16
                audio = np.frombuffer(raw_data, dtype=np.int16)
            elif sample_width == 4:  # int32
                audio = np.frombuffer(raw_data, dtype=np.int32)
            else:
                raise ValueError(f"Unsupported sample width: {sample_width}")

            # 스테레오 → 모노 변환
            if n_channels == 2:
                audio = audio.reshape(-1, 2).mean(axis=1).astype(audio.dtype)

            # float32로 정규화
            audio_float = audio.astype(np.float32) / np.iinfo(audio.dtype).max

            # 리샘플링 (16kHz가 아닌 경우)
            if frame_rate != 16000:
                # 간단한 리샘플링 (scipy 없이)
                # 실제 프로덕션에서는 librosa나 scipy 사용 권장
                ratio = 16000 / frame_rate
                new_length = int(len(audio_float) * ratio)
                indices = np.linspace(0, len(audio_float) - 1, new_length)
                audio_float = np.interp(indices, np.arange(len(audio_float)), audio_float)

            return audio_float.astype(np.float32)

    except wave.Error as e:
        raise ValueError(f"Invalid WAV file: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=11003)
