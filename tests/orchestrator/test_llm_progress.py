"""
Phase 33.1: LLM Loading Progress Monitoring Tests
TDD Red -> Green -> Refactor

Tests for Docker logs parsing to extract vLLM loading progress.
"""

import sys
from pathlib import Path

import pytest

# Orchestrator app 경로 추가
ORCHESTRATOR_APP_PATH = Path(__file__).parent.parent.parent / "services" / "orchestrator"
sys.path.insert(0, str(ORCHESTRATOR_APP_PATH))


# ============================================================================
# Phase 33.1.1: LLM Progress Parser 모듈 생성
# ============================================================================

class TestLLMProgressModuleExists:
    """Phase 33.1.1: LLM Progress Parser 모듈 존재 테스트"""

    def test_llm_progress_module_exists(self):
        """llm_progress 모듈이 존재하는지 확인"""
        # RED: 모듈이 아직 없으므로 ImportError 발생 예상
        from app import llm_progress
        assert llm_progress is not None

    def test_parse_vllm_progress_function_exists(self):
        """parse_vllm_progress 함수가 존재하는지 확인"""
        from app.llm_progress import parse_vllm_progress
        assert callable(parse_vllm_progress)


# ============================================================================
# Phase 33.1.2: vLLM 로그 패턴 파싱
# ============================================================================

class TestVLLMLogPatternParsing:
    """Phase 33.1.2: vLLM 로그 패턴 파싱 테스트"""

    def test_parse_progress_extracts_percentage(self):
        """로그에서 진행률 퍼센트를 추출하는지 확인"""
        from app.llm_progress import parse_vllm_progress

        # vLLM 실제 로그 패턴: "Loading model weights:  45%|████"
        log_text = "Loading model weights:  45%|████"
        result = parse_vllm_progress(log_text)

        assert result is not None
        assert result["progress_percent"] == 45
        assert result["stage"] == "loading_weights"

    def test_parse_progress_detects_loading_complete(self):
        """모델 로딩 완료를 감지하는지 확인"""
        from app.llm_progress import parse_vllm_progress

        # vLLM 로딩 완료 로그 패턴
        log_text = "INFO: Model loaded successfully"
        result = parse_vllm_progress(log_text)

        assert result is not None
        assert result["progress_percent"] == 100
        assert result["stage"] == "complete"

    def test_parse_progress_detects_initializing(self):
        """초기화 단계를 감지하는지 확인"""
        from app.llm_progress import parse_vllm_progress

        # vLLM 초기화 로그
        log_text = "INFO: Initializing the model"
        result = parse_vllm_progress(log_text)

        assert result is not None
        assert result["progress_percent"] == 0
        assert result["stage"] == "initializing"

    def test_parse_progress_returns_none_for_unknown(self):
        """알 수 없는 로그에 대해 None을 반환하는지 확인"""
        from app.llm_progress import parse_vllm_progress

        log_text = "Some random log message that doesn't match"
        result = parse_vllm_progress(log_text)

        assert result is None


# ============================================================================
# Phase 33.1.3: Docker Logs 읽기
# ============================================================================

class TestDockerLogsReader:
    """Phase 33.1.3: Docker Logs 읽기 테스트"""

    def test_get_docker_logs_function_exists(self):
        """get_docker_logs 함수가 존재하는지 확인"""
        from app.llm_progress import get_docker_logs
        assert callable(get_docker_logs)

    @pytest.mark.asyncio
    async def test_get_docker_logs_returns_string(self):
        """get_docker_logs가 문자열을 반환하는지 확인"""
        from app.llm_progress import get_docker_logs

        # Mock 환경에서는 빈 문자열 또는 에러 메시지 반환
        result = await get_docker_logs("nonexistent_container")
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_get_docker_logs_limits_tail_lines(self):
        """get_docker_logs가 tail_lines 파라미터를 지원하는지 확인"""
        from app.llm_progress import get_docker_logs
        import inspect

        sig = inspect.signature(get_docker_logs)
        assert "tail_lines" in sig.parameters


# ============================================================================
# Phase 33.2: Orchestrator LLM Heartbeat 진행률 추가
# ============================================================================

class TestLLMHeartbeatProgress:
    """Phase 33.2.1: llm_heartbeat_task 진행률 테스트"""

    def test_get_llm_loading_progress_function_exists(self):
        """get_llm_loading_progress 함수가 존재하는지 확인"""
        from app.llm_progress import get_llm_loading_progress
        assert callable(get_llm_loading_progress)

    @pytest.mark.asyncio
    async def test_get_llm_loading_progress_returns_dict(self):
        """get_llm_loading_progress가 딕셔너리를 반환하는지 확인"""
        from app.llm_progress import get_llm_loading_progress

        result = await get_llm_loading_progress("nonexistent_container")
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_get_llm_loading_progress_has_progress_percent(self):
        """get_llm_loading_progress 반환값에 progress_percent가 있는지 확인"""
        from app.llm_progress import get_llm_loading_progress

        result = await get_llm_loading_progress("nonexistent_container")
        assert "progress_percent" in result

    @pytest.mark.asyncio
    async def test_get_llm_loading_progress_has_stage(self):
        """get_llm_loading_progress 반환값에 stage가 있는지 확인"""
        from app.llm_progress import get_llm_loading_progress

        result = await get_llm_loading_progress("nonexistent_container")
        assert "stage" in result


# ============================================================================
# Phase 33.2.2: 진행률 로깅 (Pipeline Log 통합)
# ============================================================================

class TestLLMProgressLogging:
    """Phase 33.2.2: LLM 진행률 로깅 테스트"""

    def test_log_llm_loading_progress_function_exists(self):
        """log_llm_loading_progress 함수가 존재하는지 확인"""
        from app.llm_progress import log_llm_loading_progress
        assert callable(log_llm_loading_progress)

    @pytest.mark.asyncio
    async def test_llm_loading_progress_logged_to_pipeline(self):
        """LLM 로딩 진행률이 Pipeline Log에 기록되는지 확인"""
        from app.llm_progress import log_llm_loading_progress
        from unittest.mock import AsyncMock, patch

        # Mock PipelineLogger
        mock_logger = AsyncMock()
        mock_logger.log = AsyncMock()

        with patch("app.llm_progress.get_logger", return_value=mock_logger):
            await log_llm_loading_progress(
                progress_percent=45,
                stage="loading_weights",
                message="Loading model weights: 45%"
            )

            # log 메서드가 호출되었는지 확인
            mock_logger.log.assert_called_once()

    @pytest.mark.asyncio
    async def test_llm_loading_log_has_correct_event_name(self):
        """LLM 로딩 로그가 올바른 이벤트 이름을 가지는지 확인"""
        from app.llm_progress import log_llm_loading_progress
        from unittest.mock import AsyncMock, patch

        mock_logger = AsyncMock()
        mock_logger.log = AsyncMock()

        with patch("app.llm_progress.get_logger", return_value=mock_logger):
            await log_llm_loading_progress(
                progress_percent=45,
                stage="loading_weights",
                message="Loading model weights: 45%"
            )

            # 호출 시 event 파라미터가 llm_loading_progress인지 확인
            call_args = mock_logger.log.call_args
            assert call_args is not None
            # Checking kwargs or positional arg
            if call_args.kwargs.get("event"):
                assert call_args.kwargs["event"] == "llm_loading_progress"
            else:
                # event is the first positional argument
                assert call_args.args[0] == "llm_loading_progress"