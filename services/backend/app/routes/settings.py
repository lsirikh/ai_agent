"""
Backend API Settings Router

Phase 5.2: Settings 관리 API
Phase 10.3: Dynamic Model Selection API
Phase 12: Settings 영속성 및 서비스 전파
"""
import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel, Field

from ..models.llm_models import LLM_MODELS, get_all_models
from ..services.settings_repository import SettingsRepository, get_settings_repository
from ..services.settings_propagator import SettingsPropagator, get_settings_propagator
from ..services.settings_env_sync import sync_settings_to_env

router = APIRouter(prefix="/api/settings", tags=["settings"])


# ===== Pydantic Models =====

class LLMSettings(BaseModel):
    """LLM 설정"""
    model: str = Field(default="qwen2.5-7b-instruct-awq")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=1024, ge=1, le=8192)
    system_prompt: str = Field(default="당신은 EdgeVoice AI 어시스턴트입니다. 친절하고 도움이 되는 응답을 제공해주세요.")


class TTSSettings(BaseModel):
    """TTS 설정"""
    engine: str = Field(default="melo")
    voice: str = Field(default="af_heart")
    speed: float = Field(default=1.0, ge=0.5, le=2.0)


class STTSettings(BaseModel):
    """STT 설정"""
    model: str = Field(default="small")
    language: str = Field(default="ko")
    model_size: str = Field(default="large-v3")  # 호환성 유지


class AudioSettings(BaseModel):
    """오디오 설정"""
    sample_rate: int = Field(default=16000)
    vad_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    silence_duration: float = Field(default=0.5, ge=0.1, le=3.0)


class AllSettings(BaseModel):
    """전체 설정"""
    llm: LLMSettings = Field(default_factory=LLMSettings)
    tts: TTSSettings = Field(default_factory=TTSSettings)
    stt: STTSettings = Field(default_factory=STTSettings)
    audio: AudioSettings = Field(default_factory=AudioSettings)


class GeneralSettings(BaseModel):
    """General Settings (Phase 13.5, Phase 50)"""
    wake_word: str = Field(default="hey_jarvis")
    language: str = Field(default="ko")
    voice_speed: float = Field(default=1.0, ge=0.5, le=2.0)
    wake_word_threshold: float = Field(default=0.5, ge=0.1, le=0.9)
    # Phase 50: End Pause 설정 추가
    end_pause_seconds: float = Field(
        default=3.0, ge=1.0, le=10.0,
        description="음성 입력 완료 판단을 위한 무음 시간 (초)"
    )
    listening_timeout_seconds: float = Field(
        default=10.0, ge=5.0, le=30.0,
        description="Listening 모드 타임아웃 (초)"
    )


# ===== LLM Context Settings (Phase 15) =====

class LLMContextSettings(BaseModel):
    """LLM 컨텍스트 설정 (Sliding Window)"""
    context_enabled: bool = Field(default=True, description="컨텍스트 활성화 여부")
    context_window_size: int = Field(default=20, ge=5, le=50, description="Sliding Window 크기 (5-50)")


class LLMContextSettingsResponse(BaseModel):
    """LLM 컨텍스트 설정 응답"""
    context_enabled: bool
    context_window_size: int
    status: str = "applied"
    estimated_tokens_per_request: int = 0


class GeneralSettingsResponse(BaseModel):
    """General Settings 응답 (전파 결과 포함)"""
    wake_word: str
    language: str
    voice_speed: float
    wake_word_threshold: float
    # Phase 50: End Pause 설정 추가
    end_pause_seconds: float
    listening_timeout_seconds: float
    status: str = "applied"
    propagation_results: Optional[Dict[str, Any]] = None


# ===== In-memory Settings Storage =====

_current_settings = AllSettings()
_general_settings = GeneralSettings()
_llm_context_settings = LLMContextSettings()


# ===== Startup Settings Loading (Phase 16) =====

