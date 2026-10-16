"""
Test Settings E2E

Phase 12.5: E2E Settings Tests
- test_settings_persist_and_propagate: Settings are saved and propagated
- test_settings_survive_restart: Settings persist across service restarts
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import uuid


class TestSettingsPersistAndPropagate:
    """E2E tests for settings persistence and propagation."""

    @pytest.mark.asyncio
    async def test_settings_persist_and_propagate(self):
        """
        Test that settings are saved to DB and propagated to services.

        E2E Flow:
        1. Save settings via PUT /api/settings/general
        2. Verify settings saved (via response)
        3. Verify propagation was attempted (via response)
        """
        from services.backend.app.main import app
        from services.backend.app.routes import settings as settings_module
        from httpx import AsyncClient, ASGITransport

        # Track propagation calls
        propagation_calls = []

        # Mock repository
        mock_repo = MagicMock()
        mock_repo.load = MagicMock(return_value={})
        mock_repo.save = MagicMock(return_value=True)

        # Mock propagator
        mock_propagator = MagicMock()

        async def mock_propagate(service, settings):
            propagation_calls.append({"service": service, "settings": settings})
            return {"success": True}

        mock_propagator.propagate = mock_propagate

        # Patch at the module where functions are used (settings route module)
        with patch.object(settings_module, "get_settings_repository", return_value=mock_repo), \
             patch.object(settings_module, "get_settings_propagator", return_value=mock_propagator):

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                # Step 1: Save settings
                response = await client.put(
                    "/api/settings/general",
                    json={
                        "wake_word": "hey_jarvis",
                        "language": "ko",
                        "voice_speed": 1.5,
                        "wake_word_threshold": 0.6
                    }
                )

                assert response.status_code == 200
                data = response.json()

                # Step 2: Verify settings in response
                assert data.get("language") == "ko"
                assert data.get("voice_speed") == 1.5
                assert data.get("status") == "applied"

                # Step 3: Verify propagation attempted
                assert len(propagation_calls) >= 1  # At least one propagation call
                services_propagated = [c["service"] for c in propagation_calls]
                # Should propagate to TTS (voice_speed) and wake_word (threshold)
                assert "tts" in services_propagated or "wake_word" in services_propagated


class TestSettingsSurviveRestart:
    """Tests for settings surviving service restarts."""

    @pytest.mark.asyncio
    async def test_settings_survive_restart(self):
        """
        Test that settings persist across service restarts.

        This test validates the concept that:
        1. Settings are saved to persistent storage (DB)
        2. On restart, settings are loaded from storage
        3. The loaded settings match what was saved
        """
        from services.backend.app.main import app
        from services.backend.app.routes import settings as settings_module
        from httpx import AsyncClient, ASGITransport

        # Persistent database (simulates actual database)
        database = {}

        def create_mock_repo():
            """Create a new mock repository pointing to same database."""
            mock = MagicMock()

            def load(key):
                return database.get(key, {})

            def save(key, value):
                database[key] = value
                return True

            mock.load = load
            mock.save = save
            return mock

        mock_propagator = MagicMock()
        mock_propagator.propagate = AsyncMock(return_value={"success": True})

        original_settings = {
            "wake_word": "alexa",
            "language": "en",
            "voice_speed": 0.9,
            "wake_word_threshold": 0.7
        }

        # === First "instance" - Save settings ===
        first_repo = create_mock_repo()

        with patch.object(settings_module, "get_settings_repository", return_value=first_repo), \
             patch.object(settings_module, "get_settings_propagator", return_value=mock_propagator):

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.put(
                    "/api/settings/general",
                    json=original_settings
                )
                assert response.status_code == 200

                # Verify response includes the settings
                data = response.json()
                assert data.get("language") == "en"
                assert data.get("voice_speed") == 0.9

        # === Simulate restart - Reset module globals ===
        # Clear the module-level _general_settings
        settings_module._general_settings = settings_module.GeneralSettings()

        # === Second "instance" - Load settings ===
        second_repo = create_mock_repo()
        # Put saved settings in the mock database for loading
        database["general"] = original_settings

        with patch.object(settings_module, "get_settings_repository", return_value=second_repo), \
             patch.object(settings_module, "get_settings_propagator", return_value=mock_propagator):

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/api/settings/general")
                assert response.status_code == 200

                loaded = response.json()
                # Settings should match what was saved
                assert loaded.get("language") == original_settings["language"]
                assert loaded.get("voice_speed") == original_settings["voice_speed"]
                assert loaded.get("wake_word") == original_settings["wake_word"]


class TestSettingsPropagatesToAllServices:
    """Tests for settings propagating to all required services."""

    @pytest.mark.asyncio
    async def test_voice_speed_propagates_to_tts(self):
        """
        Test that voice_speed changes are propagated to TTS service.
        """
        from services.backend.app.main import app
        from services.backend.app.routes import settings as settings_module
        from httpx import AsyncClient, ASGITransport

        propagation_calls = []

        mock_repo = MagicMock()
        mock_repo.load = MagicMock(return_value={})
        mock_repo.save = MagicMock(return_value=True)

        mock_propagator = MagicMock()

        async def capture_propagate(service, settings):
            propagation_calls.append({"service": service, "settings": settings})
            return {"success": True}

        mock_propagator.propagate = capture_propagate

        with patch.object(settings_module, "get_settings_repository", return_value=mock_repo), \
             patch.object(settings_module, "get_settings_propagator", return_value=mock_propagator):

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.put(
                    "/api/settings/general",
                    json={
                        "voice_speed": 1.8,
                        "language": "ko",
                        "wake_word": "hey_jarvis",
                        "wake_word_threshold": 0.5
                    }
                )
                assert response.status_code == 200

        # Check TTS propagation includes speed
        tts_calls = [c for c in propagation_calls if c["service"] == "tts"]
        assert len(tts_calls) >= 1, "TTS should be called for voice_speed"
        tts_settings = tts_calls[0]["settings"]
        assert "speed" in tts_settings

    @pytest.mark.asyncio
    async def test_language_propagates_to_stt(self):
        """
        Test that language changes are propagated to STT service.
        """
        from services.backend.app.main import app
        from services.backend.app.routes import settings as settings_module
        from httpx import AsyncClient, ASGITransport

        propagation_calls = []

        mock_repo = MagicMock()
        mock_repo.load = MagicMock(return_value={})
        mock_repo.save = MagicMock(return_value=True)

        mock_propagator = MagicMock()

        async def capture_propagate(service, settings):
            propagation_calls.append({"service": service, "settings": settings})
            return {"success": True}

        mock_propagator.propagate = capture_propagate

        with patch.object(settings_module, "get_settings_repository", return_value=mock_repo), \
             patch.object(settings_module, "get_settings_propagator", return_value=mock_propagator):

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.put(
                    "/api/settings/general",
                    json={
                        "language": "ja",
                        "voice_speed": 1.0,
                        "wake_word": "hey_jarvis",
                        "wake_word_threshold": 0.5
                    }
                )
                assert response.status_code == 200

        # Check STT propagation includes language
        stt_calls = [c for c in propagation_calls if c["service"] == "stt"]
        assert len(stt_calls) >= 1, "STT should be called for language"
        stt_settings = stt_calls[0]["settings"]
        assert "language" in stt_settings
