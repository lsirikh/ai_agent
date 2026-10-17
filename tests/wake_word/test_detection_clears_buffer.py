"""
감지한 뒤에는 모델의 소리·예측 버퍼를 비운다 (실측 2026-10-17)

대기 중 소리를 끊지 않고 받게 되자, 듣기가 끝나고 다시 받기 시작할 때 버퍼에 남은
이전 "Hey Jarvis" 로 한 번 더 감지됐다(질문 인식 직후 0.998).
"""

from unittest.mock import MagicMock

import numpy as np


def test_should_clear_model_buffers_after_detection() -> None:
    from services.wake_word.app.detector import WakeWordDetector

    detector = WakeWordDetector()
    detector.model = MagicMock()
    detector._use_mock = True
    detector.model.predict.return_value = {"hey_jarvis_v0.1": 0.95}

    result = detector.detect(np.zeros(1600, dtype=np.float32))

    assert result["detected"] is True
    detector.model.reset.assert_called_once()


def test_should_keep_buffers_while_not_detected() -> None:
    from services.wake_word.app.detector import WakeWordDetector

    detector = WakeWordDetector()
    detector.model = MagicMock()
    detector._use_mock = True
    detector.model.predict.return_value = {"hey_jarvis_v0.1": 0.05}

    detector.detect(np.zeros(1600, dtype=np.float32))

    detector.model.reset.assert_not_called()
