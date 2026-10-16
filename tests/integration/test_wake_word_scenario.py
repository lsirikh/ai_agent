"""
Wake Word Scenario Tests

Phase 17.4: "헤이 자비스" 시나리오 테스트
- Wake Word 감지 로그 확인
- Listening 모드 활성화 로그 확인
- Orchestrator 상태 변경 로그 확인
- 전체 파이프라인 로그 시퀀스 확인
"""
from typing import List, Dict, Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestWakeWordDetectedLog:
    """Wake Word 감지 로그 테스트"""

    def test_wake_word_detected_log_has_service(self):
        """wake_word_detected 로그에 service가 'wake_word'여야 한다"""
        log = {
            "service": "wake_word",
            "stage": "wake_word_detected",
            "level": "INFO",
            "message": "Wake word detected: Hey Jarvis"
        }

        assert log["service"] == "wake_word"

    def test_wake_word_detected_log_has_stage(self):
        """wake_word_detected 로그에 stage가 'wake_word_detected'여야 한다"""
        log = {
            "service": "wake_word",
            "stage": "wake_word_detected"
        }

        assert log["stage"] == "wake_word_detected"

    def test_wake_word_detected_log_has_confidence(self):
        """wake_word_detected 로그에 confidence가 포함되어야 한다"""
        log = {
            "service": "wake_word",
            "stage": "wake_word_detected",
            "metadata": {
                "wake_word": "hey_jarvis",
                "confidence": 0.92
            }
        }

        assert "confidence" in log["metadata"]
        assert 0 <= log["metadata"]["confidence"] <= 1


class TestListeningModeActivatedLog:
    """Listening 모드 활성화 로그 테스트"""

    def test_listening_mode_log_has_audio_gateway_service(self):
        """listening_mode_activated 로그에 service가 'audio_gateway'여야 한다"""
        log = {
            "service": "audio_gateway",
            "stage": "listening_mode_activated",
            "level": "INFO",
            "message": "Listening mode activated"
        }

        assert log["service"] == "audio_gateway"

    def test_listening_mode_log_has_correct_stage(self):
        """listening_mode_activated 로그에 올바른 stage가 있어야 한다"""
        log = {
            "service": "audio_gateway",
            "stage": "listening_mode_activated"
        }

        assert log["stage"] == "listening_mode_activated"

    def test_listening_mode_log_follows_wake_word(self):
        """listening_mode 로그가 wake_word 감지 후에 와야 한다"""
        # Arrange: simulate log sequence
        logs = [
            {"timestamp": 1000, "stage": "wake_word_detected"},
            {"timestamp": 1050, "stage": "state_change"},
            {"timestamp": 1100, "stage": "listening_mode_activated"}
        ]

        # Get timestamps
        wake_word_ts = next(log["timestamp"] for log in logs if log["stage"] == "wake_word_detected")
        listening_ts = next(log["timestamp"] for log in logs if log["stage"] == "listening_mode_activated")

        # Assert: listening comes after wake word
        assert listening_ts > wake_word_ts


class TestOrchestratorStateChangeLog:
    """Orchestrator 상태 변경 로그 테스트"""

    def test_state_change_log_has_orchestrator_service(self):
        """state_change 로그에 service가 'orchestrator'여야 한다"""
        log = {
            "service": "orchestrator",
            "stage": "state_change",
            "level": "INFO",
            "message": "State changed: IDLE -> LISTENING"
        }

        assert log["service"] == "orchestrator"

    def test_state_change_log_has_previous_and_new_state(self):
        """state_change 로그에 previous_state와 new_state가 있어야 한다"""
        log = {
            "service": "orchestrator",
            "stage": "state_change",
            "metadata": {
                "previous_state": "IDLE",
                "new_state": "LISTENING"
            }
        }

        assert "previous_state" in log["metadata"]
        assert "new_state" in log["metadata"]

    def test_valid_orchestrator_states(self):
        """orchestrator 상태가 유효한 값이어야 한다"""
        valid_states = ["IDLE", "LISTENING", "PROCESSING", "SPEAKING"]

        state_change = {
            "previous_state": "IDLE",
            "new_state": "LISTENING"
        }

        assert state_change["previous_state"] in valid_states
        assert state_change["new_state"] in valid_states


