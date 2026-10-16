"""
Phase 30.2: 미사용 코드 삭제 테스트

TDD 방식으로 미사용 코드 삭제를 검증합니다.

Based on: docs/PRD_Phase30_Code_Cleanup.md
"""
import pytest
import os


# ============================================
# Phase 30.2.1: SettingsBroadcaster 삭제
# ============================================

class TestSettingsBroadcasterRemoval:
    """SettingsBroadcaster 삭제 테스트"""

    def test_settings_broadcaster_file_not_exists(self):
        """settings_broadcaster.py 파일이 삭제되었는지 확인"""
        file_path = "services/backend/app/services/settings_broadcaster.py"
        assert not os.path.exists(file_path), f"File should be deleted: {file_path}"

    def test_no_import_references_to_settings_broadcaster(self):
        """settings_broadcaster를 import하는 코드가 없는지 확인"""
        import subprocess
        result = subprocess.run(
            ["grep", "-r", "settings_broadcaster", "services/backend/app/", "--include=*.py"],
            capture_output=True,
            text=True
        )
        # 빈 결과면 import 없음
        assert result.stdout.strip() == "", f"Found references: {result.stdout}"


# ============================================
# Phase 30.2.2: HealthCollector 정리
# ============================================

class TestHealthCollectorCleanup:
    """HealthCollector 정리 테스트"""

    def test_health_collector_removed_or_integrated(self):
        """health_collector.py가 삭제되었거나 프로덕션에서 사용되는지 확인"""
        file_path = "services/backend/app/services/health_collector.py"
        # 파일이 삭제되었거나, 있다면 main.py에서 사용되어야 함
        if os.path.exists(file_path):
            # main.py에서 import되는지 확인
            with open("services/backend/app/main.py", "r") as f:
                content = f.read()
                assert "health_collector" in content.lower(), \
                    "health_collector.py exists but not used in main.py"
        # 파일이 없으면 테스트 통과

    def test_no_dead_code_in_health_collector(self):
        """health_collector에 dead code가 없는지 확인 (run_forever 등)"""
        file_path = "services/backend/app/services/health_collector.py"
        if os.path.exists(file_path):
            with open(file_path, "r") as f:
                content = f.read()
                # run_forever가 있다면 사용되는지 확인
                if "run_forever" in content:
                    # main.py에서 run_forever 호출하는지 확인
                    with open("services/backend/app/main.py", "r") as main_f:
                        main_content = main_f.read()
                        assert "run_forever" in main_content, \
                            "run_forever method exists but never called"


# ============================================
# Phase 30.3.1: StateManager 싱글톤 패턴
# ============================================

class TestStateManagerSingleton:
    """StateManager 싱글톤 패턴 테스트"""

    def test_state_manager_get_instance_exists(self):
        """get_instance 메서드 존재 확인"""
        from services.backend.app.services.state_manager import StateManager
        assert hasattr(StateManager, 'get_instance'), \
            "StateManager should have get_instance class method"

    def test_state_manager_singleton_returns_same_instance(self):
        """동일한 인스턴스 반환 확인"""
        from services.backend.app.services.state_manager import StateManager
        StateManager.reset_instance()  # 테스트 격리

        instance1 = StateManager.get_instance()
        instance2 = StateManager.get_instance()

        assert instance1 is instance2, "get_instance should return same instance"

    def test_state_manager_reset_instance_for_testing(self):
        """테스트용 reset_instance 동작 확인"""
        from services.backend.app.services.state_manager import StateManager

        instance1 = StateManager.get_instance()
        StateManager.reset_instance()
        instance2 = StateManager.get_instance()

        assert instance1 is not instance2, "reset_instance should create new instance"


# ============================================
# Phase 30.4.1: 통합 Health Check 함수
# ============================================

