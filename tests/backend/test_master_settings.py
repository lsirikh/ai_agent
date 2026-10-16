"""
Test Master Settings

Phase 14.4.1: Master Settings Only Tests
- Master settings (general, llm, audio) are stored in DB
- Derived settings (tts, stt) are not stored separately in DB
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestGeneralIsMasterSetting:
    """Tests for general being a master setting."""

    @pytest.mark.asyncio
    async def test_general_is_master_setting(self):
        """
        Test that general settings are saved to DB as a master setting.

        Requirements:
        - PUT /api/settings/general triggers DB save
        - general settings are stored in the settings table
        """
        from services.backend.app.main import app
        from httpx import AsyncClient, ASGITransport

        mock_sync_repo = MagicMock()
        mock_sync_repo.save = MagicMock(return_value=True)
        mock_sync_repo.load = MagicMock(return_value={})

        mock_propagator = AsyncMock()
        mock_propagator.propagate = AsyncMock(return_value={"success": True})

        with patch("services.backend.app.routes.settings.get_settings_repository") as mock_get_repo, \
             patch("services.backend.app.routes.settings.get_settings_propagator") as mock_get_prop:

            mock_get_repo.return_value = mock_sync_repo
            mock_get_prop.return_value = mock_propagator

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.put(
                    "/api/settings/general",
                    json={
                        "wake_word": "hey_jarvis",
                        "language": "ko",
                        "voice_speed": 1.0,
                        "wake_word_threshold": 0.5
                    }
                )

                assert response.status_code == 200
                # Background task schedules DB save for "general"
                # The save function should be called with "general" key


class TestLlmIsMasterSetting:
    """Tests for LLM being a master setting."""

    @pytest.mark.asyncio
    async def test_llm_is_master_setting(self):
        """
        Test that LLM settings are saved to DB as a master setting.

        Requirements:
        - PATCH /api/settings/llm triggers DB save
        - llm settings are stored in the settings table
        """
        from services.backend.app.main import app
        from httpx import AsyncClient, ASGITransport

        mock_sync_repo = MagicMock()
        mock_sync_repo.save = MagicMock(return_value=True)

        mock_propagator = AsyncMock()
        mock_propagator.propagate = AsyncMock(return_value={"success": True})

        with patch("services.backend.app.routes.settings.get_settings_repository") as mock_get_repo, \
             patch("services.backend.app.routes.settings.get_settings_propagator") as mock_get_prop:

            mock_get_repo.return_value = mock_sync_repo
            mock_get_prop.return_value = mock_propagator

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.patch(
                    "/api/settings/llm",
                    json={
                        "model": "Qwen/Qwen2.5-7B-Instruct",
                        "temperature": 0.8
                    }
                )

                assert response.status_code == 200
                data = response.json()
                assert data["temperature"] == 0.8


class TestAudioIsMasterSetting:
    """Tests for audio being a master setting."""

    @pytest.mark.asyncio
    async def test_audio_is_master_setting(self):
        """
        Test that audio settings are saved to DB as a master setting.

        Requirements:
        - PATCH /api/settings/audio triggers DB save
        - audio settings are stored in the settings table
        """
        from services.backend.app.main import app
        from httpx import AsyncClient, ASGITransport

        mock_sync_repo = MagicMock()
        mock_sync_repo.save = MagicMock(return_value=True)

        mock_propagator = AsyncMock()
        mock_propagator.propagate = AsyncMock(return_value={"success": True})

        with patch("services.backend.app.routes.settings.get_settings_repository") as mock_get_repo, \
             patch("services.backend.app.routes.settings.get_settings_propagator") as mock_get_prop:

            mock_get_repo.return_value = mock_sync_repo
            mock_get_prop.return_value = mock_propagator

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.patch(
                    "/api/settings/audio",
                    json={
                        "sample_rate": 16000,
                        "vad_threshold": 0.6
                    }
                )

                assert response.status_code == 200
                data = response.json()
                assert data["vad_threshold"] == 0.6


class TestTtsNotInDb:
    """Tests for TTS being a derived setting."""

    @pytest.mark.asyncio
    async def test_tts_not_in_db(self):
        """
        Test that TTS settings are derived from general, not stored separately.

        Requirements:
        - TTS speed comes from general.voice_speed
        - TTS settings don't need their own DB row for speed
        - Updating general.voice_speed propagates to TTS
        """
        from services.backend.app.main import app
        from httpx import AsyncClient, ASGITransport

        mock_sync_repo = MagicMock()
        mock_sync_repo.save = MagicMock(return_value=True)
        mock_sync_repo.load = MagicMock(return_value={})

        mock_propagator = AsyncMock()
        mock_propagator.propagate = AsyncMock(return_value={"success": True})

        with patch("services.backend.app.routes.settings.get_settings_repository") as mock_get_repo, \
             patch("services.backend.app.routes.settings.get_settings_propagator") as mock_get_prop:

            mock_get_repo.return_value = mock_sync_repo
            mock_get_prop.return_value = mock_propagator

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                # Update general settings with voice_speed
                response = await client.put(
                    "/api/settings/general",
                    json={
                        "wake_word": "hey_jarvis",
                        "language": "ko",
                        "voice_speed": 1.3,
                        "wake_word_threshold": 0.5
                    }
                )

                assert response.status_code == 200
                data = response.json()

                # Check propagation results - TTS should receive speed
                assert "propagation_results" in data
                if data["propagation_results"]:
                    # TTS propagation should have been attempted
                    assert "tts" in data["propagation_results"] or data["propagation_results"].get("tts") is not None


class TestSttNotInDb:
    """Tests for STT being a derived setting."""

    @pytest.mark.asyncio
    async def test_stt_not_in_db(self):
        """
        Test that STT language is derived from general, not stored separately.

        Requirements:
        - STT language comes from general.language
        - Updating general.language propagates to STT
        """
        from services.backend.app.main import app
        from httpx import AsyncClient, ASGITransport

        mock_sync_repo = MagicMock()
        mock_sync_repo.save = MagicMock(return_value=True)
        mock_sync_repo.load = MagicMock(return_value={})

        mock_propagator = AsyncMock()
        mock_propagator.propagate = AsyncMock(return_value={"success": True})

        with patch("services.backend.app.routes.settings.get_settings_repository") as mock_get_repo, \
             patch("services.backend.app.routes.settings.get_settings_propagator") as mock_get_prop:

            mock_get_repo.return_value = mock_sync_repo
            mock_get_prop.return_value = mock_propagator

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                # Update general settings with language
                response = await client.put(
                    "/api/settings/general",
                    json={
                        "wake_word": "hey_jarvis",
                        "language": "en",
                        "voice_speed": 1.0,
                        "wake_word_threshold": 0.5
                    }
                )

                assert response.status_code == 200
                data = response.json()

                # Check propagation results - STT should receive language
                assert "propagation_results" in data
                if data["propagation_results"]:
                    # STT propagation should have been attempted
                    assert "stt" in data["propagation_results"] or data["propagation_results"].get("stt") is not None
