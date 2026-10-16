"""
Test Settings Derivation

Phase 14.4.2: Settings Derivation Tests
- general.voice_speed derives to TTS speed
- general.language derives to STT language
- general.wake_word_threshold derives to Wake Word threshold
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestGeneralVoiceSpeedDerivesToTts:
    """Tests for voice_speed derivation to TTS."""

    @pytest.mark.asyncio
    async def test_general_voice_speed_derives_to_tts(self):
        """
        Test that general.voice_speed is propagated to TTS service.

        Requirements:
        - Update general settings with voice_speed
        - TTS service receives the speed value
        """
        from services.backend.app.main import app
        from httpx import AsyncClient, ASGITransport

        mock_sync_repo = MagicMock()
        mock_sync_repo.save = MagicMock(return_value=True)
        mock_sync_repo.load = MagicMock(return_value={})

        mock_propagator = AsyncMock()
        propagation_calls = []

        async def track_propagate(service_type, settings):
            propagation_calls.append((service_type, settings))
            return {"success": True}

        mock_propagator.propagate = track_propagate

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
                        "voice_speed": 1.5,
                        "wake_word_threshold": 0.5
                    }
                )

                assert response.status_code == 200

                # Check TTS propagation was called with speed
                tts_calls = [c for c in propagation_calls if c[0] == "tts"]
                assert len(tts_calls) >= 1
                assert tts_calls[0][1]["speed"] == 1.5


class TestGeneralLanguageDerivesToStt:
    """Tests for language derivation to STT."""

    @pytest.mark.asyncio
    async def test_general_language_derives_to_stt(self):
        """
        Test that general.language is propagated to STT service.

        Requirements:
        - Update general settings with language
        - STT service receives the language value
        """
        from services.backend.app.main import app
        from httpx import AsyncClient, ASGITransport

        mock_sync_repo = MagicMock()
        mock_sync_repo.save = MagicMock(return_value=True)
        mock_sync_repo.load = MagicMock(return_value={})

        mock_propagator = AsyncMock()
        propagation_calls = []

        async def track_propagate(service_type, settings):
            propagation_calls.append((service_type, settings))
            return {"success": True}

        mock_propagator.propagate = track_propagate

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
                        "language": "ja",
                        "voice_speed": 1.0,
                        "wake_word_threshold": 0.5
                    }
                )

                assert response.status_code == 200

                # Check STT propagation was called with language
                stt_calls = [c for c in propagation_calls if c[0] == "stt"]
                assert len(stt_calls) >= 1
                assert stt_calls[0][1]["language"] == "ja"


class TestGeneralThresholdDerivesToWakeWord:
    """Tests for threshold derivation to Wake Word."""

    @pytest.mark.asyncio
    async def test_general_threshold_derives_to_wake_word(self):
        """
        Test that general.wake_word_threshold is propagated to Wake Word service.

        Requirements:
        - Update general settings with wake_word_threshold
        - Wake Word service receives the threshold value
        """
        from services.backend.app.main import app
        from httpx import AsyncClient, ASGITransport

        mock_sync_repo = MagicMock()
        mock_sync_repo.save = MagicMock(return_value=True)
        mock_sync_repo.load = MagicMock(return_value={})

        mock_propagator = AsyncMock()
        propagation_calls = []

        async def track_propagate(service_type, settings):
            propagation_calls.append((service_type, settings))
            return {"success": True}

        mock_propagator.propagate = track_propagate

        with patch("services.backend.app.routes.settings.get_settings_repository") as mock_get_repo, \
             patch("services.backend.app.routes.settings.get_settings_propagator") as mock_get_prop:

            mock_get_repo.return_value = mock_sync_repo
            mock_get_prop.return_value = mock_propagator

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.put(
                    "/api/settings/general",
                    json={
                        "wake_word": "alexa",
                        "language": "ko",
                        "voice_speed": 1.0,
                        "wake_word_threshold": 0.7
                    }
                )

                assert response.status_code == 200

                # Check Wake Word propagation was called with threshold
                ww_calls = [c for c in propagation_calls if c[0] == "wake_word"]
                assert len(ww_calls) >= 1
                assert ww_calls[0][1]["threshold"] == 0.7
                assert ww_calls[0][1]["wake_word"] == "alexa"