async def load_all_settings_from_db() -> None:
    """
    서버 시작 시 DB에서 모든 설정을 로드하여 메모리에 적용.

    Phase 16.1: 시작 시 설정 로드
    """
    global _current_settings, _general_settings, _llm_context_settings

    try:
        repo = get_settings_repository()

        # LLM 설정 로드
        llm_data = repo.load("llm")
        if llm_data:
            current_llm = _current_settings.llm.model_dump()
            current_llm.update(llm_data)
            _current_settings.llm = LLMSettings(**current_llm)

        # TTS 설정 로드
        tts_data = repo.load("tts")
        if tts_data:
            current_tts = _current_settings.tts.model_dump()
            current_tts.update(tts_data)
            _current_settings.tts = TTSSettings(**current_tts)

        # STT 설정 로드
        stt_data = repo.load("stt")
        if stt_data:
            current_stt = _current_settings.stt.model_dump()
            current_stt.update(stt_data)
            _current_settings.stt = STTSettings(**current_stt)

        # Audio 설정 로드
        audio_data = repo.load("audio")
        if audio_data:
            current_audio = _current_settings.audio.model_dump()
            current_audio.update(audio_data)
            _current_settings.audio = AudioSettings(**current_audio)

        # General 설정 로드
        general_data = repo.load("general")
        if general_data:
            current_general = _general_settings.model_dump()
            current_general.update(general_data)
            _general_settings = GeneralSettings(**current_general)

        # LLM Context 설정 로드
        llm_context_data = repo.load("llm_context")
        if llm_context_data:
            current_context = _llm_context_settings.model_dump()
            current_context.update(llm_context_data)
            _llm_context_settings = LLMContextSettings(**current_context)

        print("[Settings] Loaded all settings from DB")

    except Exception as e:
        print(f"[Settings] Failed to load settings from DB: {e}")
        # DB 로드 실패 시 기본값 유지


def get_current_settings_as_dict() -> Dict[str, Any]:
    """
    현재 메모리에 로드된 설정을 딕셔너리로 반환.

    Phase 16: Settings-Env 동기화용
    """
    return {
        "llm": _current_settings.llm.model_dump(),
        "tts": _current_settings.tts.model_dump(),
        "stt": _current_settings.stt.model_dump(),
    }


async def propagate_all_settings_to_services() -> Dict[str, Any]:
    """
    시작 시 모든 설정을 서비스에 전파.

    Phase 16.4: 시작 시 설정 전파
    """
    results = {}

    try:
        propagator = get_settings_propagator()

        # TTS 전파
        try:
            tts_result = await propagator.propagate("tts", _current_settings.tts.model_dump())
            results["tts"] = tts_result
        except Exception as e:
            results["tts"] = {"success": False, "error": str(e)}

        # STT 전파
        try:
            stt_result = await propagator.propagate("stt", _current_settings.stt.model_dump())
            results["stt"] = stt_result
        except Exception as e:
            results["stt"] = {"success": False, "error": str(e)}

        # LLM 전파
        try:
            llm_result = await propagator.propagate("llm", _current_settings.llm.model_dump())
            results["llm"] = llm_result
        except Exception as e:
            results["llm"] = {"success": False, "error": str(e)}

        # Audio 전파
        try:
            audio_result = await propagator.propagate("audio", _current_settings.audio.model_dump())
            results["audio"] = audio_result
        except Exception as e:
            results["audio"] = {"success": False, "error": str(e)}

        # Wake Word 전파
        try:
            wake_word_result = await propagator.propagate("wake_word", {
                "wake_word": _general_settings.wake_word,
                "threshold": _general_settings.wake_word_threshold
            })
            results["wake_word"] = wake_word_result
        except Exception as e:
            results["wake_word"] = {"success": False, "error": str(e)}

        print(f"[Settings] Propagated settings to services: {results}")

    except Exception as e:
        print(f"[Settings] Failed to propagate settings: {e}")
        results["error"] = str(e)

    return results


