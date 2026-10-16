"""
Wake Word Detector Tests

Phase 3.1: OpenWakeWord 기반 Wake Word 감지 테스트
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest


class TestWakeWordModelLoading:
    """Wake Word 모델 로드 테스트"""

    def test_wake_word_model_loads(self):
        """OpenWakeWord 모델이 로드되어야 한다"""
        from services.wake_word.app.detector import WakeWordDetector

        detector = WakeWordDetector()

        assert detector is not None
        assert detector.model is not None

    def test_wake_word_model_with_custom_config(self):
        """커스텀 설정으로 모델을 로드할 수 있어야 한다"""
        from services.wake_word.app.detector import WakeWordDetector

        detector = WakeWordDetector(
            confidence_threshold=0.7,
            sample_rate=16000
        )

        assert detector.confidence_threshold == 0.7
        assert detector.sample_rate == 16000

    def test_wake_word_default_config(self):
        """기본 설정이 올바르게 적용되어야 한다"""
        from services.wake_word.app.detector import WakeWordDetector

        detector = WakeWordDetector()

        assert detector.confidence_threshold == 0.5
        assert detector.sample_rate == 16000


class TestWakeWordDetection:
    """Wake Word 감지 테스트"""

    def test_detect_hey_robot(self):
        """'헤이로봇' 또는 유사 Wake Word를 감지해야 한다"""
        from services.wake_word.app.detector import WakeWordDetector

        detector = WakeWordDetector()

        # Wake Word가 포함된 오디오 시뮬레이션 (Mock으로 처리)
        # 실제 테스트에서는 모델이 detection을 반환하도록 설정
        with patch.object(detector, '_run_inference') as mock_inference:
            mock_inference.return_value = {"hey_jarvis": 0.85}

            # 16kHz 오디오 1초
            audio_chunk = np.zeros(16000, dtype=np.float32)
            result = detector.detect(audio_chunk)

            assert result is not None
            assert result["detected"] is True
            assert result["confidence"] >= detector.confidence_threshold

    def test_detect_returns_wake_word_name(self):
        """감지 시 Wake Word 이름을 반환해야 한다"""
        from services.wake_word.app.detector import WakeWordDetector

        detector = WakeWordDetector()

        with patch.object(detector, '_run_inference') as mock_inference:
            mock_inference.return_value = {"hey_jarvis": 0.9}

            audio_chunk = np.zeros(16000, dtype=np.float32)
            result = detector.detect(audio_chunk)

            assert "wake_word" in result
            assert result["wake_word"] == "hey_jarvis"

    def test_no_detection_on_silence(self):
        """무음 시 Wake Word를 감지하지 않아야 한다"""
        from services.wake_word.app.detector import WakeWordDetector

        detector = WakeWordDetector()

        with patch.object(detector, '_run_inference') as mock_inference:
            # 모든 Wake Word 확률이 낮음
            mock_inference.return_value = {"hey_jarvis": 0.1, "alexa": 0.05}

            # 무음 오디오
            audio_chunk = np.zeros(16000, dtype=np.float32)
            result = detector.detect(audio_chunk)

            assert result["detected"] is False

    def test_no_detection_on_random_speech(self):
        """일반 음성에서는 Wake Word를 감지하지 않아야 한다"""
        from services.wake_word.app.detector import WakeWordDetector

        detector = WakeWordDetector()

        with patch.object(detector, '_run_inference') as mock_inference:
            mock_inference.return_value = {"hey_jarvis": 0.2}

            # 랜덤 노이즈 (일반 음성 시뮬레이션)
            audio_chunk = np.random.randn(16000).astype(np.float32) * 0.1
            result = detector.detect(audio_chunk)

            assert result["detected"] is False


class TestConfidenceThreshold:
    """신뢰도 임계값 테스트"""

    def test_confidence_threshold_applied(self):
        """신뢰도 임계값이 올바르게 적용되어야 한다"""
        from services.wake_word.app.detector import WakeWordDetector

        # 높은 임계값 설정
        detector = WakeWordDetector(confidence_threshold=0.9)

        with patch.object(detector, '_run_inference') as mock_inference:
            # 0.85는 0.9 임계값보다 낮음
            mock_inference.return_value = {"hey_jarvis": 0.85}

            audio_chunk = np.zeros(16000, dtype=np.float32)
            result = detector.detect(audio_chunk)

            assert result["detected"] is False

    def test_confidence_just_above_threshold(self):
        """임계값 바로 위의 신뢰도는 감지해야 한다"""
        from services.wake_word.app.detector import WakeWordDetector

        detector = WakeWordDetector(confidence_threshold=0.5)

        with patch.object(detector, '_run_inference') as mock_inference:
            mock_inference.return_value = {"hey_jarvis": 0.51}

            audio_chunk = np.zeros(16000, dtype=np.float32)
            result = detector.detect(audio_chunk)

            assert result["detected"] is True

    def test_update_confidence_threshold(self):
        """신뢰도 임계값을 동적으로 변경할 수 있어야 한다"""
        from services.wake_word.app.detector import WakeWordDetector

        detector = WakeWordDetector(confidence_threshold=0.5)
        detector.set_confidence_threshold(0.8)

        assert detector.confidence_threshold == 0.8


class TestRedisIntegration:
    """Redis 통합 테스트 (Mock)"""

    @pytest.mark.asyncio
    async def test_detection_publishes_event(self):
        """Wake Word 감지 시 Redis 이벤트를 발행해야 한다"""
        from services.wake_word.app.detector import WakeWordDetector

        mock_redis = AsyncMock()
        detector = WakeWordDetector(redis_client=mock_redis)

        with patch.object(detector, '_run_inference') as mock_inference:
            mock_inference.return_value = {"hey_jarvis": 0.9}

            audio_chunk = np.zeros(16000, dtype=np.float32)
            await detector.detect_and_publish(audio_chunk)

            mock_redis.publish.assert_called_once()

    @pytest.mark.asyncio
    async def test_published_event_format(self):
        """발행된 이벤트 형식이 올바른지 확인"""
        from services.wake_word.app.detector import WakeWordDetector
        import json

        published_messages = []

        async def capture_publish(channel, message):
            published_messages.append({"channel": channel, "message": message})

        mock_redis = AsyncMock()
        mock_redis.publish = capture_publish

        detector = WakeWordDetector(
            redis_client=mock_redis,
            redis_channel="edgevoice:wake_word:detected"
        )

        with patch.object(detector, '_run_inference') as mock_inference:
            mock_inference.return_value = {"hey_jarvis": 0.95}

            audio_chunk = np.zeros(16000, dtype=np.float32)
            await detector.detect_and_publish(audio_chunk)

            assert len(published_messages) == 1
            assert published_messages[0]["channel"] == "edgevoice:wake_word:detected"

            msg_data = json.loads(published_messages[0]["message"])
            assert msg_data["type"] == "wake_word_detected"
            assert msg_data["wake_word"] == "hey_jarvis"
            assert "confidence" in msg_data

    @pytest.mark.asyncio
    async def test_no_publish_when_not_detected(self):
        """Wake Word 미감지 시 이벤트를 발행하지 않아야 한다"""
        from services.wake_word.app.detector import WakeWordDetector

        mock_redis = AsyncMock()
        detector = WakeWordDetector(redis_client=mock_redis)

        with patch.object(detector, '_run_inference') as mock_inference:
            mock_inference.return_value = {"hey_jarvis": 0.1}

            audio_chunk = np.zeros(16000, dtype=np.float32)
            await detector.detect_and_publish(audio_chunk)

            mock_redis.publish.assert_not_called()


class TestStreamingDetection:
    """스트리밍 감지 테스트"""

    def test_process_audio_chunk(self):
        """오디오 청크를 연속으로 처리할 수 있어야 한다"""
        from services.wake_word.app.detector import WakeWordDetector

        detector = WakeWordDetector()

        with patch.object(detector, '_run_inference') as mock_inference:
            mock_inference.return_value = {"hey_jarvis": 0.1}

            # 여러 청크 처리
            for _ in range(5):
                chunk = np.zeros(1600, dtype=np.float32)  # 100ms
                result = detector.detect(chunk)
                assert "detected" in result

    def test_reset_detection_state(self):
        """감지 상태를 리셋할 수 있어야 한다"""
        from services.wake_word.app.detector import WakeWordDetector

        detector = WakeWordDetector()
        detector.reset()

        # 리셋 후 정상 동작 확인
        with patch.object(detector, '_run_inference') as mock_inference:
            mock_inference.return_value = {"hey_jarvis": 0.1}

            chunk = np.zeros(1600, dtype=np.float32)
            result = detector.detect(chunk)
            assert result is not None


class TestMultipleWakeWords:
    """다중 Wake Word 지원 테스트"""

    def test_detect_multiple_wake_words(self):
        """여러 Wake Word 중 하나를 감지해야 한다"""
        from services.wake_word.app.detector import WakeWordDetector

        detector = WakeWordDetector()

        with patch.object(detector, '_run_inference') as mock_inference:
            # 여러 Wake Word 확률 반환
            mock_inference.return_value = {
                "hey_jarvis": 0.3,
                "alexa": 0.85,
                "ok_google": 0.1
            }

            audio_chunk = np.zeros(16000, dtype=np.float32)
            result = detector.detect(audio_chunk)

            assert result["detected"] is True
            assert result["wake_word"] == "alexa"
            assert result["confidence"] == 0.85

    def test_highest_confidence_wins(self):
        """가장 높은 신뢰도의 Wake Word가 선택되어야 한다"""
        from services.wake_word.app.detector import WakeWordDetector

        detector = WakeWordDetector(confidence_threshold=0.5)

        with patch.object(detector, '_run_inference') as mock_inference:
            mock_inference.return_value = {
                "hey_jarvis": 0.6,
                "alexa": 0.8,
                "ok_google": 0.7
            }

            audio_chunk = np.zeros(16000, dtype=np.float32)
            result = detector.detect(audio_chunk)

            assert result["wake_word"] == "alexa"


class TestCooldownPeriod:
    """감지 쿨다운 테스트"""

    def test_cooldown_prevents_repeated_detection(self):
        """쿨다운 기간 동안 중복 감지를 방지해야 한다"""
        from services.wake_word.app.detector import WakeWordDetector

        detector = WakeWordDetector(cooldown_seconds=1.0)

        with patch.object(detector, '_run_inference') as mock_inference:
            mock_inference.return_value = {"hey_jarvis": 0.9}

            audio_chunk = np.zeros(16000, dtype=np.float32)

            # 첫 번째 감지
            result1 = detector.detect(audio_chunk)
            assert result1["detected"] is True

            # 쿨다운 중 - 감지하지 않음
            result2 = detector.detect(audio_chunk)
            assert result2["detected"] is False
            assert result2.get("cooldown", False) is True

    def test_detection_after_cooldown(self):
        """쿨다운 후에는 다시 감지해야 한다"""
        from services.wake_word.app.detector import WakeWordDetector
        import time

        detector = WakeWordDetector(cooldown_seconds=0.1)

        with patch.object(detector, '_run_inference') as mock_inference:
            mock_inference.return_value = {"hey_jarvis": 0.9}

            audio_chunk = np.zeros(16000, dtype=np.float32)

            # 첫 번째 감지
            result1 = detector.detect(audio_chunk)
            assert result1["detected"] is True

            # 쿨다운 대기
            time.sleep(0.15)

            # 쿨다운 후 다시 감지
            result2 = detector.detect(audio_chunk)
            assert result2["detected"] is True