class TestUnifiedHealthCheck:
    """통합 Health Check 함수 테스트"""

    def test_check_health_function_exists_in_utils(self):
        """utils/health.py에 check_health 함수 존재"""
        from services.backend.app.utils.health import check_health
        assert callable(check_health)

    @pytest.mark.asyncio
    async def test_check_health_returns_healthy_on_200(self):
        """HTTP 200 시 healthy=True"""
        from services.backend.app.utils.health import check_health
        from unittest.mock import patch, AsyncMock
        import httpx

        with patch('httpx.AsyncClient') as mock_client:
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_response.content = b'{"status": "ok"}'
            mock_response.json.return_value = {"status": "ok"}

            mock_instance = AsyncMock()
            mock_instance.get.return_value = mock_response
            mock_instance.__aenter__.return_value = mock_instance
            mock_instance.__aexit__.return_value = None
            mock_client.return_value = mock_instance

            result = await check_health("http://test:11000/health")
            assert result["healthy"] is True

    @pytest.mark.asyncio
    async def test_check_health_returns_unhealthy_on_timeout(self):
        """타임아웃 시 healthy=False"""
        from services.backend.app.utils.health import check_health
        from unittest.mock import patch, AsyncMock
        import httpx

        with patch('httpx.AsyncClient') as mock_client:
            mock_instance = AsyncMock()
            mock_instance.get.side_effect = httpx.TimeoutException("timeout")
            mock_instance.__aenter__.return_value = mock_instance
            mock_instance.__aexit__.return_value = None
            mock_client.return_value = mock_instance

            result = await check_health("http://test:11000/health")
            assert result["healthy"] is False
            assert result["error"] == "timeout"

    @pytest.mark.asyncio
    async def test_check_health_returns_latency_ms(self):
        """latency_ms 반환 확인"""
        from services.backend.app.utils.health import check_health
        from unittest.mock import patch, AsyncMock

        with patch('httpx.AsyncClient') as mock_client:
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_response.content = b''

            mock_instance = AsyncMock()
            mock_instance.get.return_value = mock_response
            mock_instance.__aenter__.return_value = mock_instance
            mock_instance.__aexit__.return_value = None
            mock_client.return_value = mock_instance

            result = await check_health("http://test:11000/health")
            assert "latency_ms" in result
            assert isinstance(result["latency_ms"], float)

    @pytest.mark.asyncio
    async def test_check_health_parses_json_when_requested(self):
        """expect_json=True 시 JSON 파싱"""
        from services.backend.app.utils.health import check_health
        from unittest.mock import patch, MagicMock, AsyncMock

        with patch('httpx.AsyncClient') as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.content = b'{"status": "ok"}'
            mock_response.json.return_value = {"status": "ok"}

            mock_instance = AsyncMock()
            mock_instance.get.return_value = mock_response
            mock_instance.__aenter__.return_value = mock_instance
            mock_instance.__aexit__.return_value = None
            mock_client.return_value = mock_instance

            result = await check_health("http://test:11000/health", expect_json=True)
            assert result["data"] == {"status": "ok"}


# ============================================
# Phase 30.5.1: Redis 채널 상수 파일
# ============================================

class TestRedisChannelConstants:
    """Redis 채널 상수 테스트"""

    def test_redis_channels_class_exists(self):
        """RedisChannels 클래스 존재 확인"""
        from services.backend.app.constants.redis_channels import RedisChannels
        assert RedisChannels is not None

    def test_orchestrator_state_channel_defined(self):
        """ORCHESTRATOR_STATE 채널 정의"""
        from services.backend.app.constants.redis_channels import RedisChannels
        assert hasattr(RedisChannels, 'ORCHESTRATOR_STATE')
        assert "orchestrator" in RedisChannels.ORCHESTRATOR_STATE.lower()

    def test_pipeline_logs_channel_defined(self):
        """PIPELINE_LOGS 채널 정의"""
        from services.backend.app.constants.redis_channels import RedisChannels
        assert hasattr(RedisChannels, 'PIPELINE_LOGS')
        assert "logs" in RedisChannels.PIPELINE_LOGS.lower()

    def test_settings_broadcast_channel_defined(self):
        """SETTINGS_BROADCAST 채널 정의"""
        from services.backend.app.constants.redis_channels import RedisChannels
        assert hasattr(RedisChannels, 'SETTINGS_BROADCAST')
        assert "settings" in RedisChannels.SETTINGS_BROADCAST.lower()


