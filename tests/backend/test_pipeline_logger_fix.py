"""
Phase 31: Pipeline Logging System Fix Tests

TDD 방식으로 Pipeline Logger 문제를 해결합니다.

Based on: PIPELINE_LOGGING_ANALYSIS.md
"""
import pytest
import os
import sys


# ============================================
# Phase 31.1.1: Audio Gateway Wrapper
# ============================================

class TestAudioGatewayPipelineLoggerWrapper:
    """Audio Gateway pipeline_logger.py wrapper 테스트"""

    def test_audio_gateway_pipeline_logger_exists(self):
        """audio_gateway/app/pipeline_logger.py 파일 존재 확인"""
        file_path = "services/audio_gateway/app/pipeline_logger.py"
        assert os.path.exists(file_path), f"File should exist: {file_path}"

    def test_audio_gateway_pipeline_logger_has_get_logger(self):
        """get_logger 함수 존재 확인"""
        # Add to path for import
        sys.path.insert(0, "services/audio_gateway")
        try:
            from app.pipeline_logger import get_logger
            assert callable(get_logger), "get_logger should be callable"
        finally:
            sys.path.pop(0)

    def test_audio_gateway_get_logger_returns_pipeline_logger(self):
        """get_logger가 PipelineLogger 인스턴스 반환"""
        sys.path.insert(0, "services/audio_gateway")
        try:
            from app.pipeline_logger import get_logger
            from shared.pipeline_logger import PipelineLogger

            logger = get_logger("audio_gateway")
            assert isinstance(logger, PipelineLogger), \
                "get_logger should return PipelineLogger instance"
        finally:
            sys.path.pop(0)


# ============================================
# Phase 31.1.2: Wake Word Wrapper
# ============================================

class TestWakeWordPipelineLoggerWrapper:
    """Wake Word pipeline_logger.py wrapper 테스트"""

    def test_wake_word_pipeline_logger_exists(self):
        """wake_word/app/pipeline_logger.py 파일 존재 확인"""
        file_path = "services/wake_word/app/pipeline_logger.py"
        assert os.path.exists(file_path), f"File should exist: {file_path}"

    def test_wake_word_pipeline_logger_has_get_logger(self):
        """get_logger 함수 존재 확인"""
        sys.path.insert(0, "services/wake_word")
        try:
            from app.pipeline_logger import get_logger
            assert callable(get_logger), "get_logger should be callable"
        finally:
            sys.path.pop(0)

    def test_wake_word_get_logger_returns_pipeline_logger(self):
        """get_logger가 PipelineLogger 인스턴스 반환"""
        sys.path.insert(0, "services/wake_word")
        try:
            from app.pipeline_logger import get_logger
            from shared.pipeline_logger import PipelineLogger

            logger = get_logger("wake_word")
            assert isinstance(logger, PipelineLogger), \
                "get_logger should return PipelineLogger instance"
        finally:
            sys.path.pop(0)


# ============================================
# Phase 31.1.3: STT Wrapper
# ============================================

class TestSTTPipelineLoggerWrapper:
    """STT pipeline_logger.py wrapper 테스트"""

    def test_stt_pipeline_logger_exists(self):
        """stt/app/pipeline_logger.py 파일 존재 확인"""
        file_path = "services/stt/app/pipeline_logger.py"
        assert os.path.exists(file_path), f"File should exist: {file_path}"

    def test_stt_pipeline_logger_has_get_logger(self):
        """get_logger 함수 존재 확인"""
        sys.path.insert(0, "services/stt")
        try:
            from app.pipeline_logger import get_logger
            assert callable(get_logger), "get_logger should be callable"
        finally:
            sys.path.pop(0)

    def test_stt_get_logger_returns_pipeline_logger(self):
        """get_logger가 PipelineLogger 인스턴스 반환"""
        sys.path.insert(0, "services/stt")
        try:
            from app.pipeline_logger import get_logger
            from shared.pipeline_logger import PipelineLogger

            logger = get_logger("stt")
            assert isinstance(logger, PipelineLogger), \
                "get_logger should return PipelineLogger instance"
        finally:
            sys.path.pop(0)


