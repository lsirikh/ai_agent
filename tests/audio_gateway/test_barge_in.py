"""
Barge-in Detection Tests

Phase 3.3: 사용자가 TTS 재생 중 말할 때 감지하는 Barge-in 테스트
"""
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest


class TestBargeInDetectorInitialization:
    """Barge-in 감지기 초기화 테스트"""

    def test_barge_in_detector_init(self):
        """BargeInDetector가 올바르게 초기화되어야 한다"""
        from services.audio_gateway.app.barge_in import BargeInDetector

        detector = BargeInDetector()

        assert detector is not None
        assert detector.vad is not None

    def test_barge_in_with_custom_config(self):
        """커스텀 설정으로 초기화할 수 있어야 한다"""
        from services.audio_gateway.app.barge_in import BargeInDetector

        detector = BargeInDetector(
            min_speech_duration_ms=300,
            energy_threshold=0.02,
            vad_threshold=0.6
        )

        assert detector.min_speech_duration_ms == 300
        assert detector.energy_threshold == 0.02
        assert detector.vad_threshold == 0.6

    def test_barge_in_default_config(self):
        """기본 설정이 올바르게 적용되어야 한다"""
        from services.audio_gateway.app.barge_in import BargeInDetector

        detector = BargeInDetector()

        assert detector.min_speech_duration_ms == 200
        assert detector.energy_threshold == 0.01
        assert detector.vad_threshold == 0.5


class TestBargeInStateDetection:
    """상태별 Barge-in 감지 테스트"""

    def test_no_detection_when_idle(self):
        """IDLE 상태에서는 Barge-in을 감지하지 않아야 한다"""
        from services.audio_gateway.app.barge_in import BargeInDetector, PlaybackState

        detector = BargeInDetector()
        detector.set_playback_state(PlaybackState.IDLE)

        with patch.object(detector.vad, 'detect') as mock_vad:
            mock_vad.return_value = {"is_speech": True, "probability": 0.9}

            audio_chunk = np.random.randn(1600).astype(np.float32) * 0.1
            result = detector.detect(audio_chunk)

            assert result["barge_in_detected"] is False

    def test_detection_when_playing(self):
        """PLAYING 상태에서 음성이 감지되면 Barge-in이어야 한다"""
        from services.audio_gateway.app.barge_in import BargeInDetector, PlaybackState

        detector = BargeInDetector(min_speech_duration_ms=100)
        detector.set_playback_state(PlaybackState.PLAYING)

        with patch.object(detector.vad, 'detect') as mock_vad:
            # 음성 감지 + speech_started
            mock_vad.return_value = {
                "is_speech": True,
                "probability": 0.9,
                "speech_started": True
            }

            audio_chunk = np.random.randn(1600).astype(np.float32) * 0.1
            result = detector.detect(audio_chunk)

            assert result["barge_in_detected"] is True

    def test_no_detection_when_paused(self):
        """PAUSED 상태에서는 Barge-in을 감지하지 않아야 한다"""
        from services.audio_gateway.app.barge_in import BargeInDetector, PlaybackState

        detector = BargeInDetector()
        detector.set_playback_state(PlaybackState.PAUSED)

        with patch.object(detector.vad, 'detect') as mock_vad:
            mock_vad.return_value = {"is_speech": True, "probability": 0.9}

            audio_chunk = np.random.randn(1600).astype(np.float32) * 0.1
            result = detector.detect(audio_chunk)

            assert result["barge_in_detected"] is False


