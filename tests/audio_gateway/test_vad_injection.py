"""
Phase 35.5.1: VAD 주입 패턴 테스트

TDD Red Phase - M1 해결: 중복 VAD 인스턴스 제거
BargeInDetector가 외부 VAD를 주입받도록 테스트
"""
import pytest
from unittest.mock import MagicMock
import sys
import os
import numpy as np

# 서비스 경로 추가
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../services/audio_gateway'))


class TestBargeInDetectorVADInjection:
    """BargeInDetector VAD 주입 패턴 테스트"""

    def test_barge_in_detector_accepts_vad_parameter(self):
        """
        M1 해결: BargeInDetector 생성자가 vad 파라미터를 받아야 함
        """
        from app.barge_in import BargeInDetector
        from app.vad import VoiceActivityDetector

        # VAD 인스턴스 생성
        external_vad = VoiceActivityDetector()

        # BargeInDetector가 vad 파라미터를 받을 수 있어야 함
        detector = BargeInDetector(vad=external_vad)

        assert detector.vad is external_vad, \
            "BargeInDetector should use the injected VAD instance"

    def test_barge_in_detector_uses_injected_vad(self):
        """
        M1 해결: BargeInDetector가 주입된 VAD를 실제로 사용해야 함
        """
        from app.barge_in import BargeInDetector, PlaybackState

        # Mock VAD 생성
        mock_vad = MagicMock()
        mock_vad.detect.return_value = {
            "probability": 0.8,
            "is_speech": True,
            "speech_started": True,
            "speech_ended": False
        }

        # BargeInDetector에 mock VAD 주입
        detector = BargeInDetector(vad=mock_vad)
        detector.set_playback_state(PlaybackState.PLAYING)

        # 오디오 청크로 detect 호출
        audio_chunk = np.ones(1600, dtype=np.float32) * 0.5
        result = detector.detect(audio_chunk)

        # 주입된 mock VAD가 호출되어야 함
        mock_vad.detect.assert_called_once()

    def test_barge_in_detector_creates_vad_when_not_injected(self):
        """
        VAD가 주입되지 않으면 내부에서 생성해야 함 (하위 호환성)
        """
        from app.barge_in import BargeInDetector
        from app.vad import VoiceActivityDetector

        # VAD 없이 생성
        detector = BargeInDetector()

        # 내부에서 VAD가 생성되어야 함
        assert detector.vad is not None
        assert isinstance(detector.vad, VoiceActivityDetector)


class TestMainSingleVADInstance:
    """main.py에서 단일 VAD 인스턴스 사용 테스트"""

    def test_main_creates_single_vad_instance(self):
        """
        main.py에서 단일 VAD 인스턴스를 생성하고 BargeInDetector에 주입해야 함
        """
        from app import main

        # main.py의 vad와 barge_in_detector.vad가 동일해야 함
        assert main.vad is main.barge_in_detector.vad, \
            "main.vad and barge_in_detector.vad should be the same instance"

    def test_no_duplicate_vad_instances(self):
        """
        중복 VAD 인스턴스가 없어야 함
        """
        from app import main

        # main.vad가 존재
        assert hasattr(main, 'vad')
        assert main.vad is not None

        # barge_in_detector.vad가 main.vad와 동일
        assert main.barge_in_detector.vad is main.vad

        # 두 VAD가 동일한 객체 ID를 가져야 함
        assert id(main.vad) == id(main.barge_in_detector.vad)


class TestVADInjectionWithReset:
    """VAD 주입 시 reset 동작 테스트"""

    def test_barge_in_reset_calls_injected_vad_reset(self):
        """
        BargeInDetector.reset()이 주입된 VAD의 reset()을 호출해야 함
        """
        from app.barge_in import BargeInDetector

        # Mock VAD
        mock_vad = MagicMock()

        detector = BargeInDetector(vad=mock_vad)
        detector.reset()

        # 주입된 VAD의 reset이 호출되어야 함
        mock_vad.reset.assert_called_once()

    def test_set_playback_state_playing_resets_injected_vad(self):
        """
        PlaybackState.PLAYING으로 전환 시 주입된 VAD가 리셋되어야 함
        """
        from app.barge_in import BargeInDetector, PlaybackState

        # Mock VAD
        mock_vad = MagicMock()

        detector = BargeInDetector(vad=mock_vad)
        detector.set_playback_state(PlaybackState.PLAYING)

        # VAD reset이 호출되어야 함
        mock_vad.reset.assert_called_once()