def get_settings() -> AllSettings:
    """현재 설정 반환 (DB에서 로드 후 메모리 캐시)"""
    global _current_settings

    # DB에서 각 설정 로드 시도
    try:
        repo = get_settings_repository()

        # LLM 설정 로드
        llm_data = repo.load("llm")
        if llm_data:
            _current_settings.llm = LLMSettings(**{**_current_settings.llm.model_dump(), **llm_data})

        # TTS 설정 로드
        tts_data = repo.load("tts")
        if tts_data:
            _current_settings.tts = TTSSettings(**{**_current_settings.tts.model_dump(), **tts_data})

        # STT 설정 로드
        stt_data = repo.load("stt")
        if stt_data:
            _current_settings.stt = STTSettings(**{**_current_settings.stt.model_dump(), **stt_data})

        # Audio 설정 로드
        audio_data = repo.load("audio")
        if audio_data:
            _current_settings.audio = AudioSettings(**{**_current_settings.audio.model_dump(), **audio_data})

    except Exception as e:
        print(f"[Settings] Failed to load from DB: {e}")
        # DB 로드 실패 시 메모리 값 사용

    return _current_settings


def update_settings(settings_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """설정 업데이트"""
    global _current_settings

    if settings_type == "llm":
        current = _current_settings.llm.model_dump()
        current.update(data)
        _current_settings.llm = LLMSettings(**current)
        return _current_settings.llm.model_dump()
    elif settings_type == "tts":
        current = _current_settings.tts.model_dump()
        current.update(data)
        _current_settings.tts = TTSSettings(**current)
        return _current_settings.tts.model_dump()
    elif settings_type == "stt":
        current = _current_settings.stt.model_dump()
        current.update(data)
        _current_settings.stt = STTSettings(**current)
        return _current_settings.stt.model_dump()
    elif settings_type == "audio":
        current = _current_settings.audio.model_dump()
        current.update(data)
        _current_settings.audio = AudioSettings(**current)
        return _current_settings.audio.model_dump()
    else:
        raise ValueError(f"Unknown settings type: {settings_type}")


# ===== Event Publishing & Persistence (Phase 12) =====

def publish_settings_event(settings_type: str, settings_data: Dict[str, Any]) -> None:
    """설정 변경 이벤트 발행 (Redis pub/sub)"""
    # TODO: Redis pub/sub 연동
    # redis_client.publish(f"settings:{settings_type}", json.dumps(settings_data))
    pass


def save_settings_to_db(settings_type: str, settings_data: Dict[str, Any]) -> bool:
    """설정을 DB에 저장 (Phase 12.1)"""
    try:
        repo = get_settings_repository()
        return repo.save(settings_type, settings_data)
    except Exception as e:
        print(f"[Settings] Failed to save to DB: {e}")
        return False


async def propagate_settings_to_service(settings_type: str, settings_data: Dict[str, Any]) -> Dict[str, Any]:
    """설정을 서비스에 전파 (Phase 12.2)"""
    try:
        propagator = get_settings_propagator()
        result = await propagator.propagate(settings_type, settings_data)
        return result
    except Exception as e:
        print(f"[Settings] Failed to propagate: {e}")
        return {"success": False, "error": str(e)}


# ===== API Endpoints =====

@router.get("", response_model=AllSettings)
async def get_all_settings():
    """
    전체 설정 조회

    Returns:
        모든 설정 정보
    """
    return get_settings()


# ===== General Settings Endpoints (Phase 13.5) =====

@router.get("/general", response_model=GeneralSettings)
async def get_general_settings():
    """
    General Settings 조회

    Returns:
        현재 General Settings (wake_word, language, voice_speed, wake_word_threshold)
    """
    global _general_settings

    # DB에서 로드 시도
    try:
        repo = get_settings_repository()
        saved = repo.load("general")
        if saved:
            _general_settings = GeneralSettings(**saved)
    except Exception:
        pass  # DB 로드 실패 시 메모리 값 사용

    return _general_settings


@router.put("/general", response_model=GeneralSettingsResponse)
async def update_general_settings(settings: GeneralSettings, background_tasks: BackgroundTasks):
    """
    General Settings 업데이트

    Args:
        settings: 업데이트할 General Settings

    Returns:
        업데이트된 설정 및 전파 결과
    """
    global _general_settings
    _general_settings = settings

    # DB 저장
    settings_dict = settings.model_dump()
    background_tasks.add_task(save_settings_to_db, "general", settings_dict)

    # 서비스 전파
    propagation_results = {}
    try:
        propagator = get_settings_propagator()

        # TTS에 voice_speed 전파
        tts_result = await propagator.propagate("tts", {"speed": settings.voice_speed})
        propagation_results["tts"] = tts_result

        # Wake Word에 threshold 전파
        wake_word_result = await propagator.propagate("wake_word", {
            "wake_word": settings.wake_word,
            "threshold": settings.wake_word_threshold
        })
        propagation_results["wake_word"] = wake_word_result

        # STT에 language 전파
        stt_result = await propagator.propagate("stt", {"language": settings.language})
        propagation_results["stt"] = stt_result

        # Phase 50: Orchestrator에 end_pause, listening_timeout 전파
        orchestrator_result = await propagator.propagate("orchestrator", {
            "end_pause_seconds": settings.end_pause_seconds,
            "listening_timeout_seconds": settings.listening_timeout_seconds
        })
        propagation_results["orchestrator"] = orchestrator_result

    except Exception as e:
        propagation_results["error"] = str(e)

    return GeneralSettingsResponse(
        wake_word=settings.wake_word,
        language=settings.language,
        voice_speed=settings.voice_speed,
        wake_word_threshold=settings.wake_word_threshold,
        end_pause_seconds=settings.end_pause_seconds,
        listening_timeout_seconds=settings.listening_timeout_seconds,
        status="applied",
        propagation_results=propagation_results
    )


# ===== Wake Word Settings Endpoint (Phase 13.1) =====

class WakeWordRequest(BaseModel):
    """Wake Word 등록 요청"""
    wake_word: str = Field(description="Wake Word 이름 (hey_jarvis, alexa, ok_google)")


class WakeWordResponse(BaseModel):
    """Wake Word 등록 응답"""
    wake_word: str
    status: str = "registered"
    propagated: bool = False


@router.put("/wake-word", response_model=WakeWordResponse)
async def register_wake_word(request: WakeWordRequest, background_tasks: BackgroundTasks):
    """
    Wake Word 등록 (개별 엔드포인트)

    Args:
        request: Wake Word 등록 요청

    Returns:
        등록된 Wake Word 및 전파 결과
    """
    global _general_settings
    _general_settings.wake_word = request.wake_word

    # DB 저장
    settings_dict = _general_settings.model_dump()
    background_tasks.add_task(save_settings_to_db, "general", settings_dict)

    # Wake Word 서비스에 전파
    propagated = False
    try:
        propagator = get_settings_propagator()
        result = await propagator.propagate("wake_word", {
            "wake_word": request.wake_word,
            "threshold": _general_settings.wake_word_threshold
        })
        propagated = result.get("success", False)
    except Exception:
        pass

    return WakeWordResponse(
        wake_word=request.wake_word,
        status="registered",
        propagated=propagated
    )


# ===== LLM Context Settings Endpoints (Phase 15) =====

@router.get("/llm/context", response_model=LLMContextSettings)
async def get_llm_context_settings():
    """
    LLM 컨텍스트 설정 조회

    Returns:
        현재 LLM 컨텍스트 설정 (context_enabled, context_window_size)
    """
    global _llm_context_settings

    # DB에서 로드 시도
    try:
        repo = get_settings_repository()
        saved = repo.load("llm_context")
        if saved:
            _llm_context_settings = LLMContextSettings(**saved)
    except Exception:
        pass  # DB 로드 실패 시 메모리 값 사용

    return _llm_context_settings


@router.put("/llm/context", response_model=LLMContextSettingsResponse)
async def update_llm_context_settings(
    settings: LLMContextSettings,
    background_tasks: BackgroundTasks
):
    """
    LLM 컨텍스트 설정 업데이트

    Args:
        settings: 업데이트할 LLM 컨텍스트 설정

    Returns:
        업데이트된 설정 및 예상 토큰 수
    """
    global _llm_context_settings
    _llm_context_settings = settings

    # DB 저장
    settings_dict = settings.model_dump()
    background_tasks.add_task(save_settings_to_db, "llm_context", settings_dict)

    # 토큰 추정 계산
    # 평균 메시지 50 토큰, 시스템 프롬프트 200 토큰, 새 메시지 30 토큰
    estimated_tokens = 200 + (settings.context_window_size * 50) + 30

    return LLMContextSettingsResponse(
        context_enabled=settings.context_enabled,
        context_window_size=settings.context_window_size,
        status="applied",
        estimated_tokens_per_request=estimated_tokens
    )


@router.patch("/llm", response_model=LLMSettings)
async def update_llm_settings(settings: Dict[str, Any], background_tasks: BackgroundTasks):
    """
    LLM 설정 업데이트

    Args:
        settings: 업데이트할 LLM 설정

    Returns:
        업데이트된 LLM 설정
    """
    updated = update_settings("llm", settings)

    # Phase 12: DB 저장 (백그라운드)
    background_tasks.add_task(save_settings_to_db, "llm", updated)

    # Phase 12: 서비스 전파
    await propagate_settings_to_service("llm", updated)

    publish_settings_event("llm", updated)
    return updated


@router.patch("/tts", response_model=TTSSettings)
async def update_tts_settings(settings: Dict[str, Any], background_tasks: BackgroundTasks):
    """
    TTS 설정 업데이트

    Args:
        settings: 업데이트할 TTS 설정

    Returns:
        업데이트된 TTS 설정
    """
    updated = update_settings("tts", settings)

    # Phase 12: DB 저장 (백그라운드)
    background_tasks.add_task(save_settings_to_db, "tts", updated)

    # Phase 12: 서비스 전파
    await propagate_settings_to_service("tts", updated)

    publish_settings_event("tts", updated)
    return updated


@router.patch("/stt", response_model=STTSettings)
async def update_stt_settings(settings: Dict[str, Any], background_tasks: BackgroundTasks):
    """
    STT 설정 업데이트

    Args:
        settings: 업데이트할 STT 설정

    Returns:
        업데이트된 STT 설정
    """
    updated = update_settings("stt", settings)

    # Phase 12: DB 저장 (백그라운드)
    background_tasks.add_task(save_settings_to_db, "stt", updated)

    # Phase 12: 서비스 전파
    await propagate_settings_to_service("stt", updated)

    publish_settings_event("stt", updated)
    return updated


@router.patch("/audio", response_model=AudioSettings)
async def update_audio_settings(settings: Dict[str, Any], background_tasks: BackgroundTasks):
    """
    오디오 설정 업데이트

    Args:
        settings: 업데이트할 오디오 설정

    Returns:
        업데이트된 오디오 설정
    """
    updated = update_settings("audio", settings)

    # Phase 12: DB 저장 (백그라운드)
    background_tasks.add_task(save_settings_to_db, "audio", updated)

    # Phase 12: 서비스 전파 (audio gateway)
    await propagate_settings_to_service("audio", updated)

    publish_settings_event("audio", updated)
    return updated


# ===== TTS Engine Options =====

TTS_ENGINES = [
    {
        "id": "melo",
        "display_name": "MeloTTS Korean",
        "sample_rate": 44100,
        "requires_gpu": True,
        "requires_internet": False,
        "korean_quality": "매우 좋음",
        "recommended_for": "한국어 최적화 (권장)"
    },
    {
        "id": "kokoro",
        "display_name": "Kokoro TTS",
        "sample_rate": 24000,
        "requires_gpu": True,
        "requires_internet": False,
        "korean_quality": "중간",
        "recommended_for": "영어 최적화"
    },
    {
        "id": "edge_tts",
        "display_name": "Microsoft Edge TTS",
        "sample_rate": 24000,
        "requires_gpu": False,
        "requires_internet": True,
        "korean_quality": "좋음",
        "recommended_for": "클라우드 기반 (인터넷 필요)"
    },
    {
        "id": "gtts",
        "display_name": "Google TTS",
        "sample_rate": 22050,
        "requires_gpu": False,
        "requires_internet": True,
        "korean_quality": "좋음",
        "recommended_for": "클라우드 기반 (인터넷 필요)"
    }
]


# ===== STT Model Options =====

STT_MODELS = [
    {
        "id": "tiny",
        "display_name": "Tiny",
        "vram_gb": 1,
        "relative_speed": 32,
        "korean_quality": "낮음",
        "recommended_for": "빠른 테스트용"
    },
    {
        "id": "base",
        "display_name": "Base",
        "vram_gb": 1,
        "relative_speed": 16,
        "korean_quality": "낮음",
        "recommended_for": "기본 용도"
    },
    {
        "id": "small",
        "display_name": "Small",
        "vram_gb": 2,
        "relative_speed": 6,
        "korean_quality": "중간",
        "recommended_for": "균형 잡힌 성능"
    },
    {
        "id": "medium",
        "display_name": "Medium",
        "vram_gb": 5,
        "relative_speed": 2,
        "korean_quality": "좋음",
        "recommended_for": "고품질 필요 시"
    },
    {
        "id": "large-v3",
        "display_name": "Large V3",
        "vram_gb": 10,
        "relative_speed": 1,
        "korean_quality": "매우 좋음",
        "recommended_for": "최고 품질"
    },
    {
        "id": "large-v3-turbo",
        "display_name": "Large V3 Turbo",
        "vram_gb": 6,
        "relative_speed": 5.4,
        "korean_quality": "좋음",
        "recommended_for": "속도/품질 균형"
    },
    {
        "id": "ghost613/faster-whisper-large-v3-turbo-korean",
        "display_name": "Large V3 Turbo Korean",
        "vram_gb": 6,
        "relative_speed": 5.4,
        "korean_quality": "매우 좋음",
        "recommended_for": "한국어 최적화 (권장)"
    }
]


class SettingsOptionsResponse(BaseModel):
    """설정 옵션 응답"""
    tts_engines: List[Dict[str, Any]]
    stt_models: List[Dict[str, Any]]
    llm_models: List[Dict[str, Any]]
    current: Dict[str, str]


@router.get("/options", response_model=SettingsOptionsResponse)
async def get_settings_options():
    """
    사용 가능한 모델/엔진 옵션 목록 조회

    Returns:
        TTS 엔진, STT 모델, LLM 모델 목록 및 현재 설정값
    """
    settings = get_settings()

    return SettingsOptionsResponse(
        tts_engines=TTS_ENGINES,
        stt_models=STT_MODELS,
        llm_models=get_all_models(),
        current={
            "tts_engine": settings.tts.engine,  # DB에서 로드된 값
            "tts_voice": settings.tts.voice,  # TTS Voice 추가
            "stt_model": settings.stt.model_size,  # model_size 필드 사용 (Phase 17)
            "llm_model": settings.llm.model
        }
    )


# ===== Settings Apply Models =====

class SettingsApplyRequest(BaseModel):
    """설정 적용 요청"""
    changes: Dict[str, Dict[str, Any]]


class SettingsApplyResponse(BaseModel):
    """설정 적용 응답"""
    applied: Dict[str, bool]
    restart_required: List[str]
    restart_commands: Optional[Dict[str, str]] = None
    message: str


# 재시작이 필요한 설정 변경 (hot-swap 불가)
RESTART_REQUIRED_CHANGES = {
    "llm": ["model"],  # LLM 모델 변경은 vLLM 재시작 필요
    "stt": [],  # STT는 hot-swap 가능
    "tts": [],  # TTS는 hot-swap 가능
    "audio": []  # 오디오 설정은 hot-swap 가능
}


@router.post("/apply", response_model=SettingsApplyResponse)
async def apply_settings(request: SettingsApplyRequest, background_tasks: BackgroundTasks):
    """
    설정 변경 적용

    Args:
        request: 적용할 설정 변경 사항

    Returns:
        SettingsApplyResponse: 적용 결과 및 재시작 필요 서비스 정보
    """
    applied = {}
    restart_required = []
    restart_commands = {}

    for settings_type, settings_data in request.changes.items():
        try:
            # 설정 업데이트 (메모리)
            updated = update_settings(settings_type, settings_data)
            applied[settings_type] = True

            # DB 저장 (백그라운드)
            background_tasks.add_task(save_settings_to_db, settings_type, updated)

            # .env 파일 동기화 (Phase 16)
            try:
                sync_settings_to_env({settings_type: settings_data})
            except Exception as env_err:
                print(f"[Settings] .env sync failed for {settings_type}: {env_err}")

            # 설정 이벤트 발행
            publish_settings_event(settings_type, updated)

            # 재시작이 필요한 변경인지 확인
            if settings_type in RESTART_REQUIRED_CHANGES:
                for key in settings_data.keys():
                    if key in RESTART_REQUIRED_CHANGES[settings_type]:
                        if settings_type not in restart_required:
                            restart_required.append(settings_type)
                            restart_commands[settings_type] = f"docker-compose restart {settings_type}"

        except Exception as e:
            applied[settings_type] = False

    # 응답 메시지 생성
    if len(restart_required) > 0:
        message = f"설정이 적용되었습니다. 다음 서비스의 재시작이 필요합니다: {', '.join(restart_required)}"
    else:
        message = "모든 설정이 적용되었습니다."

    return SettingsApplyResponse(
        applied=applied,
        restart_required=restart_required,
        restart_commands=restart_commands if restart_commands else None,
        message=message
    )


# ===== Service Restart Endpoints (Phase 13.6) =====

services_router = APIRouter(prefix="/api/services", tags=["services"])


class ServiceRestartResponse(BaseModel):
    """서비스 재시작 응답"""
    service: str
    status: str
    message: str


@services_router.post("/llm/restart", response_model=ServiceRestartResponse)
async def restart_llm_service():
    """
    LLM 서비스 재시작

    LLM 모델 변경 후 재시작이 필요할 때 사용

    Returns:
        재시작 상태
    """
    try:
        # Docker Compose를 통한 LLM 서비스 재시작
        # 실제 환경에서는 docker-compose restart ev-llm 실행
        import subprocess
        try:
            result = subprocess.run(
                ["docker-compose", "restart", "ev-llm"],
                capture_output=True,
                text=True,
                timeout=60
            )
            if result.returncode == 0:
                return ServiceRestartResponse(
                    service="llm",
                    status="restarting",
                    message="LLM service is restarting. Please wait for it to become healthy."
                )
            else:
                return ServiceRestartResponse(
                    service="llm",
                    status="pending",
                    message="Restart command queued. Docker may not be available."
                )
        except FileNotFoundError:
            # Docker Compose가 없는 개발 환경
            return ServiceRestartResponse(
                service="llm",
                status="pending",
                message="Restart queued. Run manually: docker-compose restart ev-llm"
            )
        except subprocess.TimeoutExpired:
            return ServiceRestartResponse(
                service="llm",
                status="timeout",
                message="Restart command timed out. Check Docker status."
            )
    except Exception as e:
        return ServiceRestartResponse(
            service="llm",
            status="error",
            message=f"Failed to restart: {str(e)}"
        )
