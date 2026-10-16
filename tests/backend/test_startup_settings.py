"""
Backend API - Startup Settings Tests

Phase 16: 서버 시작 시 설정 로드 및 전파 테스트
"""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch


class TestSettingsLoaderHelper:
    """Phase 16.1: 설정 로드 헬퍼 함수 테스트"""

    @pytest.mark.asyncio
    async def test_load_all_settings_from_db_loads_llm(self):
        """load_all_settings_from_db가 LLM 설정을 로드해야 한다"""
        from services.backend.app.routes import settings as settings_module

        # Mock repository
        mock_repo = MagicMock()
        mock_repo.load = MagicMock(side_effect=lambda key: {
            "llm": {"model": "test-model", "temperature": 0.5},
            "tts": {},
            "stt": {},
            "audio": {},
            "general": {},
            "llm_context": {}
        }.get(key, {}))

        with patch.object(settings_module, 'get_settings_repository', return_value=mock_repo):
            await settings_module.load_all_settings_from_db()

            # LLM 설정이 로드되었는지 확인
            assert settings_module._current_settings.llm.model == "test-model"
            assert settings_module._current_settings.llm.temperature == 0.5

    @pytest.mark.asyncio
    async def test_load_all_settings_from_db_loads_llm_context(self):
        """load_all_settings_from_db가 LLM Context 설정을 로드해야 한다"""
        from services.backend.app.routes import settings as settings_module

        # Mock repository
        mock_repo = MagicMock()
        mock_repo.load = MagicMock(side_effect=lambda key: {
            "llm": {},
            "tts": {},
            "stt": {},
            "audio": {},
            "general": {},
            "llm_context": {"context_enabled": False, "context_window_size": 30}
        }.get(key, {}))

        with patch.object(settings_module, 'get_settings_repository', return_value=mock_repo):
            await settings_module.load_all_settings_from_db()

            # LLM Context 설정이 로드되었는지 확인
            assert settings_module._llm_context_settings.context_enabled is False
            assert settings_module._llm_context_settings.context_window_size == 30

    @pytest.mark.asyncio
    async def test_load_all_settings_from_db_loads_general(self):
        """load_all_settings_from_db가 General 설정을 로드해야 한다"""
        from services.backend.app.routes import settings as settings_module

        # Mock repository
        mock_repo = MagicMock()
        mock_repo.load = MagicMock(side_effect=lambda key: {
            "llm": {},
            "tts": {},
            "stt": {},
            "audio": {},
            "general": {"wake_word": "alexa", "language": "en"},
            "llm_context": {}
        }.get(key, {}))

        with patch.object(settings_module, 'get_settings_repository', return_value=mock_repo):
            await settings_module.load_all_settings_from_db()

            # General 설정이 로드되었는지 확인
            assert settings_module._general_settings.wake_word == "alexa"
            assert settings_module._general_settings.language == "en"

    @pytest.mark.asyncio
    async def test_load_all_settings_from_db_handles_empty_db(self):
        """DB에 설정이 없으면 기본값을 유지해야 한다"""
        from services.backend.app.routes import settings as settings_module

        # Mock repository - 모든 설정이 빈 dict 반환
        mock_repo = MagicMock()
        mock_repo.load = MagicMock(return_value={})

        # 기본값 저장
        default_model = settings_module._current_settings.llm.model

        with patch.object(settings_module, 'get_settings_repository', return_value=mock_repo):
            await settings_module.load_all_settings_from_db()

            # 기본값이 유지되어야 함
            assert settings_module._current_settings.llm.model == default_model

    @pytest.mark.asyncio
    async def test_load_all_settings_from_db_handles_db_error(self):
        """DB 오류 시 예외 없이 기본값을 유지해야 한다"""
        from services.backend.app.routes import settings as settings_module

        # Mock repository - 예외 발생
        mock_repo = MagicMock()
        mock_repo.load = MagicMock(side_effect=Exception("DB connection failed"))

        # 기본값 저장
        default_model = settings_module._current_settings.llm.model

        with patch.object(settings_module, 'get_settings_repository', return_value=mock_repo):
            # 예외 없이 실행되어야 함
            await settings_module.load_all_settings_from_db()

            # 기본값이 유지되어야 함
            assert settings_module._current_settings.llm.model == default_model


