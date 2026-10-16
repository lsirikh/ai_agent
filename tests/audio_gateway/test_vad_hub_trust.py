"""
VAD 모델 로드 회귀 테스트

torch.hub.load 가 신뢰 확인 프롬프트(y/N)를 띄우면 컨테이너에서 EOF 로 실패하고
항상 0.3 을 돌려주는 MockModel 로 떨어져, 말소리가 한 번도 감지되지 않았다.
"""

from unittest.mock import MagicMock, patch


def test_should_load_silero_without_interactive_trust_prompt() -> None:
    import services.audio_gateway.app.vad as vad_module

    fake_torch = MagicMock()
    fake_torch.hub.load.return_value = (MagicMock(name="silero"), MagicMock())

    with (
        patch.object(vad_module, "TORCH_AVAILABLE", True),
        patch.object(vad_module, "torch", fake_torch, create=True),
    ):
        vad_module.VoiceActivityDetector()

    assert fake_torch.hub.load.call_args.kwargs.get("trust_repo") is True
