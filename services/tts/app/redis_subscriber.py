"""
TTS Redis Subscriber

Phase 8.1: TTS 서비스 Redis 구독자
edgevoice:tts:request 채널 구독 및 TTS 요청 처리

Phase 17: Pipeline Logging 추가
Phase 36.5: TTS 오디오 스트림 발행 (G5 해결)
"""
import asyncio
import json
import os
import time
from typing import Any, Callable, Optional

import redis.asyncio as aioredis
import numpy as np

from .pipeline_logger import get_logger

# Phase 36.5: TTS 오디오 스트림 채널
TTS_AUDIO_CHANNEL = "edgevoice:tts:audio"
TTS_STATE_CHANNEL = "edgevoice:tts:state"
TTS_CHUNK_SIZE = 1600  # 100ms @ 16kHz


class TTSRedisSubscriber:
    """TTS Redis 구독자 클래스"""

    def __init__(self, synthesizer: Any):
        """
        초기화

        Args:
            synthesizer: TTS 합성기 인스턴스
        """
        self.redis_host = os.getenv("REDIS_HOST", "localhost")
        self.redis_port = int(os.getenv("REDIS_PORT", "6379"))
        self.redis_client: Optional[aioredis.Redis] = None
        self.pubsub: Optional[aioredis.client.PubSub] = None
        self.synthesizer = synthesizer
        self._is_running = False
        self._logger = get_logger("tts")

    async def connect(self) -> None:
        """Redis 연결"""
        self.redis_client = aioredis.Redis(
            host=self.redis_host,
            port=self.redis_port,
            decode_responses=True
        )
        self.pubsub = self.redis_client.pubsub()

    async def subscribe(self) -> None:
        """edgevoice:tts:request 채널 구독"""
        if self.pubsub:
            await self.pubsub.subscribe("edgevoice:tts:request")

    def _parse_message(self, data: str) -> dict:
        """
        TTS 요청 메시지 파싱

        Args:
            data: JSON 문자열

        Returns:
            파싱된 메시지 딕셔너리
        """
        return json.loads(data)

    async def _publish_audio_stream(self, audio_data: bytes, session_id: str) -> None:
        """
        TTS 오디오 스트림을 Redis로 발행 (Phase 36.5)

        오디오 데이터를 청크로 분할하여 Audio Gateway의 AEC에서
        사용할 수 있도록 발행합니다.

        Args:
            audio_data: TTS 합성 결과 오디오 (bytes)
            session_id: 세션 ID
        """
        if not self.redis_client:
            return

        try:
            # bytes를 float32 배열로 변환
            audio_array = np.frombuffer(audio_data, dtype=np.float32)

            # 청크 단위로 분할하여 발행
            total_samples = len(audio_array)
            chunks_sent = 0

            for i in range(0, total_samples, TTS_CHUNK_SIZE):
                chunk = audio_array[i:i + TTS_CHUNK_SIZE]

                # float32 배열을 bytes로 변환하여 발행
                await self.redis_client.publish(
                    TTS_AUDIO_CHANNEL,
                    chunk.tobytes()
                )
                chunks_sent += 1

            await self._logger.debug(
                "tts_audio_stream_published",
                f"Published {chunks_sent} audio chunks to Redis",
                session_id=session_id,
                metadata={"total_samples": total_samples, "chunks": chunks_sent}
            )

        except Exception as e:
            await self._logger.error(
                "tts_audio_stream_error",
                f"Failed to publish audio stream: {e}",
                session_id=session_id,
                metadata={"error": str(e)}
            )

    async def _handle_message(self, data: str) -> None:
        """
        TTS 요청 메시지 처리

        Args:
            data: JSON 문자열 메시지
        """
        try:
            # 메시지 파싱
            request = self._parse_message(data)

            session_id = request.get("session_id")
            text = request.get("text")
            voice = request.get("voice", "af_heart")
            speed = request.get("speed", 1.0)

            if not text:
                return

            # Log TTS request received
            await self._logger.info(
                "tts_request_received",
                f"TTS request received: {text[:50]}{'...' if len(text) > 50 else ''}",
                session_id=session_id,
                metadata={"text_length": len(text), "voice": voice, "speed": speed}
            )

            # TTS 합성 수행
            tts_start_time = time.time()

            await self._logger.info(
                "tts_synthesis_started",
                f"TTS synthesis started (voice={voice})",
                session_id=session_id,
                metadata={"voice": voice, "speed": speed}
            )

            # Phase 36.5: TTS 시작 상태 이벤트 발행
            if self.redis_client:
                started_message = json.dumps({
                    "event": "tts_started",
                    "session_id": session_id,
                    "timestamp": time.time()
                })
                await self.redis_client.publish(TTS_STATE_CHANNEL, started_message)

            # KokoroTTS.synthesize 는 text 만 받고 float32 배열을 돌려준다
            # 합성은 무겁고 동기라 스레드로 넘겨 이벤트 루프(다른 요청·헬스체크)를 막지 않는다
            audio = await asyncio.to_thread(self.synthesizer.synthesize, text)
            if isinstance(audio, np.ndarray):
                audio_data = audio.astype(np.float32, copy=False).tobytes()
            else:
                audio_data = audio or b""

            tts_duration = int((time.time() - tts_start_time) * 1000)

            # Phase 36.5: TTS 오디오 스트림 발행
            if self.redis_client and audio_data:
                await self._publish_audio_stream(audio_data, session_id)

            # Log TTS synthesis completion
            await self._logger.info(
                "tts_synthesis_complete",
                f"TTS synthesis complete ({tts_duration}ms)",
                session_id=session_id,
                duration_ms=tts_duration,
                metadata={
                    "voice": voice,
                    "audio_length": len(audio_data) if audio_data else 0
                }
            )

            # Phase 36.5: TTS 완료 상태 이벤트 발행
            if self.redis_client:
                complete_state_message = json.dumps({
                    "event": "tts_complete",
                    "session_id": session_id,
                    "timestamp": time.time()
                })
                await self.redis_client.publish(TTS_STATE_CHANNEL, complete_state_message)

            # 완료 이벤트 발행 (기존 채널)
            complete_message = {
                "session_id": session_id,
                "status": "complete",
                "audio_length": len(audio_data) if audio_data else 0,
                "timestamp": time.time()
            }

            if self.redis_client:
                await self.redis_client.publish(
                    "edgevoice:tts:complete",
                    json.dumps(complete_message)
                )

        except json.JSONDecodeError:
            # 잘못된 JSON은 무시
            await self._logger.warning(
                "tts_invalid_json",
                "Received invalid JSON message"
            )
        except Exception as e:
            await self._logger.error(
                "tts_error",
                f"TTS message handling error: {str(e)}",
                metadata={"error": str(e)}
            )
            print(f"TTS message handling error: {e}")

    async def run(self) -> None:
        """이벤트 루프 실행"""
        self._is_running = True
        print("[TTS Redis Subscriber] Starting message loop...")

        await self._logger.info(
            "tts_subscriber_started",
            "TTS Redis Subscriber started, waiting for requests"
        )

        while self._is_running:
            try:
                if self.pubsub:
                    message = await self.pubsub.get_message(
                        ignore_subscribe_messages=True,
                        timeout=1.0
                    )
                    if message and message.get("type") == "message":
                        await self._handle_message(message["data"])
            except Exception as e:
                await self._logger.error(
                    "tts_subscriber_error",
                    f"Error in message loop: {str(e)}",
                    metadata={"error": str(e)}
                )
                print(f"[TTS Redis Subscriber] Error in message loop: {e}")
                await asyncio.sleep(1)

        await self._logger.info(
            "tts_subscriber_stopped",
            "TTS Redis Subscriber stopped"
        )
        print("[TTS Redis Subscriber] Message loop stopped")

    async def stop(self) -> None:
        """구독 중지 및 연결 해제"""
        self._is_running = False
        if self.pubsub:
            await self.pubsub.unsubscribe("edgevoice:tts:request")
        if self.redis_client:
            await self.redis_client.aclose()
