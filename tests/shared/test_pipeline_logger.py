"""
Phase 30.1: Pipeline Logger 공유 라이브러리 테스트

TDD 방식으로 공유 PipelineLogger 클래스를 테스트합니다.

Based on: docs/PRD_Phase30_Code_Cleanup.md
"""
from unittest.mock import AsyncMock

import pytest

# ============================================
# Phase 30.1.1: 공유 라이브러리 구조 생성
# ============================================

class TestSharedPipelineLoggerModule:
    """공유 pipeline_logger 모듈 테스트"""

    def test_shared_pipeline_logger_module_exists(self):
        """shared.pipeline_logger 모듈이 존재하는지 확인"""
        try:
            import shared.pipeline_logger
            assert shared.pipeline_logger is not None
        except ImportError:
            pytest.fail("shared.pipeline_logger module does not exist")

    def test_pipeline_logger_class_importable_from_shared(self):
        """PipelineLogger 클래스가 shared에서 import 가능한지 확인"""
        from shared.pipeline_logger import PipelineLogger
        assert PipelineLogger is not None
        assert callable(PipelineLogger)


# ============================================
# Phase 30.1.2: 공유 PipelineLogger 클래스 구현
# ============================================

class TestPipelineLoggerClass:
    """PipelineLogger 클래스 구현 테스트"""

    def test_pipeline_logger_init_with_service_name(self):
        """service_name으로 초기화"""
        from shared.pipeline_logger import PipelineLogger
        logger = PipelineLogger(service_name="orchestrator")
        assert logger.service_name == "orchestrator"

    def test_pipeline_logger_log_method_exists(self):
        """log 메서드 존재 확인"""
        from shared.pipeline_logger import PipelineLogger
        logger = PipelineLogger(service_name="test")
        assert hasattr(logger, 'log')
        assert callable(logger.log)

    @pytest.mark.asyncio
    async def test_pipeline_logger_log_publishes_to_redis(self):
        """log 메서드가 Redis에 publish하는지 확인"""
        from shared.pipeline_logger import PipelineLogger

        mock_redis = AsyncMock()
        logger = PipelineLogger(service_name="test", redis_client=mock_redis)

        await logger.log(event="test_event", session_id="sess123")

        mock_redis.publish.assert_called_once()

    @pytest.mark.asyncio
    async def test_pipeline_logger_log_returns_log_entry(self):
        """log 메서드가 로그 엔트리를 반환하는지 확인"""
        from shared.pipeline_logger import PipelineLogger

        mock_redis = AsyncMock()
        logger = PipelineLogger(service_name="test", redis_client=mock_redis)

        result = await logger.log(event="test_event", session_id="sess123")

        assert result["service"] == "test"
        assert result["event"] == "test_event"
        assert result["session_id"] == "sess123"
        assert "timestamp" in result

    @pytest.mark.asyncio
    async def test_pipeline_logger_stage_start_method(self):
        """log_stage_start 메서드 테스트"""
        from shared.pipeline_logger import PipelineLogger

        mock_redis = AsyncMock()
        logger = PipelineLogger(service_name="orchestrator", redis_client=mock_redis)

        result = await logger.log_stage_start(stage="stt", session_id="sess123")

        assert result["event"] == "stt_start"
        assert result["data"]["stage"] == "stt"

    @pytest.mark.asyncio
    async def test_pipeline_logger_stage_complete_method(self):
        """log_stage_complete 메서드 테스트"""
        from shared.pipeline_logger import PipelineLogger

        mock_redis = AsyncMock()
        logger = PipelineLogger(service_name="orchestrator", redis_client=mock_redis)

        result = await logger.log_stage_complete(
            stage="stt",
            session_id="sess123",
            duration_ms=150.5
        )

        assert result["event"] == "stt_complete"
        assert result["data"]["stage"] == "stt"
        assert result["data"]["duration_ms"] == 150.5

    @pytest.mark.asyncio
    async def test_pipeline_logger_error_method(self):
        """log_error 메서드 테스트"""
        from shared.pipeline_logger import PipelineLogger

        mock_redis = AsyncMock()
        logger = PipelineLogger(service_name="orchestrator", redis_client=mock_redis)

        result = await logger.log_error(
            error="Connection timeout",
            session_id="sess123"
        )

        assert result["event"] == "error"
        assert result["level"] == "error"
        assert result["data"]["error"] == "Connection timeout"


# ============================================
# Phase 31.5: 공유 상수 export 테스트
# ============================================

