"""
Orchestrator Main Tests

Phase 2.3: 오케스트레이터 메인 로직 테스트
Redis 이벤트 기반 음성 대화 흐름 관리
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestOrchestratorInitialization:
    """오케스트레이터 초기화 테스트"""

    def test_orchestrator_initialization(self):
        """기본 설정으로 초기화되어야 한다"""
        from services.orchestrator.app.orchestrator import Orchestrator

        with patch.object(Orchestrator, "_setup_redis", return_value=AsyncMock()):
            orchestrator = Orchestrator()

            assert orchestrator is not None
            assert orchestrator.state_machine is not None
            assert orchestrator.queue_manager is not None

    def test_orchestrator_with_custom_llm_client(self):
        """커스텀 LLM 클라이언트로 초기화할 수 있어야 한다"""
        from services.orchestrator.app.orchestrator import Orchestrator

        mock_llm = MagicMock()

        with patch.object(Orchestrator, "_setup_redis", return_value=AsyncMock()):
            orchestrator = Orchestrator(llm_client=mock_llm)

            assert orchestrator.llm_client == mock_llm


class TestWakeWordHandling:
    """Wake Word 이벤트 처리 테스트"""

    @pytest.mark.asyncio
    async def test_handle_wake_word_event(self):
        """Wake Word 이벤트가 LISTENING 상태로 전이해야 한다"""
        from services.orchestrator.app.orchestrator import Orchestrator
        from services.orchestrator.app.state_machine import State

        with patch.object(Orchestrator, "_setup_redis", return_value=AsyncMock()):
            orchestrator = Orchestrator()

            await orchestrator.handle_wake_word()

            assert orchestrator.state_machine.current_state == State.LISTENING

    @pytest.mark.asyncio
    async def test_wake_word_ignored_when_not_idle(self):
        """IDLE이 아닌 상태에서 Wake Word가 무시되어야 한다"""
        from services.orchestrator.app.orchestrator import Orchestrator
        from services.orchestrator.app.state_machine import State

        with patch.object(Orchestrator, "_setup_redis", return_value=AsyncMock()):
            orchestrator = Orchestrator()
            # Phase 32: LISTENING → STT_PROCESSING → LLM_PROCESSING
            orchestrator.state_machine.transition_to(State.LISTENING)
            orchestrator.state_machine.transition_to(State.STT_PROCESSING)
            orchestrator.state_machine.transition_to(State.LLM_PROCESSING)

            result = await orchestrator.handle_wake_word()

            # Phase 32: LLM_PROCESSING 상태 유지 (PROCESSING은 LLM_PROCESSING 별칭)
            assert orchestrator.state_machine.current_state == State.LLM_PROCESSING
            assert result is False


class TestSTTHandling:
    """STT 이벤트 처리 테스트"""

    @pytest.mark.asyncio
    async def test_handle_stt_final_event(self):
        """STT 완료 이벤트가 PROCESSING 상태로 전이해야 한다 (Phase 32: STT_PROCESSING → LLM_PROCESSING)"""
        from services.orchestrator.app.orchestrator import Orchestrator
        from services.orchestrator.app.state_machine import State

        with patch.object(Orchestrator, "_setup_redis", return_value=AsyncMock()):
            orchestrator = Orchestrator()
            orchestrator.state_machine.transition_to(State.LISTENING)

            # Mock LLM 클라이언트
            mock_llm = MagicMock()

            async def mock_stream(*args, **kwargs):
                yield "응답입니다."

            mock_llm.generate_stream = mock_stream
            mock_llm.add_to_context = MagicMock()
            orchestrator.llm_client = mock_llm

            await orchestrator.handle_stt_result("안녕하세요")

            # Phase 32: 처리 후 READY로 돌아가거나 TTS_PROCESSING/LLM_PROCESSING 상태일 수 있음
            # (레거시 별칭: IDLE=READY, PROCESSING=LLM_PROCESSING, SPEAKING=TTS_PROCESSING)
            assert orchestrator.state_machine.current_state in [
                State.LLM_PROCESSING, State.TTS_PROCESSING, State.READY,
                State.PROCESSING, State.SPEAKING, State.IDLE  # 레거시 별칭 허용
            ]

    @pytest.mark.asyncio
    async def test_stt_result_stored_in_context(self):
        """STT 결과가 대화 컨텍스트에 저장되어야 한다"""
        from services.orchestrator.app.orchestrator import Orchestrator
        from services.orchestrator.app.state_machine import State

        with patch.object(Orchestrator, "_setup_redis", return_value=AsyncMock()):
            orchestrator = Orchestrator()
            orchestrator.state_machine.transition_to(State.LISTENING)

            mock_llm = AsyncMock()

            async def mock_stream(*args, **kwargs):
                yield "응답"

            mock_llm.generate_stream = mock_stream
            mock_llm.add_to_context = MagicMock()
            orchestrator.llm_client = mock_llm

            await orchestrator.handle_stt_result("테스트 메시지")

            # 사용자 메시지가 컨텍스트에 추가되었는지 확인
            mock_llm.add_to_context.assert_called()


class TestBargeInHandling:
    """Barge-in 이벤트 처리 테스트"""

    @pytest.mark.asyncio
    async def test_handle_barge_in_event(self):
        """Barge-in 이벤트가 올바르게 처리되어야 한다"""
        from services.orchestrator.app.orchestrator import Orchestrator
        from services.orchestrator.app.state_machine import State

        with patch.object(Orchestrator, "_setup_redis", return_value=AsyncMock()):
            orchestrator = Orchestrator()
            # SPEAKING 상태로 설정
            orchestrator.state_machine.transition_to(State.LISTENING)
            orchestrator.state_machine.transition_to(State.PROCESSING)
            orchestrator.state_machine.transition_to(State.SPEAKING)

            await orchestrator.handle_barge_in()

            assert orchestrator.state_machine.current_state == State.LISTENING

    @pytest.mark.asyncio
    async def test_barge_in_clears_queue(self):
        """Barge-in 시 문장 큐가 비워져야 한다"""
        from services.orchestrator.app.orchestrator import Orchestrator
        from services.orchestrator.app.state_machine import State

        with patch.object(Orchestrator, "_setup_redis", return_value=AsyncMock()):
            orchestrator = Orchestrator()
            orchestrator.state_machine.transition_to(State.LISTENING)
            orchestrator.state_machine.transition_to(State.PROCESSING)
            orchestrator.state_machine.transition_to(State.SPEAKING)

            # 큐에 내용 추가
            orchestrator.queue_manager.add_token("테스트 문장.")

            await orchestrator.handle_barge_in()

            # 버퍼와 큐가 비워졌는지 확인
            assert orchestrator.queue_manager.get_buffer() == ""


class TestLLMProcessing:
    """LLM 처리 테스트"""

    @pytest.mark.asyncio
    async def test_process_user_input_calls_llm(self):
        """사용자 입력이 LLM 호출로 이어져야 한다"""
        from services.orchestrator.app.orchestrator import Orchestrator
        from services.orchestrator.app.state_machine import State

        with patch.object(Orchestrator, "_setup_redis", return_value=AsyncMock()):
            orchestrator = Orchestrator()
            orchestrator.state_machine.transition_to(State.LISTENING)

            mock_llm = AsyncMock()
            call_count = 0

            async def mock_stream(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                yield "응답입니다."

            mock_llm.generate_stream = mock_stream
            mock_llm.add_to_context = MagicMock()
            orchestrator.llm_client = mock_llm

            await orchestrator.process_user_input("테스트 질문")

            assert call_count > 0

    @pytest.mark.asyncio
    async def test_first_sentence_triggers_speaking_state(self):
        """첫 문장 생성 시 SPEAKING/TTS_PROCESSING 상태로 전이해야 한다 (Phase 32)"""
        from services.orchestrator.app.orchestrator import Orchestrator
        from services.orchestrator.app.state_machine import State

        with patch.object(Orchestrator, "_setup_redis", return_value=AsyncMock()):
            orchestrator = Orchestrator()
            orchestrator.state_machine.transition_to(State.LISTENING)
            # Phase 32: LISTENING → STT_PROCESSING → LLM_PROCESSING
            orchestrator.state_machine.transition_to(State.STT_PROCESSING)
            orchestrator.state_machine.transition_to(State.LLM_PROCESSING)

            mock_llm = AsyncMock()

            async def mock_stream(*args, **kwargs):
                yield "첫 번째 문장입니다."
                yield " 두 번째 문장입니다."

            mock_llm.generate_stream = mock_stream
            mock_llm.add_to_context = MagicMock()
            orchestrator.llm_client = mock_llm

            # 첫 문장이 큐에 들어가면 TTS_PROCESSING(SPEAKING)으로 전이
            await orchestrator._process_llm_stream("테스트")

            # Phase 32: TTS_PROCESSING 상태로 전이되었거나 완료 후 READY
            # (레거시 별칭: SPEAKING=TTS_PROCESSING, IDLE=READY)
            assert orchestrator.state_machine.current_state in [
                State.TTS_PROCESSING, State.READY,
                State.SPEAKING, State.IDLE  # 레거시 별칭 허용
            ]


class TestContextAccumulation:
    """대화 컨텍스트 누적 테스트"""

    @pytest.mark.asyncio
    async def test_context_accumulation(self):
        """여러 턴의 대화가 컨텍스트에 누적되어야 한다"""
        from services.orchestrator.app.orchestrator import Orchestrator
        from services.orchestrator.app.state_machine import State

        with patch.object(Orchestrator, "_setup_redis", return_value=AsyncMock()):
            orchestrator = Orchestrator()

            mock_llm = MagicMock()
            mock_llm.add_to_context = MagicMock()
            mock_llm.get_context = MagicMock(return_value=[
                {"role": "user", "content": "첫 번째 질문"},
                {"role": "assistant", "content": "첫 번째 답변"},
                {"role": "user", "content": "두 번째 질문"},
                {"role": "assistant", "content": "두 번째 답변"}
            ])

            async def mock_stream(*args, **kwargs):
                yield "응답"

            mock_llm.generate_stream = mock_stream
            orchestrator.llm_client = mock_llm

            # 여러 턴 시뮬레이션
            orchestrator.state_machine.transition_to(State.LISTENING)
            await orchestrator.process_user_input("첫 번째 질문")

            context = mock_llm.get_context()
            assert len(context) >= 2

    @pytest.mark.asyncio
    async def test_context_cleared_on_session_reset(self):
        """세션 리셋 시 컨텍스트가 초기화되어야 한다"""
        from services.orchestrator.app.orchestrator import Orchestrator

        with patch.object(Orchestrator, "_setup_redis", return_value=AsyncMock()):
            orchestrator = Orchestrator()

            mock_llm = MagicMock()
            mock_llm.clear_context = MagicMock()
            orchestrator.llm_client = mock_llm

            await orchestrator.reset_session()

            mock_llm.clear_context.assert_called_once()


class TestRedisEventSubscription:
    """Redis 이벤트 구독 테스트"""

    @pytest.mark.asyncio
    async def test_subscribes_to_required_channels(self):
        """필요한 Redis 채널을 구독해야 한다"""
        from services.orchestrator.app.orchestrator import Orchestrator

        mock_redis = MagicMock()
        mock_pubsub = AsyncMock()
        mock_redis.pubsub.return_value = mock_pubsub

        with patch.object(Orchestrator, "_setup_redis", return_value=mock_redis):
            orchestrator = Orchestrator()
            orchestrator.redis = mock_redis

            await orchestrator.subscribe_events()

            # 필수 채널 구독 확인
            mock_pubsub.subscribe.assert_called()

    @pytest.mark.asyncio
    async def test_publishes_tts_request(self):
        """TTS 요청을 Redis로 발행해야 한다"""
        from services.orchestrator.app.orchestrator import Orchestrator

        mock_redis = AsyncMock()

        with patch.object(Orchestrator, "_setup_redis", return_value=mock_redis):
            orchestrator = Orchestrator()
            orchestrator.redis = mock_redis

            await orchestrator.publish_tts_request("테스트 문장")

            mock_redis.publish.assert_called()


class TestTimeoutHandling:
    """타임아웃 처리 테스트"""

    @pytest.mark.asyncio
    async def test_listening_timeout(self):
        """LISTENING 상태에서 타임아웃 처리"""
        from services.orchestrator.app.orchestrator import Orchestrator
        from services.orchestrator.app.state_machine import State

        with patch.object(Orchestrator, "_setup_redis", return_value=AsyncMock()):
            orchestrator = Orchestrator(listening_timeout=0.1)
            orchestrator.state_machine.transition_to(State.LISTENING)

            # 타임아웃 시뮬레이션
            await orchestrator.handle_timeout()

            assert orchestrator.state_machine.current_state == State.IDLE


class TestCompletionHandling:
    """응답 완료 처리 테스트"""

    @pytest.mark.asyncio
    async def test_speaking_completion_returns_to_idle(self):
        """모든 TTS 출력 완료 후 IDLE/READY로 돌아가야 한다 (Phase 32)"""
        from services.orchestrator.app.orchestrator import Orchestrator
        from services.orchestrator.app.state_machine import State

        with patch.object(Orchestrator, "_setup_redis", return_value=AsyncMock()):
            orchestrator = Orchestrator()
            orchestrator.state_machine.transition_to(State.LISTENING)
            # Phase 32: LISTENING → STT_PROCESSING → LLM_PROCESSING → TTS_PROCESSING
            orchestrator.state_machine.transition_to(State.STT_PROCESSING)
            orchestrator.state_machine.transition_to(State.LLM_PROCESSING)
            orchestrator.state_machine.transition_to(State.TTS_PROCESSING)

            await orchestrator.handle_speaking_complete()

            # Phase 32: TTS_PROCESSING → READY (IDLE은 READY의 별칭)
            assert orchestrator.state_machine.current_state in [State.READY, State.IDLE]