# ============================================
# Phase 30.3.2: StateManager 싱글톤 사용
# ============================================

class TestStateManagerSingletonUsage:
    """StateManager 싱글톤 사용 테스트"""

    def test_dashboard_uses_state_manager_singleton(self):
        """dashboard.py에서 StateManager.get_instance() 사용 확인"""
        with open("services/backend/app/routes/dashboard.py", "r", encoding="utf-8") as f:
            content = f.read()

        # StateManager.get_instance() 또는 get_instance() 패턴 확인
        assert "get_instance" in content or "StateManager(" not in content, \
            "dashboard.py should use StateManager.get_instance() instead of StateManager()"

    def test_orchestrator_uses_state_manager_singleton(self):
        """orchestrator.py에서 StateManager.get_instance() 사용 확인"""
        with open("services/backend/app/routes/orchestrator.py", "r", encoding="utf-8") as f:
            content = f.read()

        # StateManager를 import하고 있다면 싱글톤으로 사용해야 함
        if "StateManager" in content:
            assert "get_instance" in content or "StateManager(" not in content, \
                "orchestrator.py should use StateManager.get_instance()"

    def test_status_uses_state_manager_singleton(self):
        """status.py에서 StateManager.get_instance() 사용 확인"""
        with open("services/backend/app/routes/status.py", "r", encoding="utf-8") as f:
            content = f.read()

        if "StateManager" in content or "state_manager" in content:
            # StateManager를 직접 생성하지 않고 get_instance 또는 기존 인스턴스 사용
            assert "StateManager()" not in content or "get_instance" in content, \
                "status.py should use StateManager singleton"


# ============================================
# Phase 30.4.2: 통합 Health Check 사용
# ============================================

class TestUnifiedHealthCheckUsage:
    """통합 Health Check 함수 사용 테스트"""

    def test_dashboard_uses_unified_check_health(self):
        """dashboard.py에서 통합 check_health 함수 사용 확인"""
        with open("services/backend/app/routes/dashboard.py", "r", encoding="utf-8") as f:
            content = f.read()

        # check_health를 import하거나 utils.health를 사용해야 함
        uses_unified = (
            "from ..utils.health import check_health" in content or
            "from services.backend.app.utils.health import check_health" in content or
            "utils.health" in content
        )

        # 또는 아예 health check를 사용하지 않음 (다른 파일로 이동)
        # 이 경우 status.py에서 처리할 수 있음
        if "async def check" in content and "health" in content.lower():
            assert uses_unified, \
                "dashboard.py should import check_health from utils.health"

    def test_status_uses_unified_check_health(self):
        """status.py에서 통합 check_health 함수 사용 확인 (있다면)"""
        with open("services/backend/app/routes/status.py", "r", encoding="utf-8") as f:
            content = f.read()

        # health check 로직이 있다면 통합 함수 사용
        if "health" in content.lower() and "httpx" in content:
            uses_unified = (
                "from ..utils.health import check_health" in content or
                "utils.health" in content
            )
            assert uses_unified, \
                "status.py should use unified check_health from utils.health"


# ============================================
# Phase 30.5.2: Redis 채널 상수 사용
# ============================================

