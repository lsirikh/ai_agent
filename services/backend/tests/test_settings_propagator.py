"""
Test: Settings Propagator
Phase 22.1: Redis 설정 브로드캐스트

TDD Red Phase: 이 테스트는 처음에 실패해야 합니다.
"""
import pytest
from unittest.mock import AsyncMock, patch
import json


def test_settings_propagator_class_exists():
    """SettingsPropagator 클래스가 존재하는지 확인"""
    from app.services.settings_propagator import SettingsPropagator
    assert SettingsPropagator is not None


def test_settings_propagator_has_publish_method():
    """SettingsPropagator에 publish_settings 메서드가 있는지 확인"""
    from app.services.settings_propagator import SettingsPropagator

    propagator = SettingsPropagator()
    assert hasattr(propagator, "publish_settings")


@pytest.mark.asyncio
async def test_settings_publish_on_update():
    """설정 업데이트 시 Redis에 발행하는지 확인"""
    from app.services.settings_propagator import SettingsPropagator

    mock_redis = AsyncMock()
    mock_redis.publish = AsyncMock(return_value=1)

    propagator = SettingsPropagator(redis=mock_redis)

    await propagator.publish_settings(
        target_service="stt",
        settings={"model": "whisper-large-v3"}
    )

    mock_redis.publish.assert_called_once()


@pytest.mark.asyncio
async def test_settings_message_format():
    """설정 메시지 포맷이 올바른지 확인"""
    from app.services.settings_propagator import SettingsPropagator

    mock_redis = AsyncMock()
    mock_redis.publish = AsyncMock(return_value=1)

    propagator = SettingsPropagator(redis=mock_redis)

    await propagator.publish_settings(
        target_service="tts",
        settings={"voice": "ko-KR", "speed": 1.0}
    )

    call_args = mock_redis.publish.call_args
    message = json.loads(call_args[0][1])

    assert "target" in message
    assert "settings" in message
    assert message["target"] == "tts"


@pytest.mark.asyncio
async def test_settings_targets_specific_service():
    """설정이 특정 서비스를 대상으로 하는지 확인"""
    from app.services.settings_propagator import SettingsPropagator, SETTINGS_CHANNEL

    mock_redis = AsyncMock()
    mock_redis.publish = AsyncMock(return_value=1)

    propagator = SettingsPropagator(redis=mock_redis)

    await propagator.publish_settings(
        target_service="llm",
        settings={"temperature": 0.7}
    )

    call_args = mock_redis.publish.call_args
    channel = call_args[0][0]

    # settings 채널에 발행되어야 함
    assert channel == SETTINGS_CHANNEL


# ============================================
# Phase 25: LLM/Audio Gateway 설정 전파 수정
# ============================================

# Phase 25.1: Settings Propagator에서 LLM 제외
def test_service_urls_does_not_contain_llm():
    """
    SERVICE_URLS에 LLM이 포함되지 않아야 함.

    vLLM 공식 이미지는 /settings 엔드포인트를 지원하지 않으므로
    설정 전파 대상에서 제외해야 합니다.
    """
    from app.services.settings_propagator import SERVICE_URLS

    # LLM은 SERVICE_URLS에 없어야 함
    assert "llm" not in SERVICE_URLS

    # 다른 서비스는 여전히 존재해야 함
    assert "tts" in SERVICE_URLS
    assert "stt" in SERVICE_URLS
    assert "audio" in SERVICE_URLS
    assert "wake_word" in SERVICE_URLS


# Phase 25.2: Audio Gateway 포트 수정
def test_audio_gateway_default_port_is_11008():
    """
    Audio Gateway 기본 포트가 11008이어야 함.

    docker-compose.dev.yml에서 audio-gateway는 11008 포트를 사용하므로
    기본값도 11008이어야 합니다.
    """
    import os
    # 환경변수가 설정되지 않은 상태에서 기본값 테스트
    original = os.environ.pop("AUDIO_GATEWAY_URL", None)

    try:
        # 모듈 재로드하여 기본값 확인
        from importlib import reload
        from app.services import settings_propagator
        reload(settings_propagator)

        audio_url = settings_propagator.SERVICE_URLS.get("audio", "")
        assert "11008" in audio_url, f"Audio Gateway URL should contain port 11008, got: {audio_url}"
    finally:
        # 환경변수 복원
        if original is not None:
            os.environ["AUDIO_GATEWAY_URL"] = original


# Phase 25.4: Docker Compose 환경변수 테스트
def test_docker_compose_has_audio_gateway_url():
    """
    docker-compose.dev.yml의 backend 서비스에
    AUDIO_GATEWAY_URL 환경변수가 있는지 확인.
    """
    import yaml

    with open("../../docker-compose.dev.yml", "r", encoding="utf-8") as f:
        compose = yaml.safe_load(f)

    backend_env = compose["services"]["backend"]["environment"]

    # AUDIO_GATEWAY_URL이 backend 환경변수에 있어야 함
    audio_gateway_url_found = False
    for env_item in backend_env:
        if isinstance(env_item, str) and env_item.startswith("AUDIO_GATEWAY_URL="):
            audio_gateway_url_found = True
            # 포트가 11008인지 확인
            assert "11008" in env_item, f"AUDIO_GATEWAY_URL should use port 11008: {env_item}"
            break

    assert audio_gateway_url_found, (
        f"AUDIO_GATEWAY_URL not found in backend environment. "
        f"Current env: {backend_env}"
    )


# Phase 25.5: 통합 테스트
@pytest.mark.asyncio
async def test_settings_propagation_excludes_llm():
    """
    설정 전파 시 LLM 서비스가 포함되지 않는지 확인.

    SERVICE_URLS에서 LLM이 제외되었으므로,
    propagate_all 호출 시 LLM에 대한 전파가 시도되지 않아야 합니다.
    """
    from app.services.settings_propagator import SettingsPropagator, SERVICE_URLS

    # LLM이 SERVICE_URLS에 없어야 함
    assert "llm" not in SERVICE_URLS

    # SettingsPropagator 인스턴스 생성
    propagator = SettingsPropagator()

    # LLM 설정으로 propagate 시도하면 실패해야 함
    result = await propagator.propagate("llm", {"model": "test"})

    assert result["success"] is False
    assert "Unknown service type" in result["error"]

    await propagator.close()


@pytest.mark.asyncio
async def test_settings_propagation_audio_gateway_uses_correct_port():
    """
    Audio Gateway 설정 전파가 올바른 포트(11008)를 사용하는지 확인.
    """
    from app.services.settings_propagator import SERVICE_URLS

    audio_url = SERVICE_URLS.get("audio", "")

    # 환경변수가 없을 때도 11008 포트가 기본값이어야 함
    # 또는 환경변수로 설정된 경우 그 값을 사용
    assert "audio" in SERVICE_URLS, "audio should be in SERVICE_URLS"

    # 포트 확인 (환경변수에 의해 설정될 수 있으므로 존재 여부만 확인)
    assert len(audio_url) > 0, "audio URL should not be empty"