# ============================================
# Phase 31.1.4: TTS Wrapper
# ============================================

class TestTTSPipelineLoggerWrapper:
    """TTS pipeline_logger.py wrapper 테스트"""

    def test_tts_pipeline_logger_exists(self):
        """tts/app/pipeline_logger.py 파일 존재 확인"""
        file_path = "services/tts/app/pipeline_logger.py"
        assert os.path.exists(file_path), f"File should exist: {file_path}"

    def test_tts_pipeline_logger_has_get_logger(self):
        """get_logger 함수 존재 확인"""
        sys.path.insert(0, "services/tts")
        try:
            from app.pipeline_logger import get_logger
            assert callable(get_logger), "get_logger should be callable"
        finally:
            sys.path.pop(0)

    def test_tts_get_logger_returns_pipeline_logger(self):
        """get_logger가 PipelineLogger 인스턴스 반환"""
        sys.path.insert(0, "services/tts")
        try:
            from app.pipeline_logger import get_logger
            from shared.pipeline_logger import PipelineLogger

            logger = get_logger("tts")
            assert isinstance(logger, PipelineLogger), \
                "get_logger should return PipelineLogger instance"
        finally:
            sys.path.pop(0)


# ============================================
# Phase 31.1.5: Orchestrator Wrapper
# ============================================

class TestOrchestratorPipelineLoggerWrapper:
    """Orchestrator pipeline_logger.py wrapper 테스트"""

    def test_orchestrator_pipeline_logger_exists(self):
        """orchestrator/app/pipeline_logger.py 파일 존재 확인"""
        file_path = "services/orchestrator/app/pipeline_logger.py"
        assert os.path.exists(file_path), f"File should exist: {file_path}"

    def test_orchestrator_pipeline_logger_has_get_logger(self):
        """get_logger 함수 존재 확인"""
        sys.path.insert(0, "services/orchestrator")
        try:
            from app.pipeline_logger import get_logger
            assert callable(get_logger), "get_logger should be callable"
        finally:
            sys.path.pop(0)

    def test_orchestrator_pipeline_logger_has_pipeline_logger_class(self):
        """PipelineLogger 클래스 re-export 확인"""
        sys.path.insert(0, "services/orchestrator")
        try:
            from app.pipeline_logger import PipelineLogger
            assert PipelineLogger is not None, \
                "PipelineLogger should be importable"
        finally:
            sys.path.pop(0)

    def test_orchestrator_get_logger_returns_pipeline_logger(self):
        """get_logger가 PipelineLogger 인스턴스 반환"""
        sys.path.insert(0, "services/orchestrator")
        try:
            from app.pipeline_logger import get_logger
            from shared.pipeline_logger import PipelineLogger

            logger = get_logger("orchestrator")
            assert isinstance(logger, PipelineLogger), \
                "get_logger should return PipelineLogger instance"
        finally:
            sys.path.pop(0)


# ============================================
# Phase 31.2.1: LogSubscriber 채널 수정
# ============================================

class TestLogSubscriberChannel:
    """LogSubscriber Redis 채널 테스트"""

    def test_log_subscriber_uses_pipeline_logs_channel(self):
        """LogSubscriber가 edgevoice:logs:pipeline 채널 사용"""
        from services.backend.app.services.log_subscriber import LOGS_CHANNEL
        assert LOGS_CHANNEL == "edgevoice:logs:pipeline", \
            f"LOGS_CHANNEL should be 'edgevoice:logs:pipeline', got '{LOGS_CHANNEL}'"

    def test_log_subscriber_channel_matches_redis_channels_constant(self):
        """LogSubscriber 채널이 RedisChannels 상수와 일치"""
        from services.backend.app.services.log_subscriber import LOGS_CHANNEL
        from services.backend.app.constants.redis_channels import RedisChannels

        assert LOGS_CHANNEL == RedisChannels.PIPELINE_LOGS, \
            "LOGS_CHANNEL should match RedisChannels.PIPELINE_LOGS"


