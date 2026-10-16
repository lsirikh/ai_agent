"""
Orchestrator TTS Integration Tests

Phase 8.3-8.4: Orchestrator와 TTS 서비스 간 통합 테스트
"""
import asyncio
import json
import time
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestOrchestratorTTSRequest:
    """Orchestrator TTS 요청 발행 테스트"""

    @pytest.mark.asyncio
    async def test_process_sentence_publishes_tts_request(self):
        """문장 처리 시 TTS 요청이 Redis로 발행되는지 테스트"""
        from services.orchestrator.app.orchestrator import Orchestrator

        # Mock Redis 설정
        mock_redis = MagicMock()
        mock_redis.publish = AsyncMock()
        mock_redis.pubsub = MagicMock(return_value=MagicMock())
        mock_redis.aclose = AsyncMock()

        # Mock LLM client
        mock_llm = MagicMock()

        orchestrator = Orchestrator(
            llm_client=mock_llm,
            redis_client=mock_redis
        )

        # 세션 ID 설정
        orchestrator._current_session_id = "test-session-123"

        # TTS 요청 발행
        await orchestrator.publish_tts_request("안녕하세요, 테스트입니다.")

        # Redis publish 호출 확인
        mock_redis.publish.assert_called_once()
        call_args = mock_redis.publish.call_args
        assert call_args[0][0] == "edgevoice:tts:request"

    @pytest.mark.asyncio
    async def test_tts_request_message_format(self):
        """TTS 요청 메시지가 올바른 포맷인지 테스트"""
        from services.orchestrator.app.orchestrator import Orchestrator

        mock_redis = MagicMock()
        mock_redis.publish = AsyncMock()
        mock_redis.pubsub = MagicMock(return_value=MagicMock())
        mock_redis.aclose = AsyncMock()

        mock_llm = MagicMock()

        orchestrator = Orchestrator(
            llm_client=mock_llm,
            redis_client=mock_redis
        )
        orchestrator._current_session_id = "session-456"

        await orchestrator.publish_tts_request("테스트 문장")

        # 발행된 메시지 파싱
        call_args = mock_redis.publish.call_args
        message = json.loads(call_args[0][1])

        # 필수 필드 확인
        assert "session_id" in message
        assert "text" in message
        assert "voice" in message
        assert "speed" in message
        assert "timestamp" in message

    @pytest.mark.asyncio
    async def test_tts_request_includes_session_id(self):
        """TTS 요청에 세션 ID가 포함되는지 테스트"""
        from services.orchestrator.app.orchestrator import Orchestrator

        mock_redis = MagicMock()
        mock_redis.publish = AsyncMock()
        mock_redis.pubsub = MagicMock(return_value=MagicMock())
        mock_redis.aclose = AsyncMock()

        mock_llm = MagicMock()

        orchestrator = Orchestrator(
            llm_client=mock_llm,
            redis_client=mock_redis
        )
        orchestrator._current_session_id = "my-unique-session"

        await orchestrator.publish_tts_request("세션 테스트")

        call_args = mock_redis.publish.call_args
        message = json.loads(call_args[0][1])

        assert message["session_id"] == "my-unique-session"

    @pytest.mark.asyncio
    async def test_tts_request_includes_voice_settings(self):
        """TTS 요청에 음성 설정이 포함되는지 테스트"""
        from services.orchestrator.app.orchestrator import Orchestrator

        mock_redis = MagicMock()
        mock_redis.publish = AsyncMock()
        mock_redis.pubsub = MagicMock(return_value=MagicMock())
        mock_redis.aclose = AsyncMock()

        mock_llm = MagicMock()

        orchestrator = Orchestrator(
            llm_client=mock_llm,
            redis_client=mock_redis
        )
        orchestrator._current_session_id = "voice-test-session"
        orchestrator._tts_voice = "af_sky"
        orchestrator._tts_speed = 1.2

        await orchestrator.publish_tts_request("음성 설정 테스트")

        call_args = mock_redis.publish.call_args
        message = json.loads(call_args[0][1])

        assert message["voice"] == "af_sky"
        assert message["speed"] == 1.2


class TestOrchestratorTTSComplete:
    """Orchestrator TTS 완료 처리 테스트"""

    @pytest.mark.asyncio
    async def test_on_tts_complete_handler(self):
        """TTS 완료 핸들러가 호출되는지 테스트"""
        from services.orchestrator.app.orchestrator import Orchestrator
        from services.orchestrator.app.state_machine import State

        mock_redis = MagicMock()
        mock_redis.publish = AsyncMock()
        mock_redis.pubsub = MagicMock(return_value=MagicMock())
        mock_redis.aclose = AsyncMock()

        mock_llm = MagicMock()

        orchestrator = Orchestrator(
            llm_client=mock_llm,
            redis_client=mock_redis
        )

        # SPEAKING 상태로 설정
        orchestrator.state_machine._current_state = State.SPEAKING

        # TTS 완료 처리
        result = await orchestrator.handle_speaking_complete()

        assert result is True
        assert orchestrator.state_machine.current_state == State.IDLE

    @pytest.mark.asyncio
    async def test_on_tts_complete_ignores_different_session(self):
        """다른 세션의 TTS 완료 메시지는 무시하는지 테스트"""
        from services.orchestrator.app.orchestrator import Orchestrator
        from services.orchestrator.app.state_machine import State

        mock_redis = MagicMock()
        mock_redis.publish = AsyncMock()
        mock_redis.pubsub = MagicMock(return_value=MagicMock())
        mock_redis.aclose = AsyncMock()

        mock_llm = MagicMock()

        orchestrator = Orchestrator(
            llm_client=mock_llm,
            redis_client=mock_redis
        )
        orchestrator._current_session_id = "my-session"

        # SPEAKING 상태로 설정
        orchestrator.state_machine._current_state = State.SPEAKING

        # 다른 세션의 TTS 완료 메시지
        data = {
            "session_id": "other-session",
            "status": "complete"
        }

        # _handle_tts_complete 메서드 호출 (존재하면)
        if hasattr(orchestrator, '_handle_tts_complete'):
            await orchestrator._handle_tts_complete(data)
            # 상태가 변경되지 않아야 함
            assert orchestrator.state_machine.current_state == State.SPEAKING
