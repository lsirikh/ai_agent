"""
Backend API Settings Tests

Phase 5.2: Backend API - Settings 테스트
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


class TestGetSettings:
    """설정 조회 테스트"""

    def test_get_settings(self):
        """전체 설정을 조회할 수 있어야 한다"""
        from services.backend.app.main import app

        client = TestClient(app)
        response = client.get("/api/settings")

        assert response.status_code == 200
        data = response.json()

        assert "llm" in data
        assert "tts" in data
        assert "stt" in data
        assert "audio" in data

    def test_get_settings_includes_llm_config(self):
        """LLM 설정이 포함되어야 한다"""
        from services.backend.app.main import app

        client = TestClient(app)
        response = client.get("/api/settings")

        assert response.status_code == 200
        data = response.json()

        llm = data["llm"]
        assert "model" in llm
        assert "temperature" in llm
        assert "max_tokens" in llm
        assert "system_prompt" in llm

    def test_get_settings_includes_tts_config(self):
        """TTS 설정이 포함되어야 한다"""
        from services.backend.app.main import app

        client = TestClient(app)
        response = client.get("/api/settings")

        assert response.status_code == 200
        data = response.json()

        tts = data["tts"]
        assert "voice" in tts
        assert "speed" in tts

    def test_get_settings_includes_stt_config(self):
        """STT 설정이 포함되어야 한다"""
        from services.backend.app.main import app

        client = TestClient(app)
        response = client.get("/api/settings")

        assert response.status_code == 200
        data = response.json()

        stt = data["stt"]
        assert "language" in stt
        assert "model_size" in stt


class TestUpdateLLMSettings:
    """LLM 설정 업데이트 테스트"""

    def test_update_llm_settings(self):
        """LLM 설정을 업데이트할 수 있어야 한다"""
        from services.backend.app.main import app

        client = TestClient(app)
        response = client.patch("/api/settings/llm", json={
            "temperature": 0.8,
            "max_tokens": 2048
        })

        assert response.status_code == 200
        data = response.json()

        assert data["temperature"] == 0.8
        assert data["max_tokens"] == 2048

    def test_update_llm_system_prompt(self):
        """LLM 시스템 프롬프트를 업데이트할 수 있어야 한다"""
        from services.backend.app.main import app

        client = TestClient(app)
        response = client.patch("/api/settings/llm", json={
            "system_prompt": "당신은 친절한 AI 어시스턴트입니다."
        })

        assert response.status_code == 200
        data = response.json()

        assert data["system_prompt"] == "당신은 친절한 AI 어시스턴트입니다."

    def test_update_llm_partial_update(self):
        """LLM 설정을 부분적으로 업데이트할 수 있어야 한다"""
        from services.backend.app.main import app

        client = TestClient(app)

        # Get current settings
        response = client.get("/api/settings")
        original_max_tokens = response.json()["llm"]["max_tokens"]

        # Update only temperature
        response = client.patch("/api/settings/llm", json={
            "temperature": 0.5
        })

        assert response.status_code == 200
        data = response.json()

        assert data["temperature"] == 0.5
        assert data["max_tokens"] == original_max_tokens


class TestUpdateTTSSettings:
    """TTS 설정 업데이트 테스트"""

    def test_update_tts_settings(self):
        """TTS 설정을 업데이트할 수 있어야 한다"""
        from services.backend.app.main import app

        client = TestClient(app)
        response = client.patch("/api/settings/tts", json={
            "voice": "af_bella",
            "speed": 1.2
        })

        assert response.status_code == 200
        data = response.json()

        assert data["voice"] == "af_bella"
        assert data["speed"] == 1.2

    def test_update_tts_voice_only(self):
        """TTS 음성만 업데이트할 수 있어야 한다"""
        from services.backend.app.main import app

        client = TestClient(app)
        response = client.patch("/api/settings/tts", json={
            "voice": "af_sarah"
        })

        assert response.status_code == 200
        data = response.json()

        assert data["voice"] == "af_sarah"


class TestUpdateSTTSettings:
    """STT 설정 업데이트 테스트"""

    def test_update_stt_settings(self):
        """STT 설정을 업데이트할 수 있어야 한다"""
        from services.backend.app.main import app

        client = TestClient(app)
        response = client.patch("/api/settings/stt", json={
            "language": "en",
            "model_size": "small"
        })

        assert response.status_code == 200
        data = response.json()

        assert data["language"] == "en"
        assert data["model_size"] == "small"

    def test_update_stt_language_only(self):
        """STT 언어만 업데이트할 수 있어야 한다"""
        from services.backend.app.main import app

        client = TestClient(app)
        response = client.patch("/api/settings/stt", json={
            "language": "ja"
        })

        assert response.status_code == 200
        data = response.json()

        assert data["language"] == "ja"


class TestSettingsEventPublishing:
    """설정 변경 이벤트 발행 테스트"""

    def test_settings_update_publishes_event(self):
        """설정 변경 시 Redis 이벤트가 발행되어야 한다"""
        from services.backend.app.main import app
        from services.backend.app.routes import settings as settings_module

        client = TestClient(app)

        with patch.object(settings_module, 'publish_settings_event') as mock_publish:
            mock_publish.return_value = None

            response = client.patch("/api/settings/llm", json={
                "temperature": 0.9
            })

            assert response.status_code == 200
            mock_publish.assert_called_once()

            # 호출 인자 확인
            call_args = mock_publish.call_args
            assert call_args[0][0] == "llm"  # settings_type
            assert "temperature" in call_args[0][1]  # settings_data

    def test_tts_settings_update_publishes_event(self):
        """TTS 설정 변경 시 이벤트가 발행되어야 한다"""
        from services.backend.app.main import app
        from services.backend.app.routes import settings as settings_module

        client = TestClient(app)

        with patch.object(settings_module, 'publish_settings_event') as mock_publish:
            mock_publish.return_value = None

            response = client.patch("/api/settings/tts", json={
                "speed": 1.5
            })

            assert response.status_code == 200
            mock_publish.assert_called_once()
            assert mock_publish.call_args[0][0] == "tts"

    def test_stt_settings_update_publishes_event(self):
        """STT 설정 변경 시 이벤트가 발행되어야 한다"""
        from services.backend.app.main import app
        from services.backend.app.routes import settings as settings_module

        client = TestClient(app)

        with patch.object(settings_module, 'publish_settings_event') as mock_publish:
            mock_publish.return_value = None

            response = client.patch("/api/settings/stt", json={
                "language": "ko"
            })

            assert response.status_code == 200
            mock_publish.assert_called_once()
            assert mock_publish.call_args[0][0] == "stt"


class TestAudioSettings:
    """오디오 설정 테스트"""

    def test_get_audio_settings(self):
        """오디오 설정을 조회할 수 있어야 한다"""
        from services.backend.app.main import app

        client = TestClient(app)
        response = client.get("/api/settings")

        assert response.status_code == 200
        data = response.json()

        audio = data["audio"]
        assert "sample_rate" in audio
        assert "vad_threshold" in audio
        assert "silence_duration" in audio

    def test_update_audio_settings(self):
        """오디오 설정을 업데이트할 수 있어야 한다"""
        from services.backend.app.main import app

        client = TestClient(app)
        response = client.patch("/api/settings/audio", json={
            "vad_threshold": 0.6,
            "silence_duration": 1.0
        })

        assert response.status_code == 200
        data = response.json()

        assert data["vad_threshold"] == 0.6
        assert data["silence_duration"] == 1.0