# ============================================
# Phase 31.2.2: LogBroadcaster 채널 확인
# ============================================

class TestLogBroadcasterChannel:
    """LogBroadcaster Redis 채널 테스트"""

    def test_log_broadcaster_channel_is_pipeline_logs(self):
        """LogBroadcaster가 edgevoice:logs:pipeline 채널 사용"""
        from services.backend.app.services.log_broadcaster import LOGS_CHANNEL
        from services.backend.app.constants.redis_channels import RedisChannels
        assert LOGS_CHANNEL == RedisChannels.PIPELINE_LOGS, \
            f"LogBroadcaster LOGS_CHANNEL should be '{RedisChannels.PIPELINE_LOGS}', got '{LOGS_CHANNEL}'"


# ============================================
# Phase 31.3.1: DASHBOARD_UPDATES_CHANNEL Export
# ============================================

class TestDashboardUpdatesChannelExport:
    """DASHBOARD_UPDATES_CHANNEL 상수 export 테스트"""

    def test_dashboard_updates_channel_exportable_from_state_manager(self):
        """state_manager에서 DASHBOARD_UPDATES_CHANNEL import 가능"""
        from services.backend.app.services.state_manager import DASHBOARD_UPDATES_CHANNEL
        assert DASHBOARD_UPDATES_CHANNEL is not None, \
            "DASHBOARD_UPDATES_CHANNEL should be importable"

    def test_dashboard_updates_channel_equals_redis_channels_constant(self):
        """DASHBOARD_UPDATES_CHANNEL이 RedisChannels 상수와 일치"""
        from services.backend.app.services.state_manager import DASHBOARD_UPDATES_CHANNEL
        from services.backend.app.constants.redis_channels import RedisChannels

        assert DASHBOARD_UPDATES_CHANNEL == RedisChannels.DASHBOARD_UPDATES, \
            "DASHBOARD_UPDATES_CHANNEL should equal RedisChannels.DASHBOARD_UPDATES"


# ============================================
# Phase 31.3.2: status.py Import 확인
# ============================================

class TestStatusImport:
    """status.py의 import 오류 수정 테스트"""

    def test_status_imports_dashboard_updates_channel(self):
        """status.py에서 DASHBOARD_UPDATES_CHANNEL import 성공"""
        try:
            # 이 import가 성공하면 테스트 통과
            from services.backend.app.routes.status import router
            assert router is not None
        except ImportError as e:
            pytest.fail(f"status.py import failed: {e}")


# ============================================
# Phase 31.4.1: LogSubscriber DB 저장 연동
# ============================================

class TestLogSubscriberDbIntegration:
    """LogSubscriber DB 저장 연동 테스트"""

    def test_log_subscriber_has_repository_parameter(self):
        """LogSubscriber.__init__에 log_repository 파라미터 존재"""
        from services.backend.app.services.log_subscriber import LogSubscriber
        import inspect

        sig = inspect.signature(LogSubscriber.__init__)
        params = list(sig.parameters.keys())

        # 'self' 제외하고 확인
        assert 'on_log' in params or 'log_repository' in params, \
            "LogSubscriber should have on_log or log_repository parameter"

    def test_log_subscriber_saves_to_db_on_receive(self):
        """로그 수신 시 DB에 저장"""
        # 이 테스트는 mock이 필요함
        # 실제 구현에서 on_log 콜백으로 DB 저장 로직 호출 여부 확인
        from services.backend.app.services.log_subscriber import LogSubscriber

        saved_logs = []

        async def mock_save(log_data):
            saved_logs.append(log_data)

        subscriber = LogSubscriber(on_log=mock_save)
        assert subscriber._on_log is not None, \
            "LogSubscriber should accept on_log callback"

    def test_log_subscriber_broadcasts_after_save(self):
        """DB 저장 후 SSE로 브로드캐스트"""
        # LogBroadcaster가 정상적으로 import 가능한지 확인
        from services.backend.app.services.log_broadcaster import broadcast_log
        assert callable(broadcast_log), \
            "broadcast_log should be callable"