class TestMinSpeechDuration:
    """최소 음성 지속 시간 테스트"""

    def test_min_speech_duration_required(self):
        """최소 음성 지속 시간을 충족해야 Barge-in으로 인식"""
        from services.audio_gateway.app.barge_in import BargeInDetector, PlaybackState

        detector = BargeInDetector(min_speech_duration_ms=200)
        detector.set_playback_state(PlaybackState.PLAYING)

        with patch.object(detector.vad, 'detect') as mock_vad:
            # 첫 번째 프레임 - 음성 시작되지 않음
            mock_vad.return_value = {"is_speech": True, "probability": 0.8}

            audio_chunk = np.zeros(1600, dtype=np.float32)
            result1 = detector.detect(audio_chunk)

            # 아직 min_duration 미달
            assert result1["barge_in_detected"] is False

    def test_barge_in_after_min_duration(self):
        """최소 지속 시간 이후 Barge-in 감지"""
        from services.audio_gateway.app.barge_in import BargeInDetector, PlaybackState

        detector = BargeInDetector(min_speech_duration_ms=100)
        detector.set_playback_state(PlaybackState.PLAYING)

        with patch.object(detector.vad, 'detect') as mock_vad:
            # speech_started 이벤트 발생
            mock_vad.return_value = {
                "is_speech": True,
                "probability": 0.9,
                "speech_started": True
            }

            # 에너지가 충분한 오디오 (energy_threshold 충족 필요)
            audio_chunk = np.random.randn(1600).astype(np.float32) * 0.5
            result = detector.detect(audio_chunk)

            assert result["barge_in_detected"] is True


class TestEnergyThreshold:
    """에너지 임계값 테스트"""

    def test_energy_threshold_applied(self):
        """에너지 임계값이 적용되어야 한다"""
        from services.audio_gateway.app.barge_in import BargeInDetector, PlaybackState

        detector = BargeInDetector(energy_threshold=0.05)
        detector.set_playback_state(PlaybackState.PLAYING)

        with patch.object(detector.vad, 'detect') as mock_vad:
            mock_vad.return_value = {
                "is_speech": True,
                "probability": 0.9,
                "speech_started": True
            }

            # 낮은 에너지 오디오
            audio_chunk = np.zeros(1600, dtype=np.float32) + 0.001
            result = detector.detect(audio_chunk)

            # 에너지가 임계값 미만이면 Barge-in 미감지
            assert result["barge_in_detected"] is False

    def test_high_energy_triggers_barge_in(self):
        """높은 에너지의 음성은 Barge-in을 트리거해야 한다"""
        from services.audio_gateway.app.barge_in import BargeInDetector, PlaybackState

        detector = BargeInDetector(energy_threshold=0.01)
        detector.set_playback_state(PlaybackState.PLAYING)

        with patch.object(detector.vad, 'detect') as mock_vad:
            mock_vad.return_value = {
                "is_speech": True,
                "probability": 0.9,
                "speech_started": True
            }

            # 높은 에너지 오디오
            audio_chunk = np.random.randn(1600).astype(np.float32) * 0.5
            result = detector.detect(audio_chunk)

            assert result["barge_in_detected"] is True

    def test_calculate_energy(self):
        """오디오 에너지 계산이 올바른지 확인"""
        from services.audio_gateway.app.barge_in import BargeInDetector

        detector = BargeInDetector()

        # 무음
        silence = np.zeros(1600, dtype=np.float32)
        assert detector._calculate_energy(silence) == 0.0

        # 일정한 값
        constant = np.ones(1600, dtype=np.float32) * 0.5
        energy = detector._calculate_energy(constant)
        assert energy > 0


