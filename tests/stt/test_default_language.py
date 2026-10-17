"""
언어를 지정하지 않은 전사 요청은 설정한 언어(기본 ko)로 받아 적는다 (실측 2026-10-17)

게이트웨이는 언어를 보내지 않아 매번 자동 감지가 됐고,
짧은 대답 "네." 를 일본어 "ねえ。" 로 받아 적어 실행 확인이 되지 않았다.
"""

import io
import sys
import wave
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "services" / "stt"))


def _wav() -> io.BytesIO:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(np.zeros(16000, dtype=np.int16).tobytes())
    buffer.seek(0)
    return buffer


def _transcribe(data=None):
    from app import main

    transcriber = MagicMock()
    transcriber.transcribe.return_value = {
        "text": "네", "confidence": 0.9, "language": "ko", "segments": []
    }
    with patch.object(main, "get_transcriber", return_value=transcriber):
        response = TestClient(main.app).post(
            "/transcribe",
            files={"audio": ("a.wav", _wav(), "audio/wav")},
            data=data or {},
        )
    assert response.status_code == 200
    return transcriber.transcribe.call_args.kwargs["language"]


def test_should_use_configured_language_when_request_has_none() -> None:
    from app import main

    with patch.dict(main._current_settings, {"language": "ko"}):
        assert _transcribe() == "ko"


def test_request_language_still_wins() -> None:
    assert _transcribe({"language": "en"}) == "en"


def test_auto_setting_means_detect() -> None:
    from app import main

    with patch.dict(main._current_settings, {"language": "auto"}):
        assert _transcribe() is None
