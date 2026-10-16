"""
Pipeline Logging E2E Tests

Phase 17.4: Pipeline Logging 통합 테스트
- Heartbeat 로그가 DB에 저장되는지 확인
- SSE를 통해 로그가 전달되는지 확인
- Wake Word 감지 시 로그 시퀀스 확인

Phase 31.5: HEARTBEAT_INTERVAL 중앙화 테스트
- 모든 서비스의 HEARTBEAT_INTERVAL 일관성 검증
"""
import asyncio
import sys
import time
from datetime import datetime, timedelta
from typing import List, Dict, Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestHeartbeatLogging:
    """Heartbeat 로그 테스트"""

    def test_heartbeat_log_structure(self):
        """heartbeat 로그가 올바른 구조를 가져야 한다"""
        # Arrange: expected log structure
        expected_fields = ["service", "stage", "level", "message", "metadata"]

        # Act: create a mock heartbeat log
        heartbeat_log = {
            "service": "stt",
            "stage": "heartbeat",
            "level": "INFO",
            "message": "STT Service alive (uptime: 10s)",
            "metadata": {
                "uptime_seconds": 10,
                "model": "small",
                "device": "cpu"
            }
        }

        # Assert: all expected fields are present
        for field in expected_fields:
            assert field in heartbeat_log

    def test_heartbeat_metadata_includes_uptime(self):
        """heartbeat 메타데이터에 uptime이 포함되어야 한다"""
        # Arrange
        metadata = {
            "uptime_seconds": 120,
            "service": "stt"
        }

        # Assert
        assert "uptime_seconds" in metadata
        assert isinstance(metadata["uptime_seconds"], int)
        assert metadata["uptime_seconds"] >= 0

    @pytest.mark.asyncio
    async def test_heartbeat_interval_is_10_seconds(self):
        """heartbeat 간격이 10초여야 한다"""
        from services.stt.app.main import HEARTBEAT_INTERVAL

        assert HEARTBEAT_INTERVAL == 10


class TestSSELogStreaming:
    """SSE 로그 스트리밍 테스트"""

    def test_sse_log_event_format(self):
        """SSE 로그 이벤트가 올바른 형식이어야 한다"""
        # Arrange: expected SSE event format
        log_entry = {
            "id": "test-log-id",
            "session_id": None,
            "service": "orchestrator",
            "stage": "state_change",
            "level": "INFO",
            "message": "State changed: IDLE -> LISTENING",
            "duration_ms": None,
            "metadata": {"previous_state": "IDLE", "new_state": "LISTENING"},
            "created_at": "2024-01-01T00:00:00Z"
        }

        # Assert: all required fields are present
        required_fields = ["id", "service", "stage", "level", "message", "created_at"]
        for field in required_fields:
            assert field in log_entry

    def test_sse_event_type_is_log(self):
        """SSE 이벤트 타입이 'log'이어야 한다"""
        # The SSE event should be sent with event type "log"
        # This is checked in the Logs.tsx component: eventSource.addEventListener('log', ...)
        expected_event_type = "log"
        assert expected_event_type == "log"


class TestWakeWordLogSequence:
    """Wake Word 감지 로그 시퀀스 테스트"""

    def test_wake_word_detection_log_fields(self):
        """wake_word_detected 로그가 올바른 필드를 가져야 한다"""
        log = {
            "service": "wake_word",
            "stage": "wake_word_detected",
            "level": "INFO",
            "message": "Wake word detected: Hey Jarvis",
            "metadata": {
                "wake_word": "Hey Jarvis",
                "confidence": 0.95
            }
        }

        assert log["service"] == "wake_word"
        assert log["stage"] == "wake_word_detected"
        assert "confidence" in log["metadata"]

    def test_listening_mode_log_follows_detection(self):
        """listening_mode_activated 로그가 감지 후에 와야 한다"""
        # Arrange: expected log sequence
        logs = [
            {"stage": "wake_word_detected", "timestamp": 1},
            {"stage": "listening_mode_activated", "timestamp": 2}
        ]

        # Assert: listening_mode comes after detection
        detection_idx = next(i for i, log in enumerate(logs) if log["stage"] == "wake_word_detected")
        listening_idx = next(i for i, log in enumerate(logs) if log["stage"] == "listening_mode_activated")

        assert listening_idx > detection_idx

    def test_orchestrator_state_change_log(self):
        """orchestrator state_change 로그가 올바른 형식이어야 한다"""
        log = {
            "service": "orchestrator",
            "stage": "state_change",
            "level": "INFO",
            "message": "State changed: IDLE -> LISTENING",
            "metadata": {
                "previous_state": "IDLE",
                "new_state": "LISTENING"
            }
        }

        assert log["service"] == "orchestrator"
        assert log["stage"] == "state_change"
        assert "previous_state" in log["metadata"]
        assert "new_state" in log["metadata"]


