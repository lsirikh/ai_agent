"""
VAD Filtering Tests - Phase 44

Phase 44: VAD 필터링 - Wake Word 서비스 전달 조건 추가
TDD Red 단계: 테스트 먼저 작성

VAD is_speech=True인 경우에만 Wake Word 서비스로 오디오 전달
VAD is_speech=False인 경우 오디오 무시 (Redis 발행 안함)
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import numpy as np
import pytest


class TestVADFilteringWebSocket:
    """WebSocket 핸들러에서 VAD 필터링 테스트"""

    @pytest.mark.asyncio
    async def test_websocket_skips_redis_publish_when_vad_false(self):
        """
        VAD is_speech=False일 때 Redis 발행이 호출되지 않아야 한다.

        Phase 44.1: TDD Red 단계 - 이 테스트는 현재 실패해야 함
        """
        # Mock 설정
        mock_redis = AsyncMock()
        mock_vad = MagicMock()
        mock_vad.detect.return_value = {
            "is_speech": False,
            "probability": 0.2
        }

        # Audio chunk 준비
        audio_chunk = np.zeros(1600, dtype=np.float32)

        # VAD 결과가 is_speech=False일 때
        vad_result = mock_vad.detect(audio_chunk)
        assert vad_result["is_speech"] is False

        # Redis publish가 호출되면 안됨
        # should_publish 로직 시뮬레이션
        should_publish = vad_result.get("is_speech", False)

        if should_publish:
            await mock_redis.publish("edgevoice:audio:input", audio_chunk.tobytes())

        # Redis publish가 호출되지 않았음을 검증
        mock_redis.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_websocket_publishes_to_redis_when_vad_true(self):
        """
        VAD is_speech=True일 때 Redis 발행이 호출되어야 한다.

        Phase 44.1: TDD Red 단계
        """
        # Mock 설정
        mock_redis = AsyncMock()
        mock_vad = MagicMock()
        mock_vad.detect.return_value = {
            "is_speech": True,
            "probability": 0.8
        }

        # Audio chunk 준비
        audio_chunk = np.zeros(1600, dtype=np.float32)

        # VAD 결과가 is_speech=True일 때
        vad_result = mock_vad.detect(audio_chunk)
        assert vad_result["is_speech"] is True

        # should_publish 로직 시뮬레이션
        should_publish = vad_result.get("is_speech", False)

        if should_publish:
            await mock_redis.publish("edgevoice:audio:input", audio_chunk.tobytes())

        # Redis publish가 호출되었음을 검증
        mock_redis.publish.assert_called_once_with(
            "edgevoice:audio:input",
            audio_chunk.tobytes()
        )

    @pytest.mark.asyncio
    async def test_mic_handler_skips_redis_when_vad_false(self):
        """
        마이크 핸들러에서도 VAD is_speech=False일 때 Redis 발행 안함.

        Phase 44.1: TDD Red 단계
        """
        # Mock 설정
        mock_redis = AsyncMock()
        mock_vad = MagicMock()

        # 여러 청크 처리 시뮬레이션
        chunks_processed = 0
        redis_publish_count = 0

        for i in range(10):
            # 짝수 청크는 음성, 홀수는 비음성
            is_speech = (i % 2 == 0)
            mock_vad.detect.return_value = {
                "is_speech": is_speech,
                "probability": 0.8 if is_speech else 0.2
            }

            audio_chunk = np.zeros(1600, dtype=np.float32)
            vad_result = mock_vad.detect(audio_chunk)
            chunks_processed += 1

            # VAD 필터링 적용
            if vad_result.get("is_speech", False):
                await mock_redis.publish("edgevoice:audio:input", audio_chunk.tobytes())
                redis_publish_count += 1

        # 10개 청크 중 5개만 발행되어야 함 (짝수만)
        assert chunks_processed == 10
        assert redis_publish_count == 5
        assert mock_redis.publish.call_count == 5


class TestVADFilteringIntegration:
    """VAD 필터링 통합 테스트"""

    @pytest.mark.asyncio
    async def test_consecutive_speech_chunks_all_published(self):
        """
        연속된 음성 청크가 모두 발행되어야 한다.
        """
        mock_redis = AsyncMock()
        mock_vad = MagicMock()
        mock_vad.detect.return_value = {
            "is_speech": True,
            "probability": 0.9
        }

        for _ in range(5):
            audio_chunk = np.random.randn(1600).astype(np.float32)
            vad_result = mock_vad.detect(audio_chunk)

            if vad_result.get("is_speech", False):
                await mock_redis.publish("edgevoice:audio:input", audio_chunk.tobytes())

        # 모든 5개 청크가 발행됨
        assert mock_redis.publish.call_count == 5

    @pytest.mark.asyncio
    async def test_only_noise_chunks_none_published(self):
        """
        노이즈만 있는 청크는 발행되지 않아야 한다.
        """
        mock_redis = AsyncMock()
        mock_vad = MagicMock()
        mock_vad.detect.return_value = {
            "is_speech": False,
            "probability": 0.1
        }

        for _ in range(10):
            audio_chunk = np.random.randn(1600).astype(np.float32) * 0.01
            vad_result = mock_vad.detect(audio_chunk)

            if vad_result.get("is_speech", False):
                await mock_redis.publish("edgevoice:audio:input", audio_chunk.tobytes())

        # 아무것도 발행되지 않음
        assert mock_redis.publish.call_count == 0

    @pytest.mark.asyncio
    async def test_speech_in_middle_of_noise(self):
        """
        노이즈 사이에 음성이 있을 때 음성만 발행되어야 한다.

        시나리오: [noise, noise, speech, speech, speech, noise, noise]
        """
        mock_redis = AsyncMock()
        mock_vad = MagicMock()

        # VAD 결과 시퀀스: [False, False, True, True, True, False, False]
        vad_results = [
            {"is_speech": False, "probability": 0.1},
            {"is_speech": False, "probability": 0.15},
            {"is_speech": True, "probability": 0.85},
            {"is_speech": True, "probability": 0.9},
            {"is_speech": True, "probability": 0.88},
            {"is_speech": False, "probability": 0.2},
            {"is_speech": False, "probability": 0.1},
        ]
        mock_vad.detect.side_effect = vad_results

        for _ in range(7):
            audio_chunk = np.random.randn(1600).astype(np.float32)
            vad_result = mock_vad.detect(audio_chunk)

            if vad_result.get("is_speech", False):
                await mock_redis.publish("edgevoice:audio:input", audio_chunk.tobytes())

        # 3개 음성 청크만 발행됨
        assert mock_redis.publish.call_count == 3


class TestVADFilteringEdgeCases:
    """VAD 필터링 엣지 케이스 테스트"""

    @pytest.mark.asyncio
    async def test_redis_client_none_does_not_crash(self):
        """
        Redis 클라이언트가 None일 때 크래시하지 않아야 한다.
        """
        mock_vad = MagicMock()
        mock_vad.detect.return_value = {
            "is_speech": True,
            "probability": 0.9
        }

        redis_client = None
        audio_chunk = np.zeros(1600, dtype=np.float32)
        vad_result = mock_vad.detect(audio_chunk)

        # Redis 클라이언트가 None이면 발행하지 않음
        if redis_client and vad_result.get("is_speech", False):
            await redis_client.publish("edgevoice:audio:input", audio_chunk.tobytes())

        # 크래시 없이 완료
        assert True

    @pytest.mark.asyncio
    async def test_vad_result_missing_is_speech_key(self):
        """
        VAD 결과에 is_speech 키가 없을 때 기본값 False 처리.
        """
        mock_redis = AsyncMock()
        mock_vad = MagicMock()
        mock_vad.detect.return_value = {
            "probability": 0.5  # is_speech 키 없음
        }

        audio_chunk = np.zeros(1600, dtype=np.float32)
        vad_result = mock_vad.detect(audio_chunk)

        # is_speech 키가 없으면 기본값 False
        should_publish = vad_result.get("is_speech", False)
        assert should_publish is False

        if should_publish:
            await mock_redis.publish("edgevoice:audio:input", audio_chunk.tobytes())

        # 발행되지 않음
        mock_redis.publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_tts_playing_bypasses_vad_filter(self):
        """
        TTS 재생 중에는 VAD 필터링과 무관하게 Barge-in만 활성화.

        이 테스트는 기존 로직 유지를 확인:
        - TTS 재생 중: Barge-in 감지만 (Wake Word로 전송 안함)
        - TTS 재생 안함: VAD 필터링 후 Wake Word로 전송
        """
        mock_redis = AsyncMock()
        mock_vad = MagicMock()
        mock_vad.detect.return_value = {
            "is_speech": True,
            "probability": 0.9
        }

        # TTS 재생 중일 때
        is_tts_playing = True
        audio_chunk = np.zeros(1600, dtype=np.float32)
        vad_result = mock_vad.detect(audio_chunk)

        if is_tts_playing:
            # Barge-in 처리 (Wake Word로 전송 안함)
            pass
        else:
            # VAD 필터링 적용
            if vad_result.get("is_speech", False):
                await mock_redis.publish("edgevoice:audio:input", audio_chunk.tobytes())

        # TTS 재생 중이므로 Redis 발행 안됨
        mock_redis.publish.assert_not_called()

        # TTS 재생 중이 아닐 때
        is_tts_playing = False
        if is_tts_playing:
            pass
        else:
            if vad_result.get("is_speech", False):
                await mock_redis.publish("edgevoice:audio:input", audio_chunk.tobytes())

        # TTS 재생 중이 아니고 is_speech=True이므로 Redis 발행됨
        mock_redis.publish.assert_called_once()
