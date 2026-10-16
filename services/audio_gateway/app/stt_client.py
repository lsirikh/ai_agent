"""
STT Client

Phase 35.7.2: STT 서비스 호출 클라이언트
음성 데이터를 STT 서비스로 전송하고 텍스트 결과를 반환
"""
import json
import logging
import os
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

# STT 결과 Redis 채널
STT_RESULT_CHANNEL = "edgevoice:stt:result"


class STTClient:
    """
    STT 서비스 클라이언트

    WAV 형식의 오디오 데이터를 STT 서비스로 전송하고
    텍스트 결과를 반환합니다.

    Attributes:
        stt_url: STT 서비스 URL
        timeout: HTTP 요청 타임아웃 (초)
    """

    def __init__(
        self,
        stt_url: Optional[str] = None,
        timeout: float = 30.0,
        redis_client: Optional[Any] = None
    ):
        """
        STTClient 초기화

        Args:
            stt_url: STT 서비스 URL (기본값: 환경변수 또는 localhost:11003)
            timeout: HTTP 요청 타임아웃 (초)
            redis_client: Redis 클라이언트 (결과 발행용)
        """
        self.stt_url = stt_url or os.environ.get("STT_URL", "http://localhost:11003")
        self.timeout = timeout
        self.redis_client = redis_client

        # HTTP 클라이언트 (lazy init)
        self._http_client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """HTTP 클라이언트 가져오기 (lazy init)"""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=self.timeout)
        return self._http_client

    async def transcribe_async(self, wav_bytes: bytes) -> Optional[str]:
        """
        WAV 데이터를 STT 서비스로 전송하고 텍스트 결과 반환

        Args:
            wav_bytes: WAV 형식의 오디오 바이트

        Returns:
            인식된 텍스트, 실패 시 None
        """
        try:
            client = await self._get_client()

            # multipart/form-data로 오디오 파일 전송
            files = {
                "audio": ("audio.wav", wav_bytes, "audio/wav")
            }

            response = await client.post(
                f"{self.stt_url}/transcribe",
                files=files
            )

            if response.status_code == 200:
                result = response.json()
                text = result.get("text", "")
                logger.info(f"STT transcription result: {text[:50]}...")
                return text
            else:
                logger.error(f"STT service returned status {response.status_code}")
                return None

        except httpx.TimeoutException:
            logger.error("STT service timeout")
            return None

        except httpx.ConnectError:
            logger.error("STT service connection failed")
            return None

        except Exception as e:
            logger.error(f"STT transcription error: {e}")
            return None

    async def transcribe_and_publish(
        self,
        wav_bytes: bytes,
        session_id: str
    ) -> Optional[str]:
        """
        WAV 데이터를 STT로 변환하고 결과를 Redis로 발행

        Args:
            wav_bytes: WAV 형식의 오디오 바이트
            session_id: 세션 ID

        Returns:
            인식된 텍스트, 실패 시 None
        """
        text = await self.transcribe_async(wav_bytes)

        if text and self.redis_client:
            message = json.dumps({
                "event": "stt_result",
                "session_id": session_id,
                "text": text
            })

            await self.redis_client.publish(STT_RESULT_CHANNEL, message)
            logger.info(f"Published STT result to Redis: {text[:30]}...")

        return text

    async def close(self) -> None:
        """HTTP 클라이언트 종료"""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