class TestWakeWordServiceUrl:
    """Phase 16.2: wake_word SERVICE_URL 테스트"""

    def test_service_urls_contains_wake_word(self):
        """SERVICE_URLS에 wake_word가 포함되어야 한다"""
        from services.backend.app.services.settings_propagator import SERVICE_URLS

        assert "wake_word" in SERVICE_URLS
        assert SERVICE_URLS["wake_word"] is not None

    def test_propagator_can_propagate_to_wake_word(self):
        """SettingsPropagator가 wake_word에 전파할 수 있어야 한다"""
        from services.backend.app.services.settings_propagator import SettingsPropagator, SERVICE_URLS

        propagator = SettingsPropagator()

        # wake_word URL이 존재하면 전파 시도 가능
        assert "wake_word" in SERVICE_URLS


class TestStartupSettingsLoading:
    """Phase 16.3: 시작 시 설정 로드 테스트"""

    @pytest.mark.asyncio
    async def test_lifespan_calls_load_all_settings(self):
        """lifespan이 load_all_settings_from_db를 호출해야 한다"""
        from services.backend.app import main as main_module

        # Mock DB manager
        mock_db = MagicMock()
        mock_db.connect = AsyncMock()
        mock_db.disconnect = AsyncMock()
        mock_db.is_connected = True
        mock_db.health_check = AsyncMock(return_value=True)

        # Mock load_all_settings_from_db - main 모듈에서 직접 패치
        mock_load = AsyncMock()

        with patch.object(main_module, 'get_db_manager', return_value=mock_db):
            with patch.object(main_module, 'load_all_settings_from_db', mock_load):
                with patch.object(main_module, 'propagate_all_settings_to_services', AsyncMock()):
                    # lifespan 컨텍스트 매니저 실행
                    async with main_module.lifespan(main_module.app):
                        pass

                    # load_all_settings_from_db가 호출되었는지 확인
                    mock_load.assert_called_once()


class TestStartupSettingsPropagation:
    """Phase 16.4: 시작 시 설정 전파 테스트"""

    @pytest.mark.asyncio
    async def test_lifespan_calls_propagate_all_settings(self):
        """lifespan이 propagate_all_settings를 호출해야 한다"""
        from services.backend.app import main as main_module

        # Mock DB manager
        mock_db = MagicMock()
        mock_db.connect = AsyncMock()
        mock_db.disconnect = AsyncMock()
        mock_db.is_connected = True
        mock_db.health_check = AsyncMock(return_value=True)

        # Mock functions - main 모듈에서 직접 패치
        mock_load = AsyncMock()
        mock_propagate = AsyncMock()

        with patch.object(main_module, 'get_db_manager', return_value=mock_db):
            with patch.object(main_module, 'load_all_settings_from_db', mock_load):
                with patch.object(main_module, 'propagate_all_settings_to_services', mock_propagate):
                    async with main_module.lifespan(main_module.app):
                        pass

                    # propagate_all_settings_to_services가 호출되었는지 확인
                    mock_propagate.assert_called_once()

    @pytest.mark.asyncio
    async def test_propagate_all_settings_propagates_to_tts(self):
        """propagate_all_settings_to_services가 TTS에 전파해야 한다"""
        from services.backend.app.routes import settings as settings_module

        # Mock propagator
        mock_propagator = MagicMock()
        mock_propagator.propagate = AsyncMock(return_value={"success": True})

        with patch('services.backend.app.routes.settings.get_settings_propagator', return_value=mock_propagator):
            await settings_module.propagate_all_settings_to_services()

            # TTS 전파 확인
            calls = mock_propagator.propagate.call_args_list
            tts_calls = [c for c in calls if c[0][0] == "tts"]
            assert len(tts_calls) >= 1

    @pytest.mark.asyncio
    async def test_propagate_all_settings_handles_failure_gracefully(self):
        """전파 실패 시 예외 없이 처리해야 한다"""
        from services.backend.app.routes import settings as settings_module

        # Mock propagator - 예외 발생
        mock_propagator = MagicMock()
        mock_propagator.propagate = AsyncMock(side_effect=Exception("Connection refused"))

        with patch('services.backend.app.routes.settings.get_settings_propagator', return_value=mock_propagator):
            # 예외 없이 실행되어야 함
            await settings_module.propagate_all_settings_to_services()
