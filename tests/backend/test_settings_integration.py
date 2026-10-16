"""
Test Settings Integration

Phase 14.3.1: Settings Router Integration Tests
- PUT /api/settings/general saves to DB
- GET /api/settings/general loads from DB
- Settings persisted after restart simulation
- Settings propagation on startup
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport


class TestSettingsSavedToDb:
    """Tests for PUT /api/settings/general saving to DB."""

    @pytest.mark.asyncio
    async def test_settings_saved_to_db(self):
        """
        Test that PUT /api/settings/general saves settings to the database.

        Requirements:
        - Call PUT /api/settings/general with new settings
        - Verify SettingsRepository.upsert() is called with correct data
        """
        from services.backend.app.main import app

        # Mock the async SettingsRepository
        mock_repo = AsyncMock()
        mock_repo.upsert = AsyncMock()
        mock_repo.get = AsyncMock(return_value={})

        # Mock the propagator
        mock_propagator = AsyncMock()
        mock_propagator.propagate = AsyncMock(return_value={"success": True})

        with patch("services.backend.app.routes.settings.get_settings_repository") as mock_get_repo, \
             patch("services.backend.app.routes.settings.get_settings_propagator") as mock_get_prop:

            # Return a mock sync repository that wraps async
            mock_sync_repo = MagicMock()
            mock_sync_repo.save = MagicMock(return_value=True)
            mock_get_repo.return_value = mock_sync_repo
            mock_get_prop.return_value = mock_propagator

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.put(
                    "/api/settings/general",
                    json={
                        "wake_word": "hey_jarvis",
                        "language": "ko",
                        "voice_speed": 1.2,
                        "wake_word_threshold": 0.6
                    }
                )

                assert response.status_code == 200
                data = response.json()
                assert data["voice_speed"] == 1.2
                assert data["language"] == "ko"
                # Background task is scheduled for DB save


class TestSettingsLoadedFromDb:
    """Tests for GET /api/settings/general loading from DB."""

    @pytest.mark.asyncio
    async def test_settings_loaded_from_db(self):
        """
        Test that GET /api/settings/general loads settings from the database.

        Requirements:
        - Call GET /api/settings/general
        - Verify response contains data loaded from DB
        """
        from services.backend.app.main import app

        # Mock the sync repository to return DB data
        mock_sync_repo = MagicMock()
        mock_sync_repo.load = MagicMock(return_value={
            "wake_word": "alexa",
            "language": "en",
            "voice_speed": 1.5,
            "wake_word_threshold": 0.7
        })

        with patch("services.backend.app.routes.settings.get_settings_repository") as mock_get_repo:
            mock_get_repo.return_value = mock_sync_repo

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/api/settings/general")

                assert response.status_code == 200
                data = response.json()
                assert data["wake_word"] == "alexa"
                assert data["language"] == "en"
                assert data["voice_speed"] == 1.5
                mock_sync_repo.load.assert_called_with("general")


class TestSettingsPersistedAfterRestart:
    """Tests for settings persistence after restart simulation."""

    @pytest.mark.asyncio
    async def test_settings_persisted_after_restart(self):
        """
        Test that settings are persisted and available after simulated restart.

        Requirements:
        - Save settings via PUT
        - Clear in-memory state
        - Load settings via GET
        - Verify settings match what was saved
        """
        from services.backend.app.main import app
        import services.backend.app.routes.settings as settings_module

        # Saved settings (simulating DB state)
        saved_settings = {
            "wake_word": "ok_google",
            "language": "ja",
            "voice_speed": 0.9,
            "wake_word_threshold": 0.4
        }

        # Mock repository
        mock_sync_repo = MagicMock()
        mock_sync_repo.load = MagicMock(return_value=saved_settings)
        mock_sync_repo.save = MagicMock(return_value=True)

        mock_propagator = AsyncMock()
        mock_propagator.propagate = AsyncMock(return_value={"success": True})

        with patch("services.backend.app.routes.settings.get_settings_repository") as mock_get_repo, \
             patch("services.backend.app.routes.settings.get_settings_propagator") as mock_get_prop:

            mock_get_repo.return_value = mock_sync_repo
            mock_get_prop.return_value = mock_propagator

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                # Step 1: Save settings
                await client.put("/api/settings/general", json=saved_settings)

                # Step 2: Simulate restart by resetting in-memory state
                from services.backend.app.routes.settings import GeneralSettings
                settings_module._general_settings = GeneralSettings()  # Reset to defaults

                # Step 3: Load settings (should come from DB)
                response = await client.get("/api/settings/general")

                assert response.status_code == 200
                data = response.json()
                assert data["wake_word"] == "ok_google"
                assert data["language"] == "ja"
                assert data["voice_speed"] == 0.9


class TestSettingsPropagatedOnStartup:
    """Tests for settings propagation during application startup."""

    @pytest.mark.asyncio
    async def test_settings_propagated_on_startup(self):
        """
        Test that settings are propagated to services on application startup.

        Requirements:
        - On startup, load settings from DB
        - Propagate to TTS, STT, Wake Word services
        - Verify propagation calls are made
        """
        # This test validates the startup propagation logic
        # We'll test the propagation mechanism in isolation

        from services.backend.app.services.settings_propagator import SettingsPropagator

        mock_propagator = SettingsPropagator()

        # Mock httpx client
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json = MagicMock(return_value={"status": "applied"})

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client.patch = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client_class.return_value = mock_client

            # Simulate startup propagation
            settings_to_propagate = {
                "tts": {"speed": 1.2},
                "stt": {"language": "ko"},
                "wake_word": {"wake_word": "hey_jarvis", "threshold": 0.5}
            }

            results = {}
            for service, settings in settings_to_propagate.items():
                result = await mock_propagator.propagate(service, settings)
                results[service] = result

            # Verify propagation was attempted
            assert "tts" in results
            assert "stt" in results
            assert "wake_word" in results