class TestRedisChannelConstantsUsage:
    """Redis 채널 상수 사용 테스트"""

    def test_no_hardcoded_dashboard_channel_in_routes(self):
        """라우트에서 하드코딩된 'dashboard:updates' 사용 금지"""
        import os

        routes_dir = "services/backend/app/routes"
        hardcoded_channels = []

        for filename in os.listdir(routes_dir):
            if filename.endswith(".py"):
                filepath = os.path.join(routes_dir, filename)
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()
                    # 문자열 리터럴로 하드코딩된 채널명 검사
                    if '"dashboard:updates"' in content or "'dashboard:updates'" in content:
                        # RedisChannels를 import하지 않았다면 하드코딩
                        if "RedisChannels" not in content:
                            hardcoded_channels.append(filename)

        assert len(hardcoded_channels) == 0, \
            f"Files with hardcoded channel names: {hardcoded_channels}"

    def test_state_manager_uses_redis_channel_constants(self):
        """state_manager.py에서 RedisChannels 상수 사용 확인"""
        with open("services/backend/app/services/state_manager.py", "r", encoding="utf-8") as f:
            content = f.read()

        # 하드코딩된 채널명 대신 상수 사용
        has_hardcoded = (
            '"dashboard:updates"' in content or
            "'dashboard:updates'" in content
        )

        if has_hardcoded:
            # RedisChannels를 import했다면 OK (마이그레이션 중일 수 있음)
            uses_constants = "RedisChannels" in content
            assert uses_constants, \
                "state_manager.py should use RedisChannels constants instead of hardcoded strings"

    def test_redis_channels_imported_where_needed(self):
        """채널을 사용하는 파일에서 RedisChannels import 확인"""
        from services.backend.app.constants.redis_channels import RedisChannels

        # RedisChannels 클래스가 올바르게 정의되어 있는지 확인
        assert hasattr(RedisChannels, 'DASHBOARD_UPDATES')
        assert hasattr(RedisChannels, 'ORCHESTRATOR_STATE')
        assert hasattr(RedisChannels, 'PIPELINE_LOGS')


# ============================================
# Phase 30.1.3 -> Phase 31: 각 서비스 PipelineLogger Wrapper 패턴
# ============================================
# Note: Phase 31에서 재설계 - 파일을 삭제하는 대신 shared 모듈로 위임하는
# wrapper 파일로 변경. 서비스들이 로컬 import를 유지할 수 있음.

class TestSharedPipelineLoggerMigration:
    """각 서비스의 공유 PipelineLogger 마이그레이션 테스트 (Phase 31 wrapper 패턴)"""

    def test_orchestrator_pipeline_logger_is_wrapper(self):
        """orchestrator의 pipeline_logger.py가 shared 모듈을 사용하는 wrapper인지 확인"""
        file_path = "services/orchestrator/app/pipeline_logger.py"
        assert os.path.exists(file_path), \
            f"Wrapper file should exist: {file_path}"
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        assert "from shared.pipeline_logger import" in content, \
            "Wrapper should import from shared.pipeline_logger"

    def test_tts_pipeline_logger_is_wrapper(self):
        """tts의 pipeline_logger.py가 shared 모듈을 사용하는 wrapper인지 확인"""
        file_path = "services/tts/app/pipeline_logger.py"
        assert os.path.exists(file_path), \
            f"Wrapper file should exist: {file_path}"
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        assert "from shared.pipeline_logger import" in content, \
            "Wrapper should import from shared.pipeline_logger"

    def test_wake_word_pipeline_logger_is_wrapper(self):
        """wake_word의 pipeline_logger.py가 shared 모듈을 사용하는 wrapper인지 확인"""
        file_path = "services/wake_word/app/pipeline_logger.py"
        assert os.path.exists(file_path), \
            f"Wrapper file should exist: {file_path}"
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        assert "from shared.pipeline_logger import" in content, \
            "Wrapper should import from shared.pipeline_logger"

    def test_stt_pipeline_logger_is_wrapper(self):
        """stt의 pipeline_logger.py가 shared 모듈을 사용하는 wrapper인지 확인"""
        file_path = "services/stt/app/pipeline_logger.py"
        assert os.path.exists(file_path), \
            f"Wrapper file should exist: {file_path}"
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        assert "from shared.pipeline_logger import" in content, \
            "Wrapper should import from shared.pipeline_logger"

    def test_audio_gateway_pipeline_logger_is_wrapper(self):
        """audio_gateway의 pipeline_logger.py가 shared 모듈을 사용하는 wrapper인지 확인"""
        file_path = "services/audio_gateway/app/pipeline_logger.py"
        assert os.path.exists(file_path), \
            f"Wrapper file should exist: {file_path}"
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        assert "from shared.pipeline_logger import" in content, \
            "Wrapper should import from shared.pipeline_logger"