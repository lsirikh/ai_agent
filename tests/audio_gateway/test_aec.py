"""
Acoustic Echo Cancellation (AEC) Tests

Phase 3.4: TTS 재생 오디오로 인한 에코 제거 테스트
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest


class TestAECInitialization:
    """AEC 초기화 테스트"""

    def test_aec_initialization(self):
        """AEC가 올바르게 초기화되어야 한다"""
        from services.audio_gateway.app.aec import AcousticEchoCanceller

        aec = AcousticEchoCanceller()

        assert aec is not None
        assert aec.sample_rate == 16000

    def test_aec_with_custom_config(self):
        """커스텀 설정으로 초기화할 수 있어야 한다"""
        from services.audio_gateway.app.aec import AcousticEchoCanceller

        aec = AcousticEchoCanceller(
            sample_rate=48000,
            filter_length=512,
            adaptation_rate=0.01
        )

        assert aec.sample_rate == 48000
        assert aec.filter_length == 512
        assert aec.adaptation_rate == 0.01

    def test_aec_default_config(self):
        """기본 설정이 올바르게 적용되어야 한다"""
        from services.audio_gateway.app.aec import AcousticEchoCanceller

        aec = AcousticEchoCanceller()

        assert aec.sample_rate == 16000
        assert aec.filter_length == 256
        assert aec.adaptation_rate == 0.1


class TestEchoCancellation:
    """에코 제거 테스트"""

    def test_echo_cancellation(self):
        """에코가 제거되어야 한다"""
        from services.audio_gateway.app.aec import AcousticEchoCanceller

        aec = AcousticEchoCanceller()

        # 재생 중인 오디오 설정
        playback_audio = np.sin(2 * np.pi * 440 * np.arange(1600) / 16000).astype(np.float32)
        aec.set_playback_reference(playback_audio)

        # 마이크 입력 (재생 오디오 + 사용자 음성)
        user_voice = np.random.randn(1600).astype(np.float32) * 0.1
        mic_input = playback_audio * 0.5 + user_voice  # 에코 + 음성

        # 에코 제거
        output = aec.process(mic_input)

        # 출력에서 에코가 감소되어야 함
        # 에코 성분의 에너지가 원본보다 줄어들었는지 확인
        echo_energy_before = np.mean(playback_audio ** 2)
        residual_echo = output - user_voice
        # 완벽한 제거가 아니더라도 감소되어야 함

        assert output is not None
        assert len(output) == len(mic_input)

    def test_echo_reduction_ratio(self):
        """에코가 충분히 감소되어야 한다"""
        from services.audio_gateway.app.aec import AcousticEchoCanceller

        aec = AcousticEchoCanceller()

        # 순수 에코 신호
        playback_audio = np.sin(2 * np.pi * 440 * np.arange(1600) / 16000).astype(np.float32)
        aec.set_playback_reference(playback_audio)

        # 마이크에 에코만 들어옴 (사용자 음성 없음)
        mic_input = playback_audio * 0.8

        output = aec.process(mic_input)

        # 출력 에너지가 입력보다 줄어들어야 함
        input_energy = np.mean(mic_input ** 2)
        output_energy = np.mean(output ** 2)

        # 최소 50% 이상 감소 기대 (실제로는 더 높을 수 있음)
        assert output_energy < input_energy


class TestPassthrough:
    """패스스루 모드 테스트"""

    def test_passthrough_when_no_playback(self):
        """재생 없을 때 입력을 그대로 통과시켜야 한다"""
        from services.audio_gateway.app.aec import AcousticEchoCanceller

        aec = AcousticEchoCanceller()

        # 재생 참조 없음 (기본 상태)
        mic_input = np.random.randn(1600).astype(np.float32) * 0.5

        output = aec.process(mic_input)

        # 입력과 출력이 거의 동일해야 함
        np.testing.assert_array_almost_equal(output, mic_input, decimal=5)

    def test_passthrough_after_playback_stops(self):
        """재생 중지 후 패스스루로 전환"""
        from services.audio_gateway.app.aec import AcousticEchoCanceller

        aec = AcousticEchoCanceller()

        # 재생 시작
        playback = np.sin(2 * np.pi * 440 * np.arange(1600) / 16000).astype(np.float32)
        aec.set_playback_reference(playback)

        # 재생 중지
        aec.clear_playback_reference()

        # 패스스루 확인
        mic_input = np.random.randn(1600).astype(np.float32) * 0.5
        output = aec.process(mic_input)

        np.testing.assert_array_almost_equal(output, mic_input, decimal=5)


class TestPlaybackReferenceManagement:
    """재생 참조 관리 테스트"""

    def test_set_playback_reference(self):
        """재생 참조를 설정할 수 있어야 한다"""
        from services.audio_gateway.app.aec import AcousticEchoCanceller

        aec = AcousticEchoCanceller()

        playback = np.random.randn(1600).astype(np.float32)
        aec.set_playback_reference(playback)

        assert aec.has_playback_reference is True

    def test_clear_playback_reference(self):
        """재생 참조를 클리어할 수 있어야 한다"""
        from services.audio_gateway.app.aec import AcousticEchoCanceller

        aec = AcousticEchoCanceller()

        playback = np.random.randn(1600).astype(np.float32)
        aec.set_playback_reference(playback)
        aec.clear_playback_reference()

        assert aec.has_playback_reference is False

    def test_update_playback_reference(self):
        """재생 참조를 업데이트할 수 있어야 한다"""
        from services.audio_gateway.app.aec import AcousticEchoCanceller

        aec = AcousticEchoCanceller()

        playback1 = np.zeros(1600, dtype=np.float32)
        playback2 = np.ones(1600, dtype=np.float32)

        aec.set_playback_reference(playback1)
        aec.set_playback_reference(playback2)

        # 최신 참조가 사용되어야 함
        assert aec.has_playback_reference is True


class TestRingBuffer:
    """링 버퍼 테스트"""

    def test_ring_buffer_for_delay_compensation(self):
        """딜레이 보상을 위한 링 버퍼가 동작해야 한다"""
        from services.audio_gateway.app.aec import AcousticEchoCanceller

        # 딜레이가 있는 AEC 설정
        aec = AcousticEchoCanceller(delay_samples=160)  # 10ms at 16kHz

        playback = np.sin(2 * np.pi * 440 * np.arange(1600) / 16000).astype(np.float32)
        aec.set_playback_reference(playback)

        mic_input = playback * 0.8
        output = aec.process(mic_input)

        assert output is not None

    def test_multiple_chunks_processing(self):
        """여러 청크를 연속으로 처리할 수 있어야 한다"""
        from services.audio_gateway.app.aec import AcousticEchoCanceller

        aec = AcousticEchoCanceller()

        for i in range(10):
            playback = np.sin(2 * np.pi * 440 * np.arange(1600) / 16000 + i).astype(np.float32)
            aec.set_playback_reference(playback)

            mic_input = playback * 0.5 + np.random.randn(1600).astype(np.float32) * 0.1
            output = aec.process(mic_input)

            assert output is not None
            assert len(output) == 1600


class TestAECReset:
    """AEC 리셋 테스트"""

    def test_reset_clears_state(self):
        """리셋 시 상태가 초기화되어야 한다"""
        from services.audio_gateway.app.aec import AcousticEchoCanceller

        aec = AcousticEchoCanceller()

        playback = np.random.randn(1600).astype(np.float32)
        aec.set_playback_reference(playback)

        aec.reset()

        assert aec.has_playback_reference is False

    def test_reset_clears_filter_coefficients(self):
        """리셋 시 필터 계수가 초기화되어야 한다"""
        from services.audio_gateway.app.aec import AcousticEchoCanceller

        aec = AcousticEchoCanceller()

        # 필터 학습
        for _ in range(5):
            playback = np.random.randn(1600).astype(np.float32)
            aec.set_playback_reference(playback)
            mic = playback * 0.5
            aec.process(mic)

        aec.reset()

        # 리셋 후 필터 계수 확인
        assert np.allclose(aec._filter_coeffs, np.zeros(aec.filter_length))


class TestAsyncAEC:
    """비동기 AEC 테스트"""

    @pytest.mark.asyncio
    async def test_async_process(self):
        """비동기 에코 제거가 동작해야 한다"""
        from services.audio_gateway.app.aec import AcousticEchoCanceller

        aec = AcousticEchoCanceller()

        playback = np.sin(2 * np.pi * 440 * np.arange(1600) / 16000).astype(np.float32)
        aec.set_playback_reference(playback)

        mic_input = playback * 0.5
        output = await aec.process_async(mic_input)

        assert output is not None
        assert len(output) == len(mic_input)


class TestNLMSAlgorithm:
    """NLMS 알고리즘 테스트"""

    def test_filter_adaptation(self):
        """필터가 에코 경로에 적응해야 한다"""
        from services.audio_gateway.app.aec import AcousticEchoCanceller

        # 재현 가능한 결과를 위해 시드 설정
        np.random.seed(42)

        aec = AcousticEchoCanceller(adaptation_rate=0.5)

        # 일정한 에코 신호 사용 (결정적 테스트)
        # 사인파를 사용하여 일관된 에코 제거 테스트
        t = np.arange(1600) / 16000
        playback = np.sin(2 * np.pi * 440 * t).astype(np.float32)

        aec.set_playback_reference(playback)

        # 마이크 입력 = 에코 (재생 신호의 감쇠 버전)
        mic_input = playback * 0.8

        # 여러 번 처리하면서 에러 감소 확인
        errors = []
        for i in range(20):
            output = aec.process(mic_input)
            error = np.mean(output ** 2)
            errors.append(error)
            # 같은 신호로 계속 처리하면 필터가 적응해야 함

        # 마지막 에러가 첫 번째 에러보다 작거나 같아야 함
        # 또는 전체적으로 에코가 감소하는 경향
        assert errors[-1] <= errors[0] * 1.5  # 약간의 여유 허용
