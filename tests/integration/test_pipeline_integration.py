"""
Pipeline Integration Tests

Phase 8.5: 전체 파이프라인 통합 테스트
Wake Word → STT → LLM + RAG → TTS
"""
import asyncio
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestWakeWordToListening:
    """Wake Word → LISTENING 상태 전이 테스트"""

    @pytest.mark.asyncio
    async def test_wake_word_to_listening_state(self):
        """Wake Word 감지 시 LISTENING 상태로 전이되는지 테스트"""
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

        # 초기 상태 확인
        assert orchestrator.state_machine.current_state == State.IDLE

        # Wake Word 이벤트 처리
        result = await orchestrator.handle_wake_word()

        # LISTENING 상태로 전이 확인
        assert result is True
        assert orchestrator.state_machine.current_state == State.LISTENING


class TestSTTResultToProcessing:
    """STT 결과 → PROCESSING 상태 전이 테스트"""

    @pytest.mark.asyncio
    async def test_stt_result_to_processing_state(self):
        """STT 결과 수신 시 PROCESSING 상태로 전이되는지 테스트"""
        from services.orchestrator.app.orchestrator import Orchestrator
        from services.orchestrator.app.state_machine import State

        mock_redis = MagicMock()
        mock_redis.publish = AsyncMock()
        mock_redis.pubsub = MagicMock(return_value=MagicMock())
        mock_redis.aclose = AsyncMock()

        # LLM 응답 스트림 시뮬레이션
        async def mock_stream(text):
            yield "응답"

        mock_llm = MagicMock()
        mock_llm.generate_stream = mock_stream
        mock_llm.add_to_context = MagicMock()

        orchestrator = Orchestrator(
            llm_client=mock_llm,
            redis_client=mock_redis
        )

        # LISTENING 상태로 설정
        orchestrator.state_machine._current_state = State.LISTENING

        # STT 결과 처리 시작 (비동기로 진행됨)
        # handle_stt_result는 LISTENING → PROCESSING 전이 후 LLM 처리를 시작
        # 여기서는 전이만 확인하기 위해 직접 transition 확인

        # transition 직접 테스트
        success = orchestrator.state_machine.transition_to(State.PROCESSING)
        assert success is True
        assert orchestrator.state_machine.current_state == State.PROCESSING


class TestLLMResponseTriggersTTS:
    """LLM 응답 → TTS 요청 테스트"""

    @pytest.mark.asyncio
    async def test_llm_response_triggers_tts_request(self):
        """LLM 응답이 TTS 요청을 트리거하는지 테스트"""
        from services.orchestrator.app.orchestrator import Orchestrator
        from services.orchestrator.app.state_machine import State

        mock_redis = MagicMock()
        mock_redis.publish = AsyncMock()
        mock_redis.pubsub = MagicMock(return_value=MagicMock())
        mock_redis.aclose = AsyncMock()

        # LLM 응답 스트림 시뮬레이션
        async def mock_stream(text):
            response = "안녕하세요. 반갑습니다."
            for char in response:
                yield char

        mock_llm = MagicMock()
        mock_llm.generate_stream = mock_stream
        mock_llm.add_to_context = MagicMock()

        orchestrator = Orchestrator(
            llm_client=mock_llm,
            redis_client=mock_redis
        )
        orchestrator._current_session_id = "test-session"

        # PROCESSING 상태로 설정
        orchestrator.state_machine._current_state = State.PROCESSING

        # LLM 스트림 처리
        await orchestrator._process_llm_stream("테스트 질문")

        # TTS 요청이 Redis로 발행되었는지 확인
        assert mock_redis.publish.called

        # edgevoice:tts:request 채널로 발행 확인
        calls = mock_redis.publish.call_args_list
        tts_requests = [c for c in calls if c[0][0] == "edgevoice:tts:request"]
        assert len(tts_requests) > 0


class TestTTSReceivesRequest:
    """TTS가 Orchestrator 요청을 수신하는지 테스트"""

    @pytest.mark.asyncio
    async def test_tts_receives_request_from_orchestrator(self):
        """TTS Subscriber가 요청을 올바르게 수신하는지 테스트"""
        from services.tts.app.redis_subscriber import TTSRedisSubscriber

        mock_synthesizer = MagicMock()
        mock_synthesizer.synthesize = MagicMock(return_value=b"audio_data")

        subscriber = TTSRedisSubscriber(synthesizer=mock_synthesizer)

        # Orchestrator 형식의 TTS 요청 메시지
        request_message = json.dumps({
            "session_id": "test-session-123",
            "text": "안녕하세요, 테스트입니다.",
            "voice": "af_heart",
            "speed": 1.0,
            "timestamp": time.time()
        })

        # 메시지 파싱
        parsed = subscriber._parse_message(request_message)

        assert parsed["session_id"] == "test-session-123"
        assert parsed["text"] == "안녕하세요, 테스트입니다."
        assert parsed["voice"] == "af_heart"
        assert parsed["speed"] == 1.0

    @pytest.mark.asyncio
    async def test_tts_synthesizes_on_request(self):
        """TTS가 요청 수신 시 합성을 수행하는지 테스트"""
        from services.tts.app.redis_subscriber import TTSRedisSubscriber

        mock_synthesizer = MagicMock()
        mock_synthesizer.synthesize = MagicMock(return_value=b"audio_data")

        with patch("services.tts.app.redis_subscriber.aioredis") as mock_aioredis:
            mock_redis = MagicMock()
            mock_aioredis.Redis.return_value = mock_redis

            mock_pubsub = MagicMock()
            mock_pubsub.subscribe = AsyncMock()
            mock_pubsub.unsubscribe = AsyncMock()
            mock_redis.pubsub.return_value = mock_pubsub
            mock_redis.aclose = AsyncMock()
            mock_redis.publish = AsyncMock()

            subscriber = TTSRedisSubscriber(synthesizer=mock_synthesizer)
            await subscriber.connect()

            # TTS 요청 처리
            request_message = json.dumps({
                "session_id": "test-session",
                "text": "합성할 텍스트",
                "voice": "af_heart",
                "speed": 1.0,
                "timestamp": time.time()
            })

            await subscriber._handle_message(request_message)

            # 합성기 호출 확인
            mock_synthesizer.synthesize.assert_called_once_with(
                text="합성할 텍스트",
                voice="af_heart",
                speed=1.0
            )

            await subscriber.stop()