class TestRedisIntegration:
    """Redis 통합 테스트"""

    @pytest.mark.asyncio
    async def test_barge_in_publishes_event(self):
        """Barge-in 감지 시 Redis 이벤트를 발행해야 한다"""
        from services.audio_gateway.app.barge_in import BargeInDetector, PlaybackState

        mock_redis = AsyncMock()
        detector = BargeInDetector(redis_client=mock_redis)
        detector.set_playback_state(PlaybackState.PLAYING)

        with patch.object(detector.vad, 'detect') as mock_vad:
            mock_vad.return_value = {
                "is_speech": True,
                "probability": 0.95,
                "speech_started": True
            }

            audio_chunk = np.random.randn(1600).astype(np.float32) * 0.5
            await detector.detect_and_publish(audio_chunk)

            mock_redis.publish.assert_called_once()

    @pytest.mark.asyncio
    async def test_published_event_format(self):
        """발행된 이벤트 형식이 올바른지 확인"""
        from services.audio_gateway.app.barge_in import BargeInDetector, PlaybackState

        published_messages = []

        async def capture_publish(channel, message):
            published_messages.append({"channel": channel, "message": message})

        mock_redis = AsyncMock()
        mock_redis.publish = capture_publish

        detector = BargeInDetector(
            redis_client=mock_redis,
            redis_channel="edgevoice:barge_in:detected"
        )
        detector.set_playback_state(PlaybackState.PLAYING)

        with patch.object(detector.vad, 'detect') as mock_vad:
            mock_vad.return_value = {
                "is_speech": True,
                "probability": 0.95,
                "speech_started": True
            }

            audio_chunk = np.random.randn(1600).astype(np.float32) * 0.5
            await detector.detect_and_publish(audio_chunk)

            assert len(published_messages) == 1
            assert published_messages[0]["channel"] == "edgevoice:barge_in:detected"

            msg_data = json.loads(published_messages[0]["message"])
            assert msg_data["type"] == "barge_in_detected"

    @pytest.mark.asyncio
    async def test_no_publish_when_not_detected(self):
        """Barge-in 미감지 시 이벤트를 발행하지 않아야 한다"""
        from services.audio_gateway.app.barge_in import BargeInDetector, PlaybackState

        mock_redis = AsyncMock()
        detector = BargeInDetector(redis_client=mock_redis)
        detector.set_playback_state(PlaybackState.IDLE)

        with patch.object(detector.vad, 'detect') as mock_vad:
            mock_vad.return_value = {"is_speech": True, "probability": 0.9}

            audio_chunk = np.zeros(1600, dtype=np.float32)
            await detector.detect_and_publish(audio_chunk)

            mock_redis.publish.assert_not_called()


class TestPlaybackStateManagement:
    """재생 상태 관리 테스트"""

    def test_set_playback_state(self):
        """재생 상태를 설정할 수 있어야 한다"""
        from services.audio_gateway.app.barge_in import BargeInDetector, PlaybackState

        detector = BargeInDetector()

        detector.set_playback_state(PlaybackState.PLAYING)
        assert detector.playback_state == PlaybackState.PLAYING

        detector.set_playback_state(PlaybackState.IDLE)
        assert detector.playback_state == PlaybackState.IDLE

    def test_initial_state_is_idle(self):
        """초기 상태는 IDLE이어야 한다"""
        from services.audio_gateway.app.barge_in import BargeInDetector, PlaybackState

        detector = BargeInDetector()
        assert detector.playback_state == PlaybackState.IDLE

    def test_reset_clears_state(self):
        """리셋 시 상태가 초기화되어야 한다"""
        from services.audio_gateway.app.barge_in import BargeInDetector, PlaybackState

        detector = BargeInDetector()
        detector.set_playback_state(PlaybackState.PLAYING)

        detector.reset()

        assert detector.playback_state == PlaybackState.IDLE


class TestCooldownMechanism:
    """Barge-in 쿨다운 메커니즘 테스트"""

    def test_cooldown_after_barge_in(self):
        """Barge-in 후 쿨다운 기간 동안 재감지하지 않아야 한다"""
        from services.audio_gateway.app.barge_in import BargeInDetector, PlaybackState

        detector = BargeInDetector(cooldown_ms=500)
        detector.set_playback_state(PlaybackState.PLAYING)

        with patch.object(detector.vad, 'detect') as mock_vad:
            mock_vad.return_value = {
                "is_speech": True,
                "probability": 0.9,
                "speech_started": True
            }

            audio_chunk = np.random.randn(1600).astype(np.float32) * 0.5

            # 첫 번째 감지
            result1 = detector.detect(audio_chunk)
            assert result1["barge_in_detected"] is True

            # 쿨다운 중 - 재감지 안됨
            result2 = detector.detect(audio_chunk)
            assert result2["barge_in_detected"] is False
            assert result2.get("in_cooldown", False) is True