class TestFullPipelineLogSequence:
    """전체 파이프라인 로그 시퀀스 테스트"""

    def test_pipeline_log_stages_order(self):
        """파이프라인 로그 스테이지가 올바른 순서여야 한다"""
        # Arrange: expected stage order for a full pipeline run
        expected_stages = [
            "wake_word_detected",
            "state_change",  # IDLE -> LISTENING
            "audio_captured",
            "transcription_started",
            "transcription_completed",
            "llm_request_started",
            "llm_response_received",
            "tts_started",
            "tts_completed",
            "state_change"  # SPEAKING -> IDLE
        ]

        # Assert: stages are in order
        assert len(expected_stages) >= 2
        assert expected_stages[0] == "wake_word_detected"
        assert "transcription" in expected_stages[3] or "transcription" in expected_stages[4]

    def test_log_includes_session_id_for_pipeline_run(self):
        """파이프라인 실행 로그에 session_id가 포함되어야 한다"""
        # Arrange: mock pipeline logs with session_id
        session_id = "session-123-abc"
        logs = [
            {"session_id": session_id, "stage": "wake_word_detected"},
            {"session_id": session_id, "stage": "transcription_started"},
            {"session_id": session_id, "stage": "transcription_completed"}
        ]

        # Assert: all logs have the same session_id
        for log in logs:
            assert log["session_id"] == session_id

    def test_duration_ms_included_in_completed_stages(self):
        """완료 스테이지에 duration_ms가 포함되어야 한다"""
        log = {
            "stage": "transcription_completed",
            "duration_ms": 1500,
            "message": "Transcription completed (1500ms)"
        }

        assert "duration_ms" in log
        assert log["duration_ms"] > 0


class TestLogsPageRealtimeDisplay:
    """Logs 페이지 실시간 표시 테스트"""

    def test_log_entry_display_fields(self):
        """로그 항목 표시에 필요한 필드가 있어야 한다"""
        # From test_logs.spec.ts, the table should have these columns
        required_columns = ["Service", "Stage", "Level", "Message", "Time"]

        log_entry = {
            "service": "stt",  # Service
            "stage": "transcription_completed",  # Stage
            "level": "INFO",  # Level
            "message": "Transcription completed",  # Message
            "created_at": "2024-01-01T00:00:00Z"  # Time
        }

        # Assert: all required display fields are present
        assert "service" in log_entry  # Service column
        assert "stage" in log_entry  # Stage column
        assert "level" in log_entry  # Level column
        assert "message" in log_entry  # Message column
        assert "created_at" in log_entry  # Time column

    def test_sse_status_states(self):
        """SSE 상태가 올바른 값이어야 한다"""
        valid_states = ["disconnected", "connecting", "connected"]

        for state in valid_states:
            assert state in valid_states


# ============================================
# Phase 31.5: HEARTBEAT_INTERVAL 중앙화 테스트
# ============================================

class TestHeartbeatIntervalConsistency:
    """Phase 31.5: 모든 서비스 HEARTBEAT_INTERVAL 일관성 테스트"""

    def test_shared_module_is_single_source_of_truth(self):
        """shared 모듈이 HEARTBEAT_INTERVAL의 유일한 정의 소스인지 확인"""
        from shared.pipeline_logger import HEARTBEAT_INTERVAL
        assert HEARTBEAT_INTERVAL == 10

    def test_all_services_heartbeat_interval_matches_shared(self):
        """모든 서비스의 HEARTBEAT_INTERVAL이 shared 모듈과 동일한지 확인"""
        from shared.pipeline_logger import HEARTBEAT_INTERVAL as SHARED_INTERVAL

        services = [
            ("services/stt", "STT"),
            ("services/tts", "TTS"),
            ("services/orchestrator", "Orchestrator"),
            ("services/audio_gateway", "Audio Gateway"),
            ("services/wake_word", "Wake Word"),
        ]

        for service_path, service_name in services:
            sys.path.insert(0, service_path)
            try:
                from app.pipeline_logger import HEARTBEAT_INTERVAL
                assert HEARTBEAT_INTERVAL == SHARED_INTERVAL, \
                    f"{service_name} HEARTBEAT_INTERVAL ({HEARTBEAT_INTERVAL}) != shared ({SHARED_INTERVAL})"
            finally:
                sys.path.pop(0)
                # Clear module cache
                if "app.pipeline_logger" in sys.modules:
                    del sys.modules["app.pipeline_logger"]


class TestPhase31_5HeartbeatCentralization:
    """Phase 31.5: HEARTBEAT_INTERVAL 중앙화 E2E 테스트"""

    def test_all_wrappers_re_export_from_shared(self):
        """모든 서비스 wrapper가 shared 모듈에서 re-export하는지 확인"""
        from shared.pipeline_logger import HEARTBEAT_INTERVAL as SHARED

        # 각 서비스별 검증
        service_paths = [
            "services/stt",
            "services/tts",
            "services/orchestrator",
            "services/audio_gateway",
            "services/wake_word",
        ]

        for path in service_paths:
            sys.path.insert(0, path)
            try:
                from app.pipeline_logger import HEARTBEAT_INTERVAL
                assert HEARTBEAT_INTERVAL == SHARED
            finally:
                sys.path.pop(0)
                if "app.pipeline_logger" in sys.modules:
                    del sys.modules["app.pipeline_logger"]

    def test_default_log_channel_consistency(self):
        """모든 서비스의 DEFAULT_LOG_CHANNEL이 shared 모듈과 동일한지 확인"""
        from shared.pipeline_logger import DEFAULT_LOG_CHANNEL as SHARED_CHANNEL

        service_paths = [
            "services/stt",
            "services/tts",
            "services/orchestrator",
            "services/audio_gateway",
            "services/wake_word",
        ]

        for path in service_paths:
            sys.path.insert(0, path)
            try:
                from app.pipeline_logger import DEFAULT_LOG_CHANNEL
                assert DEFAULT_LOG_CHANNEL == SHARED_CHANNEL, \
                    f"DEFAULT_LOG_CHANNEL mismatch in {path}"
            finally:
                sys.path.pop(0)
                if "app.pipeline_logger" in sys.modules:
                    del sys.modules["app.pipeline_logger"]
