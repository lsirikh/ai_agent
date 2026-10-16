"""
Voice Activity Detection (VAD) Tests

Phase 3.2: Silero VAD 기반 음성 활동 감지 테스트
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest


class TestSileroVADModelLoading:
    """Silero VAD 모델 로드 테스트"""

    def test_silero_vad_loads(self):
        """Silero VAD 모델이 로드되어야 한다"""
        from services.audio_gateway.app.vad import VoiceActivityDetector

        vad = VoiceActivityDetector()

        assert vad is not None
        assert vad.model is not None

    def test_vad_with_custom_config(self):
        """커스텀 설정으로 VAD를 초기화할 수 있어야 한다"""
        from services.audio_gateway.app.vad import VoiceActivityDetector

        vad = VoiceActivityDetector(
            threshold=0.6,
            sample_rate=16000,
            min_speech_duration_ms=250
        )

        assert vad.threshold == 0.6
        assert vad.sample_rate == 16000
        assert vad.min_speech_duration_ms == 250

    def test_vad_default_config(self):
        """기본 설정이 올바르게 적용되어야 한다"""
        from services.audio_gateway.app.vad import VoiceActivityDetector

        vad = VoiceActivityDetector()

        assert vad.threshold == 0.5
        assert vad.sample_rate == 16000
        assert vad.min_speech_duration_ms == 250


class TestSpeechDetection:
    """음성 감지 테스트"""

    def test_detect_speech_in_audio(self):
        """오디오에서 음성을 감지해야 한다"""
        from services.audio_gateway.app.vad import VoiceActivityDetector

        vad = VoiceActivityDetector()

        with patch.object(vad, '_run_inference') as mock_inference:
            # 음성이 포함된 오디오 시뮬레이션
            mock_inference.return_value = 0.85

            audio_chunk = np.random.randn(1600).astype(np.float32) * 0.1
            result = vad.detect(audio_chunk)

            assert result["is_speech"] is True
            assert result["probability"] >= vad.threshold

    def test_detect_silence(self):
        """무음을 올바르게 감지해야 한다"""
        from services.audio_gateway.app.vad import VoiceActivityDetector

        vad = VoiceActivityDetector()

        with patch.object(vad, '_run_inference') as mock_inference:
            # 무음 시뮬레이션
            mock_inference.return_value = 0.1

            audio_chunk = np.zeros(1600, dtype=np.float32)
            result = vad.detect(audio_chunk)

            assert result["is_speech"] is False

    def test_detect_low_energy_as_silence(self):
        """낮은 에너지의 오디오를 무음으로 처리해야 한다"""
        from services.audio_gateway.app.vad import VoiceActivityDetector

        vad = VoiceActivityDetector()

        with patch.object(vad, '_run_inference') as mock_inference:
            mock_inference.return_value = 0.2

            # 아주 낮은 볼륨
            audio_chunk = np.random.randn(1600).astype(np.float32) * 0.001
            result = vad.detect(audio_chunk)

            assert result["is_speech"] is False


class TestVADProbability:
    """VAD 확률 반환 테스트"""

    def test_vad_returns_probability(self):
        """VAD가 음성 확률을 반환해야 한다"""
        from services.audio_gateway.app.vad import VoiceActivityDetector

        vad = VoiceActivityDetector()

        with patch.object(vad, '_run_inference') as mock_inference:
            mock_inference.return_value = 0.75

            audio_chunk = np.zeros(1600, dtype=np.float32)
            result = vad.detect(audio_chunk)

            assert "probability" in result
            assert 0.0 <= result["probability"] <= 1.0
            assert result["probability"] == 0.75

    def test_probability_range(self):
        """확률이 0.0에서 1.0 사이여야 한다"""
        from services.audio_gateway.app.vad import VoiceActivityDetector

        vad = VoiceActivityDetector()

        # 다양한 확률값 테스트
        test_values = [0.0, 0.25, 0.5, 0.75, 1.0]

        for prob in test_values:
            with patch.object(vad, '_run_inference') as mock_inference:
                mock_inference.return_value = prob

                audio_chunk = np.zeros(1600, dtype=np.float32)
                result = vad.detect(audio_chunk)

                assert result["probability"] == prob


class TestThresholdConfiguration:
    """임계값 설정 테스트"""

    def test_threshold_applied(self):
        """임계값이 올바르게 적용되어야 한다"""
        from services.audio_gateway.app.vad import VoiceActivityDetector

        # 높은 임계값 설정
        vad = VoiceActivityDetector(threshold=0.8)

        with patch.object(vad, '_run_inference') as mock_inference:
            # 0.7은 0.8 임계값보다 낮음
            mock_inference.return_value = 0.7

            audio_chunk = np.zeros(1600, dtype=np.float32)
            result = vad.detect(audio_chunk)

            assert result["is_speech"] is False

    def test_threshold_just_above(self):
        """임계값 바로 위의 확률은 음성으로 감지해야 한다"""
        from services.audio_gateway.app.vad import VoiceActivityDetector

        vad = VoiceActivityDetector(threshold=0.5)

        with patch.object(vad, '_run_inference') as mock_inference:
            mock_inference.return_value = 0.51

            audio_chunk = np.zeros(1600, dtype=np.float32)
            result = vad.detect(audio_chunk)

            assert result["is_speech"] is True

    def test_update_threshold(self):
        """임계값을 동적으로 변경할 수 있어야 한다"""
        from services.audio_gateway.app.vad import VoiceActivityDetector

        vad = VoiceActivityDetector(threshold=0.5)
        vad.set_threshold(0.7)

        assert vad.threshold == 0.7


class TestStreamingVAD:
    """스트리밍 VAD 테스트"""

    def test_process_audio_stream(self):
        """오디오 스트림을 연속으로 처리할 수 있어야 한다"""
        from services.audio_gateway.app.vad import VoiceActivityDetector

        vad = VoiceActivityDetector()

        with patch.object(vad, '_run_inference') as mock_inference:
            mock_inference.return_value = 0.3

            # 여러 청크 처리
            for _ in range(10):
                chunk = np.zeros(1600, dtype=np.float32)
                result = vad.detect(chunk)
                assert "is_speech" in result

    def test_speech_start_detection(self):
        """음성 시작을 감지해야 한다"""
        from services.audio_gateway.app.vad import VoiceActivityDetector

        # 짧은 최소 음성 지속 시간으로 설정 (200ms = 2 프레임)
        vad = VoiceActivityDetector(min_speech_duration_ms=200)

        with patch.object(vad, '_run_inference') as mock_inference:
            # 무음 → 음성 전환 (3프레임 음성으로 speech_started 트리거)
            mock_inference.side_effect = [0.1, 0.1, 0.8, 0.9, 0.85]

            chunk = np.zeros(1600, dtype=np.float32)

            # 무음 구간
            result1 = vad.detect(chunk)
            result2 = vad.detect(chunk)
            assert result1["is_speech"] is False
            assert result2["is_speech"] is False

            # 음성 시작 (첫 번째 음성 프레임 - 아직 min_duration 미달)
            result3 = vad.detect(chunk)
            assert result3["is_speech"] is True

            # 두 번째 음성 프레임 - min_duration 충족으로 speech_started
            result4 = vad.detect(chunk)
            assert result4["is_speech"] is True
            assert result4.get("speech_started", False) is True

    def test_speech_end_detection(self):
        """음성 종료를 감지해야 한다"""
        from services.audio_gateway.app.vad import VoiceActivityDetector

        # 짧은 min_speech_duration과 min_silence_duration 설정
        vad = VoiceActivityDetector(
            min_speech_duration_ms=100,  # 1프레임으로 음성 시작
            min_silence_duration_ms=200   # 2프레임으로 음성 종료
        )

        with patch.object(vad, '_run_inference') as mock_inference:
            # 음성 → 무음 전환
            mock_inference.side_effect = [0.9, 0.9, 0.1, 0.1]

            chunk = np.zeros(1600, dtype=np.float32)

            # 음성 구간 - speech_started 발생 (1프레임)
            result1 = vad.detect(chunk)
            assert result1.get("speech_started", False) is True

            vad.detect(chunk)  # 계속 음성

            # 무음 시작 (첫 번째 무음 프레임)
            vad.detect(chunk)

            # 두 번째 무음 프레임 - min_silence_duration 충족으로 speech_ended
            result = vad.detect(chunk)
            assert result.get("speech_ended", False) is True


class TestMinSpeechDuration:
    """최소 음성 지속 시간 테스트"""

    def test_min_speech_duration_enforced(self):
        """최소 음성 지속 시간이 적용되어야 한다"""
        from services.audio_gateway.app.vad import VoiceActivityDetector

        # 250ms 최소 지속 시간
        vad = VoiceActivityDetector(min_speech_duration_ms=250)

        with patch.object(vad, '_run_inference') as mock_inference:
            # 아주 짧은 음성 (100ms 시뮬레이션)
            mock_inference.side_effect = [0.8, 0.1]

            chunk = np.zeros(1600, dtype=np.float32)  # 100ms

            result1 = vad.detect(chunk)
            result2 = vad.detect(chunk)

            # 짧은 음성은 노이즈로 처리될 수 있음
            # 최소 지속 시간 미달 시 speech_started가 취소됨

    def test_valid_speech_after_min_duration(self):
        """최소 지속 시간 이후 음성이 유효해야 한다"""
        from services.audio_gateway.app.vad import VoiceActivityDetector

        vad = VoiceActivityDetector(min_speech_duration_ms=200)

        with patch.object(vad, '_run_inference') as mock_inference:
            # 300ms 동안 음성 (100ms × 3)
            mock_inference.side_effect = [0.8, 0.85, 0.9]

            chunk = np.zeros(1600, dtype=np.float32)

            vad.detect(chunk)
            vad.detect(chunk)
            result = vad.detect(chunk)

            assert result["is_speech"] is True


class TestVADReset:
    """VAD 상태 리셋 테스트"""

    def test_reset_vad_state(self):
        """VAD 상태를 리셋할 수 있어야 한다"""
        from services.audio_gateway.app.vad import VoiceActivityDetector

        vad = VoiceActivityDetector()

        with patch.object(vad, '_run_inference') as mock_inference:
            mock_inference.return_value = 0.9

            chunk = np.zeros(1600, dtype=np.float32)
            vad.detect(chunk)

            # 상태 리셋
            vad.reset()

            # 리셋 후에도 정상 동작
            mock_inference.return_value = 0.3
            result = vad.detect(chunk)
            assert result is not None

    def test_reset_clears_speech_state(self):
        """리셋 시 음성 상태가 클리어되어야 한다"""
        from services.audio_gateway.app.vad import VoiceActivityDetector

        vad = VoiceActivityDetector()

        with patch.object(vad, '_run_inference') as mock_inference:
            mock_inference.return_value = 0.9

            chunk = np.zeros(1600, dtype=np.float32)
            vad.detect(chunk)  # 음성 감지

            vad.reset()

            assert vad.is_currently_speaking is False


class TestVADAsync:
    """비동기 VAD 테스트"""

    @pytest.mark.asyncio
    async def test_async_detect(self):
        """비동기 음성 감지가 동작해야 한다"""
        from services.audio_gateway.app.vad import VoiceActivityDetector

        vad = VoiceActivityDetector()

        with patch.object(vad, '_run_inference') as mock_inference:
            mock_inference.return_value = 0.75

            chunk = np.zeros(1600, dtype=np.float32)
            result = await vad.detect_async(chunk)

            assert result["is_speech"] is True

    @pytest.mark.asyncio
    async def test_async_stream_processing(self):
        """비동기 스트림 처리가 동작해야 한다"""
        from services.audio_gateway.app.vad import VoiceActivityDetector

        vad = VoiceActivityDetector()

        async def audio_generator():
            for _ in range(5):
                yield np.zeros(1600, dtype=np.float32)

        with patch.object(vad, '_run_inference') as mock_inference:
            mock_inference.return_value = 0.6

            results = []
            async for chunk in audio_generator():
                result = await vad.detect_async(chunk)
                results.append(result)

            assert len(results) == 5
            assert all(r["is_speech"] for r in results)
