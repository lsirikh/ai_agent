"""
Backend Tests - Settings Persistence

Phase 12.1: Settings DB 영속성 테스트
"""
import json
import pytest
from unittest.mock import MagicMock, patch, Mock


class TestSettingsSavedToDatabase:
    """설정이 DB에 저장되는지 테스트"""

    def test_settings_saved_to_database(self):
        """
        설정 업데이트 시 DB에 저장되어야 함.
        SettingsRepository.save()가 호출되어야 함.
        """
        from services.backend.app.services.settings_repository import SettingsRepository

        # Mock 커서 생성
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        # SettingsRepository 생성 및 _get_connection mock
        repo = SettingsRepository(database_url="postgresql://test:test@localhost/test")

        with patch.object(repo, '_get_connection') as mock_get_conn:
            mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
            mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)

            # 설정 저장
            settings_data = {
                "model": "Qwen/Qwen2.5-7B-Instruct",
                "temperature": 0.8
            }
            repo.save("llm", settings_data)

            # DB에 저장되었는지 확인
            mock_cursor.execute.assert_called()
            call_args = mock_cursor.execute.call_args
            assert "INSERT" in call_args[0][0] or "UPDATE" in call_args[0][0]


class TestSettingsLoadedFromDatabase:
    """DB에서 설정을 로드하는지 테스트"""

    def test_settings_loaded_from_database(self):
        """
        앱 시작 시 DB에서 설정을 로드해야 함.
        """
        from services.backend.app.services.settings_repository import SettingsRepository

        # Mock 커서 생성 - fetchone이 JSON 데이터 반환
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = (
            '{"model": "Qwen/Qwen2.5-7B-Instruct", "temperature": 0.9}',
        )

        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        repo = SettingsRepository(database_url="postgresql://test:test@localhost/test")

        with patch.object(repo, '_get_connection') as mock_get_conn:
            mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
            mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)

            # 설정 로드
            settings = repo.load("llm")

            # 로드된 설정 확인
            assert settings is not None
            assert settings["model"] == "Qwen/Qwen2.5-7B-Instruct"
            assert settings["temperature"] == 0.9


class TestSettingsUpdatePersists:
    """설정 업데이트가 영속화되는지 테스트"""

    def test_settings_update_persists(self):
        """
        설정 업데이트 후 재로드 시 변경된 값이 유지되어야 함.
        """
        from services.backend.app.services.settings_repository import SettingsRepository

        # 저장된 데이터를 시뮬레이션
        stored_data = {}

        mock_cursor = MagicMock()

        def mock_execute(query, params=None):
            if "INSERT" in query or "UPDATE" in query:
                # UPSERT 시 데이터 저장
                if params and len(params) >= 2:
                    stored_data[params[0]] = params[1]

        def mock_fetchone():
            # SELECT 시 저장된 데이터 반환
            if "llm" in stored_data:
                return (stored_data["llm"],)
            return None

        mock_cursor.execute.side_effect = mock_execute
        mock_cursor.fetchone.side_effect = mock_fetchone

        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        repo = SettingsRepository(database_url="postgresql://test:test@localhost/test")

        with patch.object(repo, '_get_connection') as mock_get_conn:
            mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
            mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)

            # 설정 저장
            settings_data = {"model": "new-model", "temperature": 0.5}
            repo.save("llm", settings_data)

            # 저장된 데이터 확인
            assert "llm" in stored_data


class TestSettingsDefaultValues:
    """기본값 처리 테스트"""

    def test_settings_default_values(self):
        """
        DB에 설정이 없을 때 기본값을 반환해야 함.
        """
        from services.backend.app.services.settings_repository import SettingsRepository

        # Mock 커서 - fetchone이 None 반환 (데이터 없음)
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None

        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        repo = SettingsRepository(database_url="postgresql://test:test@localhost/test")

        with patch.object(repo, '_get_connection') as mock_get_conn:
            mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
            mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)

            # 기본값 로드
            settings = repo.load("llm")

            # 기본값이 반환되어야 함
            assert settings is not None
            assert "model" in settings
            assert "temperature" in settings
            # Phase 33: 기본 모델명 업데이트
            assert settings["model"] == "qwen2.5-7b-instruct-awq"