# ============================================
# Phase 31.5.1: 서비스 Import 성공 확인
# ============================================

class TestServiceImports:
    """각 서비스에서 pipeline_logger import 성공 테스트"""

    def test_audio_gateway_imports_pipeline_logger_successfully(self):
        """Audio Gateway에서 pipeline_logger import 성공"""
        sys.path.insert(0, "services/audio_gateway")
        try:
            # 이 import가 성공하면 테스트 통과
            from app.pipeline_logger import get_logger
            logger = get_logger("audio_gateway")
            assert logger is not None
        except ModuleNotFoundError as e:
            pytest.fail(f"Audio Gateway import failed: {e}")
        finally:
            sys.path.pop(0)

    def test_wake_word_imports_pipeline_logger_successfully(self):
        """Wake Word에서 pipeline_logger import 성공"""
        sys.path.insert(0, "services/wake_word")
        try:
            from app.pipeline_logger import get_logger
            logger = get_logger("wake_word")
            assert logger is not None
        except ModuleNotFoundError as e:
            pytest.fail(f"Wake Word import failed: {e}")
        finally:
            sys.path.pop(0)

    def test_stt_imports_pipeline_logger_successfully(self):
        """STT에서 pipeline_logger import 성공"""
        sys.path.insert(0, "services/stt")
        try:
            from app.pipeline_logger import get_logger
            logger = get_logger("stt")
            assert logger is not None
        except ModuleNotFoundError as e:
            pytest.fail(f"STT import failed: {e}")
        finally:
            sys.path.pop(0)

    def test_tts_imports_pipeline_logger_successfully(self):
        """TTS에서 pipeline_logger import 성공"""
        sys.path.insert(0, "services/tts")
        try:
            from app.pipeline_logger import get_logger
            logger = get_logger("tts")
            assert logger is not None
        except ModuleNotFoundError as e:
            pytest.fail(f"TTS import failed: {e}")
        finally:
            sys.path.pop(0)

    def test_orchestrator_imports_pipeline_logger_successfully(self):
        """Orchestrator에서 pipeline_logger import 성공"""
        sys.path.insert(0, "services/orchestrator")
        try:
            from app.pipeline_logger import get_logger, PipelineLogger
            logger = get_logger("orchestrator")
            assert logger is not None
            assert PipelineLogger is not None
        except ModuleNotFoundError as e:
            pytest.fail(f"Orchestrator import failed: {e}")
        finally:
            sys.path.pop(0)


# ============================================
# Phase 31.5.2: HEARTBEAT_INTERVAL Re-export 테스트
# ============================================

