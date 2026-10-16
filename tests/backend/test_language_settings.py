"""
Phase 13.2: Language 연동 테스트

TDD Red-Green-Refactor cycle:
1. 언어 변경 시 LLM 시스템 프롬프트 변경
2. 언어 변경 시 STT 언어 힌트 전달
3. 언어에 맞는 TTS 음성 자동 선택
"""

import pytest
from unittest.mock import patch, MagicMock


class TestLanguagePrompts:
    """언어별 시스템 프롬프트 테스트"""

    def test_language_prompts_dict_exists(self):
        """LANGUAGE_PROMPTS 딕셔너리가 존재함"""
        from services.backend.app.services.llm_client import LANGUAGE_PROMPTS
        assert isinstance(LANGUAGE_PROMPTS, dict)

    def test_korean_prompt_exists(self):
        """한국어 프롬프트가 존재함"""
        from services.backend.app.services.llm_client import LANGUAGE_PROMPTS
        assert "ko" in LANGUAGE_PROMPTS
        assert "한국어" in LANGUAGE_PROMPTS["ko"]

    def test_english_prompt_exists(self):
        """영어 프롬프트가 존재함"""
        from services.backend.app.services.llm_client import LANGUAGE_PROMPTS
        assert "en" in LANGUAGE_PROMPTS
        assert "English" in LANGUAGE_PROMPTS["en"]

    def test_japanese_prompt_exists(self):
        """일본어 프롬프트가 존재함"""
        from services.backend.app.services.llm_client import LANGUAGE_PROMPTS
        assert "ja" in LANGUAGE_PROMPTS
        assert "日本語" in LANGUAGE_PROMPTS["ja"]


class TestLanguageVoiceMapping:
    """언어별 TTS 음성 매핑 테스트"""

    def test_language_voice_mapping_exists(self):
        """LANGUAGE_VOICE_MAPPING이 존재함"""
        from services.backend.app.services.llm_client import LANGUAGE_VOICE_MAPPING
        assert isinstance(LANGUAGE_VOICE_MAPPING, dict)

    def test_korean_voice_mapping(self):
        """한국어 음성 매핑"""
        from services.backend.app.services.llm_client import LANGUAGE_VOICE_MAPPING
        assert "ko" in LANGUAGE_VOICE_MAPPING
        # 한국어 음성 이름 포함 확인
        assert "ko" in LANGUAGE_VOICE_MAPPING["ko"].lower() or "korean" in LANGUAGE_VOICE_MAPPING["ko"].lower()

    def test_english_voice_mapping(self):
        """영어 음성 매핑"""
        from services.backend.app.services.llm_client import LANGUAGE_VOICE_MAPPING
        assert "en" in LANGUAGE_VOICE_MAPPING

    def test_japanese_voice_mapping(self):
        """일본어 음성 매핑"""
        from services.backend.app.services.llm_client import LANGUAGE_VOICE_MAPPING
        assert "ja" in LANGUAGE_VOICE_MAPPING


class TestGetSystemPromptByLanguage:
    """get_system_prompt_by_language 함수 테스트"""

    def test_get_korean_system_prompt(self):
        """한국어 시스템 프롬프트 반환"""
        from services.backend.app.services.llm_client import get_system_prompt_by_language
        prompt = get_system_prompt_by_language("ko")
        assert "한국어" in prompt

    def test_get_english_system_prompt(self):
        """영어 시스템 프롬프트 반환"""
        from services.backend.app.services.llm_client import get_system_prompt_by_language
        prompt = get_system_prompt_by_language("en")
        assert "English" in prompt

    def test_get_japanese_system_prompt(self):
        """일본어 시스템 프롬프트 반환"""
        from services.backend.app.services.llm_client import get_system_prompt_by_language
        prompt = get_system_prompt_by_language("ja")
        assert "日本語" in prompt

    def test_unknown_language_falls_back_to_korean(self):
        """알 수 없는 언어는 한국어로 폴백"""
        from services.backend.app.services.llm_client import get_system_prompt_by_language
        prompt = get_system_prompt_by_language("unknown")
        assert "한국어" in prompt


class TestGetVoiceByLanguage:
    """get_voice_by_language 함수 테스트"""

    def test_get_korean_voice(self):
        """한국어 음성 반환"""
        from services.backend.app.services.llm_client import get_voice_by_language
        voice = get_voice_by_language("ko")
        assert voice is not None
        assert len(voice) > 0

    def test_get_english_voice(self):
        """영어 음성 반환"""
        from services.backend.app.services.llm_client import get_voice_by_language
        voice = get_voice_by_language("en")
        assert voice is not None

    def test_get_japanese_voice(self):
        """일본어 음성 반환"""
        from services.backend.app.services.llm_client import get_voice_by_language
        voice = get_voice_by_language("ja")
        assert voice is not None


class TestLanguageSettingsIntegration:
    """언어 설정 통합 테스트"""

    def test_general_settings_includes_language(self, client):
        """General Settings에 language 포함"""
        response = client.get("/api/settings/general")
        data = response.json()
        assert "language" in data

    def test_language_update_propagates(self, client):
        """언어 변경이 전파됨"""
        response = client.put("/api/settings/general", json={
            "wake_word": "hey_jarvis",
            "language": "en",
            "voice_speed": 1.0,
            "wake_word_threshold": 0.5
        })
        assert response.status_code == 200
        data = response.json()
        assert data["language"] == "en"


@pytest.fixture
def client():
    """FastAPI TestClient fixture"""
    from fastapi.testclient import TestClient
    from services.backend.app.main import app
    return TestClient(app)