class TestPipelineLoggerConstants:
    """Phase 31.5: 공유 상수 export 테스트"""

    def test_heartbeat_interval_is_exported(self):
        """HEARTBEAT_INTERVAL이 shared.pipeline_logger에서 export되는지 확인"""
        from shared.pipeline_logger import HEARTBEAT_INTERVAL
        assert HEARTBEAT_INTERVAL is not None

    def test_heartbeat_interval_value_is_10(self):
        """HEARTBEAT_INTERVAL 값이 10초인지 확인"""
        from shared.pipeline_logger import HEARTBEAT_INTERVAL
        assert HEARTBEAT_INTERVAL == 10

    def test_default_log_channel_is_exported(self):
        """DEFAULT_LOG_CHANNEL이 shared.pipeline_logger에서 export되는지 확인"""
        from shared.pipeline_logger import DEFAULT_LOG_CHANNEL
        assert DEFAULT_LOG_CHANNEL is not None

    def test_default_log_channel_value(self):
        """DEFAULT_LOG_CHANNEL 값이 올바른지 확인"""
        from shared.pipeline_logger import DEFAULT_LOG_CHANNEL
        assert DEFAULT_LOG_CHANNEL == "edgevoice:logs:pipeline"


# ============================================
# Phase 5: PipelineLogger 핵심 기능 테스트
# ============================================

class TestPipelineLoggerFunctionality:
    """Phase 5: PipelineLogger 핵심 기능 테스트"""

    @pytest.mark.asyncio
    async def test_log_entry_has_all_required_fields(self):
        """로그 엔트리에 필수 필드가 포함되는지 확인"""
        from shared.pipeline_logger import PipelineLogger

        mock_redis = AsyncMock()
        logger = PipelineLogger(service_name="test_service", redis_client=mock_redis)
        entry = await logger.log("test_event", data={"key": "value"})

        assert "timestamp" in entry
        assert "service" in entry
        assert entry["service"] == "test_service"
        assert "event" in entry
        assert entry["event"] == "test_event"
        assert "level" in entry

    @pytest.mark.asyncio
    async def test_redis_publish_to_correct_channel(self):
        """Redis publish가 올바른 채널로 호출되는지 확인"""
        from shared.pipeline_logger import DEFAULT_LOG_CHANNEL, PipelineLogger

        mock_redis = AsyncMock()
        logger = PipelineLogger(service_name="test_service", redis_client=mock_redis)

        await logger.log("test_event")

        mock_redis.publish.assert_called_once()
        call_args = mock_redis.publish.call_args
        assert call_args[0][0] == DEFAULT_LOG_CHANNEL

    @pytest.mark.asyncio
    async def test_graceful_failure_without_redis(self):
        """Redis 없이도 로거가 정상 동작하는지 확인"""
        from shared.pipeline_logger import PipelineLogger

        # auto_connect=False로 설정하여 자동 연결 시도 방지
        logger = PipelineLogger(service_name="test_service", redis_client=None, auto_connect=False)

        # Should not raise exception
        entry = await logger.log("test_event")
        assert entry is not None
        assert entry["event"] == "test_event"

    @pytest.mark.asyncio
    async def test_info_method_creates_info_level_log(self):
        """info 메서드가 info 레벨 로그를 생성하는지 확인"""
        from shared.pipeline_logger import PipelineLogger

        mock_redis = AsyncMock()
        logger = PipelineLogger(service_name="test_service", redis_client=mock_redis)

        entry = await logger.info("test info message")

        assert entry["level"] == "info"
        assert entry["event"] == "info"  # info 메서드는 event가 "info"로 설정됨

    @pytest.mark.asyncio
    async def test_log_with_data(self):
        """로그에 data가 포함되는지 확인"""
        from shared.pipeline_logger import PipelineLogger

        mock_redis = AsyncMock()
        logger = PipelineLogger(service_name="test_service", redis_client=mock_redis)

        data = {"key1": "value1", "key2": 42}
        entry = await logger.log("test_event", data=data)

        assert entry["data"]["key1"] == "value1"
        assert entry["data"]["key2"] == 42

    @pytest.mark.asyncio
    async def test_warning_method_creates_warning_level_log(self):
        """warning 메서드가 warning 레벨 로그를 생성하는지 확인"""
        from shared.pipeline_logger import PipelineLogger

        mock_redis = AsyncMock()
        logger = PipelineLogger(service_name="test_service", redis_client=mock_redis)

        entry = await logger.warning("test warning message")

        assert entry["level"] == "warning"
        assert entry["event"] == "warning"

    @pytest.mark.asyncio
    async def test_auto_connect_disabled(self):
        """auto_connect=False일 때 자동 연결하지 않는지 확인"""
        from shared.pipeline_logger import PipelineLogger

        logger = PipelineLogger(service_name="test_service", redis_client=None, auto_connect=False)

        entry = await logger.log("test_event")

        # Redis 연결이 없어도 로그 엔트리는 생성됨
        assert entry is not None
        assert logger.redis is None  # 자동 연결 시도하지 않음