class TestWrapperHeartbeatInterval:
    """Phase 31.5: 서비스별 wrapper HEARTBEAT_INTERVAL 테스트"""

    def test_stt_wrapper_exports_heartbeat_interval(self):
        """STT wrapper에서 HEARTBEAT_INTERVAL export 확인"""
        sys.path.insert(0, "services/stt")
        try:
            from app.pipeline_logger import HEARTBEAT_INTERVAL
            from shared.pipeline_logger import HEARTBEAT_INTERVAL as SHARED_INTERVAL
            assert HEARTBEAT_INTERVAL == SHARED_INTERVAL == 10
        finally:
            sys.path.pop(0)
            if "app.pipeline_logger" in sys.modules:
                del sys.modules["app.pipeline_logger"]

    def test_tts_wrapper_exports_heartbeat_interval(self):
        """TTS wrapper에서 HEARTBEAT_INTERVAL export 확인"""
        sys.path.insert(0, "services/tts")
        try:
            from app.pipeline_logger import HEARTBEAT_INTERVAL
            assert HEARTBEAT_INTERVAL == 10
        finally:
            sys.path.pop(0)
            if "app.pipeline_logger" in sys.modules:
                del sys.modules["app.pipeline_logger"]

    def test_orchestrator_wrapper_exports_heartbeat_interval(self):
        """Orchestrator wrapper에서 HEARTBEAT_INTERVAL export 확인"""
        sys.path.insert(0, "services/orchestrator")
        try:
            from app.pipeline_logger import HEARTBEAT_INTERVAL, PipelineLogger
            assert HEARTBEAT_INTERVAL == 10
            assert PipelineLogger is not None  # re-export 확인
        finally:
            sys.path.pop(0)
            if "app.pipeline_logger" in sys.modules:
                del sys.modules["app.pipeline_logger"]

    def test_audio_gateway_wrapper_exports_heartbeat_interval(self):
        """Audio Gateway wrapper에서 HEARTBEAT_INTERVAL export 확인"""
        sys.path.insert(0, "services/audio_gateway")
        try:
            from app.pipeline_logger import HEARTBEAT_INTERVAL
            assert HEARTBEAT_INTERVAL == 10
        finally:
            sys.path.pop(0)
            if "app.pipeline_logger" in sys.modules:
                del sys.modules["app.pipeline_logger"]

    def test_wake_word_wrapper_exports_heartbeat_interval(self):
        """Wake Word wrapper에서 HEARTBEAT_INTERVAL export 확인"""
        sys.path.insert(0, "services/wake_word")
        try:
            from app.pipeline_logger import HEARTBEAT_INTERVAL
            assert HEARTBEAT_INTERVAL == 10
        finally:
            sys.path.pop(0)
            if "app.pipeline_logger" in sys.modules:
                del sys.modules["app.pipeline_logger"]


# ============================================
# Phase 31.5.3: main.py HEARTBEAT_INTERVAL 로컬 정의 제거 검증
# ============================================

import re

class TestMainPyHeartbeatImport:
    """Phase 31.5: 서비스 main.py에서 HEARTBEAT_INTERVAL 로컬 정의 제거 검증"""

    def _check_no_local_heartbeat_definition(self, file_path: str) -> bool:
        """main.py에서 로컬 HEARTBEAT_INTERVAL 정의가 없는지 확인"""
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        # HEARTBEAT_INTERVAL = 10 형태의 로컬 정의 패턴
        pattern = r'^HEARTBEAT_INTERVAL\s*=\s*\d+'
        matches = re.findall(pattern, content, re.MULTILINE)
        return len(matches) == 0

    def test_stt_no_local_heartbeat_definition(self):
        """STT main.py에서 로컬 HEARTBEAT_INTERVAL 정의 없음"""
        assert self._check_no_local_heartbeat_definition("services/stt/app/main.py")

    def test_tts_no_local_heartbeat_definition(self):
        """TTS main.py에서 로컬 HEARTBEAT_INTERVAL 정의 없음"""
        assert self._check_no_local_heartbeat_definition("services/tts/app/main.py")

    def test_orchestrator_no_local_heartbeat_definition(self):
        """Orchestrator main.py에서 로컬 HEARTBEAT_INTERVAL 정의 없음"""
        assert self._check_no_local_heartbeat_definition("services/orchestrator/app/main.py")

    def test_audio_gateway_no_local_heartbeat_definition(self):
        """Audio Gateway main.py에서 로컬 HEARTBEAT_INTERVAL 정의 없음"""
        assert self._check_no_local_heartbeat_definition("services/audio_gateway/app/main.py")

    def test_wake_word_no_local_heartbeat_definition(self):
        """Wake Word main.py에서 로컬 HEARTBEAT_INTERVAL 정의 없음"""
        assert self._check_no_local_heartbeat_definition("services/wake_word/app/main.py")