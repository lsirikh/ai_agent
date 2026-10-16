"""
Test Settings Repository

Phase 14.2.2: Settings Repository Tests
- CRUD operations for settings table
- JSONB value storage
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import json


class TestSettingsRepoGetReturnsValue:
    """Tests for SettingsRepository.get() method."""

    @pytest.mark.asyncio
    async def test_settings_repo_get_returns_value(self):
        """
        Test that get() returns the value for an existing key.

        Requirements:
        - Query settings table by key
        - Return the JSONB value as dict
        """
        from services.backend.app.repositories.settings_repository import SettingsRepository

        # Mock connection and result
        mock_row = {
            "key": "general",
            "value": {"language": "ko", "voice_speed": 1.0},
            "category": "system"
        }

        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value=mock_row)

        mock_pool = MagicMock()
        mock_acquire_ctx = AsyncMock()
        mock_acquire_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_acquire_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_pool.acquire = MagicMock(return_value=mock_acquire_ctx)

        from services.backend.app.database import get_db_manager
        with patch.object(get_db_manager(), '_pool', mock_pool):
            repo = SettingsRepository()
            result = await repo.get("general")

            assert result == {"language": "ko", "voice_speed": 1.0}
            mock_conn.fetchrow.assert_called_once()


class TestSettingsRepoGetReturnsEmptyForMissing:
    """Tests for SettingsRepository.get() with missing key."""

    @pytest.mark.asyncio
    async def test_settings_repo_get_returns_empty_for_missing(self):
        """
        Test that get() returns empty dict for non-existent key.

        Requirements:
        - Return {} when key not found
        - Do not raise exception
        """
        from services.backend.app.repositories.settings_repository import SettingsRepository

        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value=None)  # No row found

        mock_pool = MagicMock()
        mock_acquire_ctx = AsyncMock()
        mock_acquire_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_acquire_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_pool.acquire = MagicMock(return_value=mock_acquire_ctx)

        from services.backend.app.database import get_db_manager
        with patch.object(get_db_manager(), '_pool', mock_pool):
            repo = SettingsRepository()
            result = await repo.get("non_existent_key")

            assert result == {}


class TestSettingsRepoUpsertCreatesNew:
    """Tests for SettingsRepository.upsert() creating new settings."""

    @pytest.mark.asyncio
    async def test_settings_repo_upsert_creates_new(self):
        """
        Test that upsert() creates a new setting if key doesn't exist.

        Requirements:
        - INSERT ... ON CONFLICT DO UPDATE
        - Store value as JSONB
        """
        from services.backend.app.repositories.settings_repository import SettingsRepository

        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock(return_value="INSERT 0 1")

        mock_pool = MagicMock()
        mock_acquire_ctx = AsyncMock()
        mock_acquire_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_acquire_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_pool.acquire = MagicMock(return_value=mock_acquire_ctx)

        from services.backend.app.database import get_db_manager
        with patch.object(get_db_manager(), '_pool', mock_pool):
            repo = SettingsRepository()
            await repo.upsert("llm", {"model": "qwen2.5-72b", "temperature": 0.7})

            mock_conn.execute.assert_called_once()
            # Verify the SQL contains INSERT and ON CONFLICT
            call_args = mock_conn.execute.call_args
            sql = call_args[0][0]
            assert "INSERT" in sql.upper()
            assert "ON CONFLICT" in sql.upper()


class TestSettingsRepoUpsertUpdatesExisting:
    """Tests for SettingsRepository.upsert() updating existing settings."""

    @pytest.mark.asyncio
    async def test_settings_repo_upsert_updates_existing(self):
        """
        Test that upsert() updates existing setting.

        Requirements:
        - ON CONFLICT DO UPDATE
        - Update updated_at timestamp
        """
        from services.backend.app.repositories.settings_repository import SettingsRepository

        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock(return_value="UPDATE 1")

        mock_pool = MagicMock()
        mock_acquire_ctx = AsyncMock()
        mock_acquire_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_acquire_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_pool.acquire = MagicMock(return_value=mock_acquire_ctx)

        from services.backend.app.database import get_db_manager
        with patch.object(get_db_manager(), '_pool', mock_pool):
            repo = SettingsRepository()
            await repo.upsert("general", {"language": "en", "voice_speed": 1.2})

            mock_conn.execute.assert_called_once()
            call_args = mock_conn.execute.call_args
            sql = call_args[0][0]
            # Verify UPDATE clause exists
            assert "DO UPDATE" in sql.upper()
            assert "updated_at" in sql.lower()


class TestSettingsRepoGetAll:
    """Tests for SettingsRepository.get_all() method."""

    @pytest.mark.asyncio
    async def test_settings_repo_get_all(self):
        """
        Test that get_all() returns all settings as a dictionary.

        Requirements:
        - Return dict with key -> value mapping
        - Include all rows from settings table
        """
        from services.backend.app.repositories.settings_repository import SettingsRepository

        mock_rows = [
            {"key": "general", "value": {"language": "ko"}, "category": "system"},
            {"key": "llm", "value": {"model": "qwen2.5"}, "category": "ai"},
            {"key": "audio", "value": {"sample_rate": 16000}, "category": "system"},
        ]

        mock_conn = AsyncMock()
        mock_conn.fetch = AsyncMock(return_value=mock_rows)

        mock_pool = MagicMock()
        mock_acquire_ctx = AsyncMock()
        mock_acquire_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_acquire_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_pool.acquire = MagicMock(return_value=mock_acquire_ctx)

        from services.backend.app.database import get_db_manager
        with patch.object(get_db_manager(), '_pool', mock_pool):
            repo = SettingsRepository()
            result = await repo.get_all()

            assert result == {
                "general": {"language": "ko"},
                "llm": {"model": "qwen2.5"},
                "audio": {"sample_rate": 16000},
            }
            mock_conn.fetch.assert_called_once()


class TestSettingsRepoDelete:
    """Tests for SettingsRepository.delete() method."""

    @pytest.mark.asyncio
    async def test_settings_repo_delete(self):
        """
        Test that delete() removes a setting by key.

        Requirements:
        - DELETE FROM settings WHERE key = $1
        - Return True if deleted, False if not found
        """
        from services.backend.app.repositories.settings_repository import SettingsRepository

        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock(return_value="DELETE 1")

        mock_pool = MagicMock()
        mock_acquire_ctx = AsyncMock()
        mock_acquire_ctx.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_acquire_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_pool.acquire = MagicMock(return_value=mock_acquire_ctx)

        from services.backend.app.database import get_db_manager
        with patch.object(get_db_manager(), '_pool', mock_pool):
            repo = SettingsRepository()
            result = await repo.delete("old_setting")

            assert result is True
            mock_conn.execute.assert_called_once()
            call_args = mock_conn.execute.call_args
            sql = call_args[0][0]
            assert "DELETE" in sql.upper()
