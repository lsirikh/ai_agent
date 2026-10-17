"""
말하는 도중의 '헤이 자비스' (사용자 요청 2026-10-17)

실측: 답을 말하는 동안 스피커 소리가 마이크로 다시 들어가(원격 데스크톱·에코 제거 안 됨)
사용자의 호출어가 6.9%·25.3%·17.2% 로 기준(30%)에 못 미쳤다. 조용할 때는 74%.
TTS 만 나올 때는 3% 를 넘은 적이 없어, 답하는 동안만 기준을 낮춘다.
"""

from unittest.mock import MagicMock

import numpy as np


def _detector(score):
    from services.wake_word.app.detector import WakeWordDetector

    detector = WakeWordDetector()
    detector.model = MagicMock()
    detector._use_mock = True
    detector.model.predict.return_value = {"hey_jarvis_v0.1": score}
    return detector


def test_lower_threshold_only_while_answering() -> None:
    quiet = _detector(0.2)
    assert quiet.detect(np.zeros(1600, dtype=np.float32))["detected"] is False

    answering = _detector(0.2)
    answering.answering = True
    assert answering.detect(np.zeros(1600, dtype=np.float32))["detected"] is True

    too_low = _detector(0.1)
    too_low.answering = True
    assert too_low.detect(np.zeros(1600, dtype=np.float32))["detected"] is False


def test_service_tracks_whether_assistant_is_answering() -> None:
    from services.wake_word.app.main import WakeWordService

    detector = _detector(0.0)
    service = WakeWordService(detector=detector)

    service.handle_state({"type": "state_change", "new_state": "TTS_PROCESSING"})
    assert detector.answering is True
    service.handle_state({"type": "state_change", "new_state": "READY"})
    assert detector.answering is False
