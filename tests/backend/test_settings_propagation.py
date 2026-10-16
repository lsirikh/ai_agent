"""
Backend Tests - Settings Propagation

Phase 12.2: 설정 서비스 전파 테스트
Phase 47.2: Wake Word Threshold 런타임 동적 반영 - Backend 설정 전파 테스트
"""
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
import httpx


class TestTTSSettingsPropagated:
    """TTS 설정이 전파되는지 테스트"""

    @pytest.mark.asyncio
    async def test_tts_settings_propagated(self):
        """
        TTS 설정 변경 시 TTS 서비스에 전파되어야 함.
        """
        from services.backend.app.services.settings_propagator import SettingsPropagator

        propagator = SettingsPropagator()

        # Mock HTTP 클라이언트
        with patch.object(propagator, '_http_client') as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"status": "applied"}
            mock_client.put = AsyncMock(return_value=mock_response)

            # TTS 설정 전파
            tts_settings = {
                "engine": "melo",
                "voice": "af_heart",
                "speed": 1.2
            }
            result = await propagator.propagate("tts", tts_settings)

            # 전파 확인
            assert result["success"] is True
            mock_client.put.assert_called_once()
            call_args = mock_client.put.call_args
            assert "/settings" in call_args[0][0]


class TestSTTSettingsPropagated:
    """STT 설정이 전파되는지 테스트"""

    @pytest.mark.asyncio
    async def test_stt_settings_propagated(self):
        """
        STT 설정 변경 시 STT 서비스에 전파되어야 함.
        """
        from services.backend.app.services.settings_propagator import SettingsPropagator

        propagator = SettingsPropagator()

        with patch.object(propagator, '_http_client') as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"status": "applied"}
            mock_client.put = AsyncMock(return_value=mock_response)

            # STT 설정 전파
            stt_settings = {
                "model": "large-v3-turbo",
                "language": "ko"
            }
            result = await propagator.propagate("stt", stt_settings)

            # 전파 확인
            assert result["success"] is True
            mock_client.put.assert_called_once()


class TestLLMSettingsPropagated:
    """LLM 설정이 전파되는지 테스트"""

    @pytest.mark.asyncio
    async def test_llm_settings_propagated(self):
        """
        LLM 설정 변경 시 전파되어야 함.
        Note: LLM(vLLM)은 모델 변경 시 재시작이 필요할 수 있음.
        """
        from services.backend.app.services.settings_propagator import SettingsPropagator

        propagator = SettingsPropagator()

        with patch.object(propagator, '_http_client') as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"status": "applied", "restart_required": True}
            mock_client.put = AsyncMock(return_value=mock_response)

            # LLM 설정 전파
            llm_settings = {
                "model": "Qwen/Qwen2.5-7B-Instruct",
                "temperature": 0.8,
                "max_tokens": 2048
            }
            result = await propagator.propagate("llm", llm_settings)

            # 전파 결과 확인
            assert result["success"] is True


class TestPropagationReturnsStatus:
    """전파 상태 반환 테스트"""

    @pytest.mark.asyncio
    async def test_propagation_returns_status(self):
        """
        전파 결과에 상태 정보가 포함되어야 함.
        - success: 성공 여부
        - service: 서비스 이름
        - restart_required: 재시작 필요 여부
        - error: 오류 메시지 (실패 시)
        """
        from services.backend.app.services.settings_propagator import SettingsPropagator

        propagator = SettingsPropagator()

        with patch.object(propagator, '_http_client') as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"status": "applied"}
            mock_client.put = AsyncMock(return_value=mock_response)

            result = await propagator.propagate("tts", {"engine": "melo"})

            # 필수 필드 확인
            assert "success" in result
            assert "service" in result
            assert result["service"] == "tts"

    @pytest.mark.asyncio
    async def test_propagation_failure_returns_error(self):
        """
        전파 실패 시 에러 정보 반환.
        """
        from services.backend.app.services.settings_propagator import SettingsPropagator

        propagator = SettingsPropagator()

        with patch.object(propagator, '_http_client') as mock_client:
            # 서비스 연결 실패 시뮬레이션
            mock_client.put = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))

            result = await propagator.propagate("tts", {"engine": "melo"})

            # 실패 상태 확인
            assert result["success"] is False
            assert "error" in result


class TestWakeWordThresholdPropagation:
    """
    Phase 47.2: Wake Word Threshold 런타임 동적 반영 - Backend 설정 전파 테스트

    Dashboard에서 Wake Word Threshold를 변경하면 Backend가
    Wake Word 서비스에 HTTP 요청을 보내 즉시 반영되어야 함.
    """

    @pytest.mark.asyncio
    async def test_backend_broadcasts_to_wake_word(self):
        """
        Backend PUT /settings/general에서 Wake Word 서비스로 threshold 전파 확인.

        요구사항:
        1. PUT /api/settings/general 호출 시
        2. SettingsPropagator가 wake_word 서비스로 HTTP PUT 요청 전송
        3. threshold 값이 올바르게 전달되어야 함
        """
        from services.backend.app.services.settings_propagator import SettingsPropagator

        propagator = SettingsPropagator()

        with patch.object(propagator, '_http_client') as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "wake_word": "hey_jarvis",
                "threshold": 0.35,
                "status": "applied"
            }
            mock_client.put = AsyncMock(return_value=mock_response)

            # Wake Word 설정 전파
            wake_word_settings = {
                "wake_word": "hey_jarvis",
                "threshold": 0.35
            }
            result = await propagator.propagate("wake_word", wake_word_settings)

            # 전파 성공 확인
            assert result["success"] is True
            assert result["service"] == "wake_word"

            # HTTP 요청 확인
            mock_client.put.assert_called_once()
            call_args = mock_client.put.call_args
            assert "/settings" in call_args[0][0]
            assert call_args[1]["json"]["threshold"] == 0.35

    @pytest.mark.asyncio
    async def test_general_settings_propagates_wake_word_threshold(self):
        """
        PUT /api/settings/general 엔드포인트에서 wake_word_threshold가 전파되어야 함.

        요구사항:
        1. GeneralSettings에 wake_word_threshold 변경
        2. SettingsPropagator.propagate("wake_word", {...}) 호출 확인
        """
        from fastapi.testclient import TestClient
        from services.backend.app.main import app
        from services.backend.app.services.settings_propagator import get_settings_propagator

        client = TestClient(app)

        with patch('services.backend.app.routes.settings.get_settings_propagator') as mock_get_propagator:
            mock_propagator = MagicMock()
            mock_propagator.propagate = AsyncMock(return_value={"success": True, "service": "wake_word"})
            mock_get_propagator.return_value = mock_propagator

            # General Settings 업데이트
            response = client.put(
                "/api/settings/general",
                json={
                    "wake_word": "hey_jarvis",
                    "language": "ko",
                    "voice_speed": 1.0,
                    "wake_word_threshold": 0.35
                }
            )

            assert response.status_code == 200

            # wake_word 전파 호출 확인
            propagate_calls = mock_propagator.propagate.call_args_list
            wake_word_call = None
            for call in propagate_calls:
                if call[0][0] == "wake_word":
                    wake_word_call = call
                    break

            assert wake_word_call is not None
            assert wake_word_call[0][1]["threshold"] == 0.35

    @pytest.mark.asyncio
    async def test_wake_word_service_url_configured(self):
        """
        Wake Word 서비스 URL이 SERVICE_URLS에 올바르게 설정되어 있어야 함.
        """
        from services.backend.app.services.settings_propagator import SERVICE_URLS

        assert "wake_word" in SERVICE_URLS
        assert "11005" in SERVICE_URLS["wake_word"]