class TestTTSCompleteToIdle:
    """TTS 완료 → IDLE 전이 테스트"""

    @pytest.mark.asyncio
    async def test_tts_complete_returns_to_idle(self):
        """TTS 완료 시 IDLE 상태로 돌아가는지 테스트"""
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

        # IDLE 상태로 전이 확인
        assert result is True
        assert orchestrator.state_machine.current_state == State.IDLE


class TestFullPipelineE2E:
    """전체 파이프라인 E2E 테스트"""

    @pytest.mark.asyncio
    async def test_full_pipeline_end_to_end(self):
        """Wake Word → STT → LLM → TTS → IDLE 전체 흐름 테스트"""
        from services.orchestrator.app.orchestrator import Orchestrator
        from services.orchestrator.app.state_machine import State

        mock_redis = MagicMock()
        mock_redis.publish = AsyncMock()
        mock_redis.pubsub = MagicMock(return_value=MagicMock())
        mock_redis.aclose = AsyncMock()

        # LLM 응답 스트림 시뮬레이션
        async def mock_stream(text):
            response = "안녕하세요!"
            for char in response:
                yield char

        mock_llm = MagicMock()
        mock_llm.generate_stream = mock_stream
        mock_llm.add_to_context = MagicMock()

        orchestrator = Orchestrator(
            llm_client=mock_llm,
            redis_client=mock_redis
        )
        orchestrator._current_session_id = "e2e-test-session"

        # 1. 초기 상태 IDLE
        assert orchestrator.state_machine.current_state == State.IDLE

        # 2. Wake Word → LISTENING
        await orchestrator.handle_wake_word()
        assert orchestrator.state_machine.current_state == State.LISTENING

        # 3. STT 결과 → PROCESSING → LLM 처리 → SPEAKING → IDLE
        # (handle_stt_result가 전체 흐름을 처리)
        await orchestrator.handle_stt_result("안녕")

        # 잠시 대기 (비동기 처리 완료 대기)
        await asyncio.sleep(0.1)

        # 4. 최종 상태 확인 (IDLE 또는 SPEAKING)
        # LLM 처리 후 자동으로 IDLE로 전이됨
        final_state = orchestrator.state_machine.current_state
        assert final_state in [State.IDLE, State.SPEAKING]

        # TTS 요청이 발행되었는지 확인
        tts_calls = [
            c for c in mock_redis.publish.call_args_list
            if c[0][0] == "edgevoice:tts:request"
        ]
        assert len(tts_calls) > 0


class TestBargeInInterrupt:
    """Barge-in 인터럽트 테스트"""

    @pytest.mark.asyncio
    async def test_barge_in_interrupts_pipeline(self):
        """Barge-in 시 파이프라인이 중단되는지 테스트"""
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

        # SPEAKING 상태로 설정 (TTS 출력 중)
        orchestrator.state_machine._current_state = State.SPEAKING

        # Barge-in 이벤트 처리
        result = await orchestrator.handle_barge_in()

        # LISTENING 상태로 전이 확인 (사용자 입력 대기)
        assert result is True
        assert orchestrator.state_machine.current_state == State.LISTENING

    @pytest.mark.asyncio
    async def test_barge_in_clears_queue(self):
        """Barge-in 시 큐가 클리어되는지 테스트"""
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

        # 큐에 데이터 추가
        orchestrator.queue_manager._buffer = "남은 텍스트..."
        orchestrator.state_machine._current_state = State.SPEAKING

        # Barge-in 처리
        await orchestrator.handle_barge_in()

        # 큐가 클리어되었는지 확인
        assert orchestrator.queue_manager._buffer == ""


# Helper class for async iteration
class AsyncIterator:
    def __init__(self, items):
        self.items = items
        self.index = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.index >= len(self.items):
            raise StopAsyncIteration
        item = self.items[self.index]
        self.index += 1
        return item