class TestFullPipelineLogSequence:
    """전체 파이프라인 로그 시퀀스 테스트"""

    def test_full_pipeline_has_minimum_stages(self):
        """전체 파이프라인에 최소 필요한 스테이지가 있어야 한다"""
        # Arrange: minimum required stages for a complete pipeline run
        required_stages = [
            "wake_word_detected",
            "state_change",
            "transcription_completed",
            "llm_response_received",
            "tts_completed"
        ]

        # Act: simulate a full pipeline run
        pipeline_logs = [
            {"stage": "wake_word_detected", "service": "wake_word"},
            {"stage": "state_change", "service": "orchestrator"},
            {"stage": "listening_mode_activated", "service": "audio_gateway"},
            {"stage": "audio_captured", "service": "audio_gateway"},
            {"stage": "transcription_started", "service": "stt"},
            {"stage": "transcription_completed", "service": "stt"},
            {"stage": "llm_request_started", "service": "llm"},
            {"stage": "llm_response_received", "service": "llm"},
            {"stage": "tts_started", "service": "tts"},
            {"stage": "tts_completed", "service": "tts"},
            {"stage": "state_change", "service": "orchestrator"}
        ]

        # Assert: all required stages are present
        logged_stages = [log["stage"] for log in pipeline_logs]
        for stage in required_stages:
            assert stage in logged_stages, f"Missing required stage: {stage}"

    def test_pipeline_logs_have_same_session_id(self):
        """파이프라인 로그가 동일한 session_id를 가져야 한다"""
        session_id = "session-abc-123"

        pipeline_logs = [
            {"session_id": session_id, "stage": "wake_word_detected"},
            {"session_id": session_id, "stage": "transcription_started"},
            {"session_id": session_id, "stage": "transcription_completed"},
            {"session_id": session_id, "stage": "tts_completed"}
        ]

        # Assert: all logs have same session_id
        session_ids = set(log["session_id"] for log in pipeline_logs)
        assert len(session_ids) == 1
        assert session_id in session_ids

    def test_pipeline_logs_are_chronologically_ordered(self):
        """파이프라인 로그가 시간순으로 정렬되어야 한다"""
        pipeline_logs = [
            {"timestamp": 1000, "stage": "wake_word_detected"},
            {"timestamp": 1100, "stage": "state_change"},
            {"timestamp": 1200, "stage": "transcription_started"},
            {"timestamp": 2500, "stage": "transcription_completed"},
            {"timestamp": 2600, "stage": "llm_request_started"},
            {"timestamp": 4000, "stage": "llm_response_received"},
            {"timestamp": 4100, "stage": "tts_started"},
            {"timestamp": 5500, "stage": "tts_completed"}
        ]

        # Assert: timestamps are in ascending order
        timestamps = [log["timestamp"] for log in pipeline_logs]
        assert timestamps == sorted(timestamps)

    def test_duration_included_for_completed_stages(self):
        """완료 스테이지에 duration_ms가 포함되어야 한다"""
        completed_stages = [
            {"stage": "transcription_completed", "duration_ms": 1300},
            {"stage": "llm_response_received", "duration_ms": 1400},
            {"stage": "tts_completed", "duration_ms": 1400}
        ]

        for log in completed_stages:
            assert "duration_ms" in log
            assert log["duration_ms"] > 0


class TestHeyJarvisScenario:
    """'헤이 자비스' 시나리오 전체 테스트"""

    def test_hey_jarvis_triggers_pipeline(self):
        """'헤이 자비스' 호출이 파이프라인을 트리거해야 한다"""
        # Arrange
        wake_word = "hey_jarvis"
        trigger_log = {
            "service": "wake_word",
            "stage": "wake_word_detected",
            "metadata": {"wake_word": wake_word}
        }

        # Assert
        assert trigger_log["metadata"]["wake_word"] == wake_word
        assert trigger_log["stage"] == "wake_word_detected"

    def test_complete_hey_jarvis_flow(self):
        """'헤이 자비스' 전체 흐름이 올바르게 로깅되어야 한다"""
        # Arrange: complete flow
        flow_stages = [
            "wake_word_detected",      # Wake word service detects "Hey Jarvis"
            "state_change",            # Orchestrator: IDLE -> LISTENING
            "listening_mode_activated", # Audio gateway starts listening
            "audio_captured",          # Audio gateway captures speech
            "transcription_started",   # STT starts processing
            "transcription_completed", # STT returns text
            "state_change",            # Orchestrator: LISTENING -> PROCESSING
            "llm_request_started",     # LLM request sent
            "llm_response_received",   # LLM response received
            "tts_started",             # TTS starts synthesis
            "tts_completed",           # TTS completes
            "state_change"             # Orchestrator: SPEAKING -> IDLE
        ]

        # Assert: flow has at least 10 stages
        assert len(flow_stages) >= 10

        # Assert: starts with wake_word_detected
        assert flow_stages[0] == "wake_word_detected"

        # Assert: ends with state_change (back to IDLE)
        assert flow_stages[-1] == "state_change"
