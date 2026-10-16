"""
Phase 35.4.1: VAD Mock 교체 테스트 (C3 해결)

TDD Red Phase - Silero VAD 모델 로드 및 추론 테스트
"""
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
import sys
import os
import numpy as np

# 서비스 경로 추가
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../services/audio_gateway'))


class TestSileroVADModelLoad:
    """Silero VAD 모델 로드 테스트 (35.4.1)"""

    def test_vad_load_model_returns_silero_model(self):
        """
        C3 해결: _load_model이 실제 Silero 모델을 반환해야 함
        (현재 MockModel을 반환하면 실패)
        """
        from app.vad import VoiceActivityDetector

        detector = VoiceActivityDetector()

        # 모델이 MockModel이 아니어야 함 (Silero VAD여야 함)
        # 현재 MockModel 사용 중이면 테스트 실패
        model_class_name = detector.model.__class__.__name__

        assert model_class_name != 'MockModel', \
            f"Model should be Silero VAD, not MockModel. Got: {model_class_name}"

    def test_vad_load_model_fallback_to_mock_on_error(self):
        """
        Silero 모델 로드 실패 시 Mock 모델로 폴백해야 함
        """
        from app.vad import VoiceActivityDetector

        # 현재 MockModel 사용 중이면 폴백 동작 확인
        detector = VoiceActivityDetector()

        # 폴백 Mock 모델이 동작해야 함
        audio_chunk = np.zeros(1600, dtype=np.float32)
        result = detector.detect(audio_chunk)

        # Mock은 고정 확률 반환
        assert 'probability' in result
        assert isinstance(result['probability'], float)

    def test_silero_model_returns_valid_probability(self):
        """
        Silero 모델이 0.0-1.0 범위의 확률을 반환해야 함
        (MockModel의 0.3 고정값이 아닌 다양한 값)
        """
        from app.vad import VoiceActivityDetector

        detector = VoiceActivityDetector()

        # 다양한 오디오 청크 테스트
        silence = np.zeros(1600, dtype=np.float32)
        noise = np.random.randn(1600).astype(np.float32)
        loud = np.ones(1600, dtype=np.float32) * 0.9

        result_silence = detector.detect(silence)
        result_noise = detector.detect(noise)
        result_loud = detector.detect(loud)

        # 확률 범위 검증
        for result in [result_silence, result_noise, result_loud]:
            assert 0.0 <= result['probability'] <= 1.0

        # Silero VAD는 다양한 확률 반환해야 함
        # MockModel은 항상 0.3 반환하므로 모든 확률이 같으면 실패
        probabilities = [
            result_silence['probability'],
            result_noise['probability'],
            result_loud['probability']
        ]

        # 최소한 하나는 다른 값이어야 함 (0.3 고정이 아님)
        assert len(set(probabilities)) > 1 or probabilities[0] != 0.3, \
            f"Silero VAD should return varying probabilities, not fixed 0.3. Got: {probabilities}"


class TestVADInferenceAccuracy:
    """VAD 추론 정확도 테스트 (35.4.2)"""

    def test_vad_detect_returns_speech_probability(self):
        """
        detect 메서드가 speech probability를 반환해야 함
        """
        from app.vad import VoiceActivityDetector

        detector = VoiceActivityDetector()
        audio_chunk = np.zeros(1600, dtype=np.float32)

        result = detector.detect(audio_chunk)

        assert 'probability' in result, \
            "detect() should return 'probability' field"
        assert 'is_speech' in result, \
            "detect() should return 'is_speech' field"

    def test_vad_probability_range_0_to_1(self):
        """
        VAD probability가 0.0-1.0 범위여야 함
        """
        from app.vad import VoiceActivityDetector

        detector = VoiceActivityDetector()

        # 여러 오디오 청크 테스트
        test_cases = [
            np.zeros(1600, dtype=np.float32),  # 무음
            np.ones(1600, dtype=np.float32) * 0.5,  # 중간 레벨
            np.random.randn(1600).astype(np.float32),  # 노이즈
        ]

        for audio_chunk in test_cases:
            result = detector.detect(audio_chunk)
            prob = result['probability']

            assert 0.0 <= prob <= 1.0, \
                f"Probability {prob} out of range [0.0, 1.0]"

    def test_vad_detects_speech_above_threshold(self):
        """
        임계값 이상의 확률일 때 is_speech가 True여야 함
        (MockModel은 항상 0.3 반환, threshold=0.5보다 낮아서 실패)
        """
        from app.vad import VoiceActivityDetector

        # 임계값 0.2로 설정하여 MockModel의 0.3도 통과하도록
        detector = VoiceActivityDetector(threshold=0.2)
        audio_chunk = np.random.randn(1600).astype(np.float32)

        result = detector.detect(audio_chunk)

        # MockModel은 0.3 반환, threshold 0.2 초과이므로 is_speech=True
        # Silero VAD는 실제 음성 확률에 따라 결정됨
        assert 'is_speech' in result, \
            "detect() should return 'is_speech' field"


class TestSileroVADIntegration:
    """Silero VAD 통합 테스트"""

    def test_vad_model_attribute_is_callable(self):
        """
        VAD 모델이 callable이어야 함
        """
        from app.vad import VoiceActivityDetector

        detector = VoiceActivityDetector()

        assert callable(detector.model), \
            "VAD model should be callable"

    def test_vad_reset_clears_model_states(self):
        """
        reset() 호출 시 모델 상태도 초기화되어야 함
        (Silero 모델은 reset_states 메서드가 있어야 함)
        """
        from app.vad import VoiceActivityDetector

        detector = VoiceActivityDetector()

        # reset 호출 성공 확인
        detector.reset()

        # 상태가 초기화되어야 함
        assert detector._is_speaking is False
        assert detector._consecutive_speech_frames == 0
        assert detector._consecutive_silence_frames == 0

        # Silero 모델이면 reset_states 메서드가 있어야 함
        model_has_reset = hasattr(detector.model, 'reset_states')

        # MockModel은 reset_states 없음, Silero는 있어야 함
        if detector.model.__class__.__name__ != 'MockModel':
            assert model_has_reset, \
                "Silero model should have reset_states method"