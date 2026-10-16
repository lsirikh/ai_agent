"""
Backend Services - Settings Propagator

Phase 12.2: 설정 서비스 전파
Phase 22.1: Redis Pub/Sub 기반 설정 브로드캐스트

각 서비스(TTS, STT, LLM)에 설정 변경을 HTTP 및 Redis로 전파
"""
import json
import os
from datetime import datetime
from typing import Any, Dict, Optional

import httpx


# 서비스 URL 설정
# Phase 25.1: vLLM은 /settings 엔드포인트를 지원하지 않으므로 제외
# Phase 25.2: Audio Gateway 포트 8008로 수정 (docker-compose.dev.yml과 일치)
# Phase 27: Docker 환경에서는 서비스명으로 접근 (audio-gateway)
# Phase 50: Orchestrator 서비스 추가
SERVICE_URLS = {
    "tts": os.getenv("TTS_SERVICE_URL", "http://tts:11002"),
    "stt": os.getenv("STT_SERVICE_URL", "http://stt:11001"),
    "audio": os.getenv("AUDIO_GATEWAY_URL", "http://audio-gateway:11008"),
    "wake_word": os.getenv("WAKE_WORD_SERVICE_URL", "http://wake-word:11005"),
    # compose 는 ORCHESTRATOR_URL 을 넣는다.
    # 컨테이너 안에서는 호스트 포트(11007)가 아닌 8007
    "orchestrator": os.getenv(
        "ORCHESTRATOR_SERVICE_URL",
        os.getenv("ORCHESTRATOR_URL", "http://orchestrator:8007"),
    ),
}

# LLM 서비스는 별도 처리 (vLLM은 런타임 설정 변경 불가)
# Phase 27: LLM 서비스 타입 명시적 처리
LLM_SERVICE_TYPES = {"llm", "vllm"}

# Redis 채널
SETTINGS_CHANNEL = "settings:updates"

# 재시작이 필요한 설정 변경
# Phase 25.1: LLM 제거 (vLLM은 설정 전파 대상이 아님)
RESTART_REQUIRED = {
    "stt": [],  # STT는 hot-swap 가능
    "tts": [],  # TTS는 hot-swap 가능
    "audio": [],  # 오디오 설정은 hot-swap 가능
}


class SettingsPropagator:
    """
    설정 변경을 각 서비스에 HTTP 및 Redis Pub/Sub으로 전파하는 클래스.
    """

    def __init__(self, redis=None):
        """SettingsPropagator 초기화.

        Args:
            redis: Redis 클라이언트 (선택, Redis Pub/Sub 사용 시 필요)
        """
        self._http_client = httpx.AsyncClient(timeout=10.0)
        self._redis = redis

    async def close(self):
        """HTTP 클라이언트 종료."""
        await self._http_client.aclose()

    async def publish_settings(
        self,
        target_service: str,
        settings: Dict[str, Any]
    ) -> bool:
        """
        Redis Pub/Sub을 통해 설정을 브로드캐스트.

        Args:
            target_service: 대상 서비스 이름 (stt, tts, llm 등)
            settings: 전파할 설정 딕셔너리

        Returns:
            발행 성공 여부
        """
        if self._redis is None:
            return False

        message = {
            "target": target_service,
            "settings": settings,
            "timestamp": datetime.utcnow().isoformat()
        }

        await self._redis.publish(SETTINGS_CHANNEL, json.dumps(message))
        return True

    async def propagate(
        self,
        service_type: str,
        settings_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        설정을 해당 서비스에 전파.

        Args:
            service_type: 서비스 타입 (tts, stt, llm, audio)
            settings_data: 전파할 설정 데이터

        Returns:
            전파 결과:
            - success: 성공 여부
            - service: 서비스 이름
            - restart_required: 재시작 필요 여부
            - error: 오류 메시지 (실패 시)
        """
        # Phase 27: LLM 서비스는 vLLM을 사용하며 런타임 설정 변경을 지원하지 않음
        # 컨테이너 재시작이 필요하므로 restart_required=True 반환
        if service_type in LLM_SERVICE_TYPES:
            return {
                "success": True,
                "service": service_type,
                "restart_required": True,
                "message": "LLM settings require container restart. vLLM does not support runtime configuration changes."
            }

        service_url = SERVICE_URLS.get(service_type)

        if not service_url:
            return {
                "success": False,
                "service": service_type,
                "error": f"Unknown service type: {service_type}"
            }

        # 재시작 필요 여부 확인
        restart_required = False
        if service_type in RESTART_REQUIRED:
            for key in settings_data.keys():
                if key in RESTART_REQUIRED[service_type]:
                    restart_required = True
                    break

        try:
            # 서비스의 /settings 엔드포인트에 PUT 요청
            response = await self._http_client.put(
                f"{service_url}/settings",
                json=settings_data
            )

            if response.status_code == 200:
                response_data = response.json()
                return {
                    "success": True,
                    "service": service_type,
                    "restart_required": restart_required or response_data.get("restart_required", False),
                    "response": response_data
                }
            else:
                return {
                    "success": False,
                    "service": service_type,
                    "error": f"HTTP {response.status_code}: {response.text}"
                }

        except httpx.ConnectError as e:
            return {
                "success": False,
                "service": service_type,
                "error": f"Connection failed: {str(e)}"
            }
        except httpx.TimeoutException as e:
            return {
                "success": False,
                "service": service_type,
                "error": f"Request timeout: {str(e)}"
            }
        except Exception as e:
            return {
                "success": False,
                "service": service_type,
                "error": f"Unexpected error: {str(e)}"
            }

    async def propagate_all(
        self,
        settings: Dict[str, Dict[str, Any]]
    ) -> Dict[str, Dict[str, Any]]:
        """
        모든 서비스에 설정 전파.

        Args:
            settings: 서비스별 설정 딕셔너리
                {
                    "tts": {...},
                    "stt": {...},
                    "llm": {...}
                }

        Returns:
            서비스별 전파 결과
        """
        results = {}
        for service_type, settings_data in settings.items():
            results[service_type] = await self.propagate(service_type, settings_data)
        return results


# 싱글톤 인스턴스
_settings_propagator: Optional[SettingsPropagator] = None


def get_settings_propagator() -> SettingsPropagator:
    """SettingsPropagator 싱글톤 인스턴스 반환."""
    global _settings_propagator
    if _settings_propagator is None:
        _settings_propagator = SettingsPropagator()
    return _settings_propagator


def reset_settings_propagator():
    """SettingsPropagator 리셋 (테스트용)."""
    global _settings_propagator
    _settings_propagator = None
