"""
Phase 32.3: Orchestrator Pipeline Stage Status Reporting Tests

Tests that orchestrator correctly reports each pipeline processing stage
to the backend using the new 7-state system.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestOrchestratorReportsSTTProcessingState:
    """Orchestrator가 STT_PROCESSING 상태를 보고하는지 테스트"""

    @pytest.mark.asyncio
    async def test_orchestrator_reports_stt_processing_state(self):
        """STT 처리 시작 시 STT_PROCESSING 상태로 전이되어야 한다"""
        from services.orchestrator.app.orchestrator import Orchestrator
        from services.orchestrator.app.state_machine import State

        with patch.object(Orchestrator, "_setup_redis", return_value=AsyncMock()):
            orchestrator = Orchestrator()
            orchestrator.state_machine.transition_to(State.LISTENING)

            # STT 처리 시작
            orchestrator.state_machine.transition_to(State.STT_PROCESSING)

            assert orchestrator.state_machine.current_state == State.STT_PROCESSING

    @pytest.mark.asyncio
    async def test_handle_stt_result_transitions_to_stt_processing(self):
        """handle_stt_result 호출 시 STT_PROCESSING 상태를 거쳐야 한다"""
        from services.orchestrator.app.orchestrator import Orchestrator
        from services.orchestrator.app.state_machine import State

        with patch.object(Orchestrator, "_setup_redis", return_value=AsyncMock()):
            orchestrator = Orchestrator()
            orchestrator.state_machine.transition_to(State.LISTENING)

            # State transition history를 추적
            state_history = []
            original_transition = orchestrator.state_machine.transition_to

            def track_transition(state):
                state_history.append(state)
                return original_transition(state)

            orchestrator.state_machine.transition_to = track_transition

            # Mock LLM
            mock_llm = MagicMock()

            async def mock_stream(*args, **kwargs):
                yield "응답"

            mock_llm.generate_stream = mock_stream
            mock_llm.add_to_context = MagicMock()
            orchestrator.llm_client = mock_llm

            await orchestrator.handle_stt_result("테스트")

            # STT_PROCESSING 상태를 거쳤는지 확인
            assert State.STT_PROCESSING in state_history


class TestOrchestratorReportsLLMProcessingState:
    """Orchestrator가 LLM_PROCESSING 상태를 보고하는지 테스트"""

    @pytest.mark.asyncio
    async def test_orchestrator_reports_llm_processing_state(self):
        """LLM 처리 시작 시 LLM_PROCESSING 상태로 전이되어야 한다"""
        from services.orchestrator.app.orchestrator import Orchestrator
        from services.orchestrator.app.state_machine import State

        with patch.object(Orchestrator, "_setup_redis", return_value=AsyncMock()):
            orchestrator = Orchestrator()
            orchestrator.state_machine.transition_to(State.LISTENING)
            orchestrator.state_machine.transition_to(State.STT_PROCESSING)

            # LLM 처리 시작
            orchestrator.state_machine.transition_to(State.LLM_PROCESSING)

            assert orchestrator.state_machine.current_state == State.LLM_PROCESSING

    @pytest.mark.asyncio
    async def test_handle_stt_result_transitions_to_llm_processing(self):
        """handle_stt_result 완료 후 LLM_PROCESSING 상태로 전이되어야 한다"""
        from services.orchestrator.app.orchestrator import Orchestrator
        from services.orchestrator.app.state_machine import State

        with patch.object(Orchestrator, "_setup_redis", return_value=AsyncMock()):
            orchestrator = Orchestrator()
            orchestrator.state_machine.transition_to(State.LISTENING)

            # State transition history를 추적
            state_history = []
            original_transition = orchestrator.state_machine.transition_to

            def track_transition(state):
                state_history.append(state)
                return original_transition(state)

            orchestrator.state_machine.transition_to = track_transition

            # Mock LLM
            mock_llm = MagicMock()

            async def mock_stream(*args, **kwargs):
                yield "응답"

            mock_llm.generate_stream = mock_stream
            mock_llm.add_to_context = MagicMock()
            orchestrator.llm_client = mock_llm

            await orchestrator.handle_stt_result("테스트")

            # LLM_PROCESSING 상태를 거쳤는지 확인
            assert State.LLM_PROCESSING in state_history


class TestOrchestratorReportsTTSProcessingState:
    """Orchestrator가 TTS_PROCESSING 상태를 보고하는지 테스트"""

    @pytest.mark.asyncio
    async def test_orchestrator_reports_tts_processing_state(self):
        """TTS 처리 시작 시 TTS_PROCESSING 상태로 전이되어야 한다"""
        from services.orchestrator.app.orchestrator import Orchestrator
        from services.orchestrator.app.state_machine import State

        with patch.object(Orchestrator, "_setup_redis", return_value=AsyncMock()):
            orchestrator = Orchestrator()
            orchestrator.state_machine.transition_to(State.LISTENING)
            orchestrator.state_machine.transition_to(State.STT_PROCESSING)
            orchestrator.state_machine.transition_to(State.LLM_PROCESSING)

            # TTS 처리 시작
            orchestrator.state_machine.transition_to(State.TTS_PROCESSING)

            assert orchestrator.state_machine.current_state == State.TTS_PROCESSING

    @pytest.mark.asyncio
    async def test_first_sentence_triggers_tts_processing_state(self):
        """첫 문장 생성 시 TTS_PROCESSING 상태로 전이되어야 한다"""
        from services.orchestrator.app.orchestrator import Orchestrator
        from services.orchestrator.app.state_machine import State

        with patch.object(Orchestrator, "_setup_redis", return_value=AsyncMock()):
            orchestrator = Orchestrator()
            orchestrator.state_machine.transition_to(State.LISTENING)
            orchestrator.state_machine.transition_to(State.STT_PROCESSING)
            orchestrator.state_machine.transition_to(State.LLM_PROCESSING)

            # State transition history를 추적
            state_history = []
            original_transition = orchestrator.state_machine.transition_to

            def track_transition(state):
                state_history.append(state)
                return original_transition(state)

            orchestrator.state_machine.transition_to = track_transition

            # Mock LLM
            mock_llm = MagicMock()

            async def mock_stream(*args, **kwargs):
                yield "첫 번째 문장입니다."
                yield " 두 번째 문장입니다."

            mock_llm.generate_stream = mock_stream
            mock_llm.add_to_context = MagicMock()
            orchestrator.llm_client = mock_llm

            await orchestrator._process_llm_stream("테스트")

            # TTS_PROCESSING 상태로 전이되었는지 확인
            assert State.TTS_PROCESSING in state_history


class TestBackendClientStateMapping:
    """Backend Client가 올바른 상태 값을 전송하는지 테스트"""

    @pytest.mark.asyncio
    async def test_backend_client_sends_correct_state_value(self):
        """BackendClient가 올바른 상태 문자열을 전송해야 한다"""
        from services.orchestrator.app.backend_client import BackendClient
        from services.orchestrator.app.state_machine import State

        client = BackendClient(base_url="http://test:11000")

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_response = MagicMock()
            mock_response.json.return_value = {"status": "ok"}
            mock_response.raise_for_status = MagicMock()

            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            # STT_PROCESSING 상태 보고
            await client.report_state(State.STT_PROCESSING.value)

            # POST 호출 확인
            mock_client.post.assert_called_once()
            call_args = mock_client.post.call_args
            payload = call_args[1]["json"]

            assert payload["state"] == "stt_processing"

    @pytest.mark.asyncio
    async def test_backend_client_state_matches_orchestrator_state(self):
        """BackendClient 상태가 Orchestrator State enum 값과 일치해야 한다"""
        from services.orchestrator.app.state_machine import State

        # 모든 새로운 상태의 값 확인
        assert State.OFF.value == "off"
        assert State.READY.value == "ready"
        assert State.LISTENING.value == "listening"
        assert State.STT_PROCESSING.value == "stt_processing"
        assert State.LLM_PROCESSING.value == "llm_processing"
        assert State.TTS_PROCESSING.value == "tts_processing"
        assert State.ERROR.value == "error"


class TestPhase32CompletePipelineFlow:
    """Phase 32 완전한 파이프라인 흐름 테스트"""

    @pytest.mark.asyncio
    async def test_complete_pipeline_state_flow(self):
        """완전한 파이프라인 상태 흐름 테스트:
        READY → LISTENING → STT_PROCESSING → LLM_PROCESSING → TTS_PROCESSING → READY
        """
        from services.orchestrator.app.orchestrator import Orchestrator
        from services.orchestrator.app.state_machine import State

        with patch.object(Orchestrator, "_setup_redis", return_value=AsyncMock()):
            orchestrator = Orchestrator()

            # 초기 상태: READY
            assert orchestrator.state_machine.current_state == State.READY

            # Wake word → LISTENING
            await orchestrator.handle_wake_word()
            assert orchestrator.state_machine.current_state == State.LISTENING

            # STT 결과 처리 (STT_PROCESSING → LLM_PROCESSING → ... → READY)
            mock_llm = MagicMock()

            async def mock_stream(*args, **kwargs):
                yield "응답입니다."

            mock_llm.generate_stream = mock_stream
            mock_llm.add_to_context = MagicMock()
            orchestrator.llm_client = mock_llm

            await orchestrator.handle_stt_result("테스트")

            # 최종 상태: READY (또는 TTS_PROCESSING 아직 완료 안됨)
            assert orchestrator.state_machine.current_state in [
                State.READY, State.TTS_PROCESSING,
                State.IDLE, State.SPEAKING  # 레거시 별칭
            ]
