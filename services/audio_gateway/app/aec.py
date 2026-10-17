"""
Acoustic Echo Cancellation (AEC)

Phase 3.4: TTS 재생 오디오로 인한 에코 제거
NLMS (Normalized Least Mean Squares) 알고리즘 사용
"""
import asyncio
from typing import Optional

import numpy as np


class AcousticEchoCanceller:
    """
    음향 에코 제거기

    NLMS 알고리즘을 사용하여 스피커에서 재생되는 오디오가
    마이크에 입력되는 에코를 제거합니다.

    Attributes:
        sample_rate: 오디오 샘플레이트
        filter_length: 적응 필터 길이
        adaptation_rate: NLMS 적응률 (μ)
        delay_samples: 에코 경로 딜레이 보상
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        filter_length: int = 256,
        adaptation_rate: float = 0.1,
        delay_samples: int = 0
    ):
        """
        AcousticEchoCanceller 초기화

        Args:
            sample_rate: 오디오 샘플레이트 (Hz)
            filter_length: 적응 필터 탭 수
            adaptation_rate: NLMS 학습률 (0.0-1.0)
            delay_samples: 에코 딜레이 샘플 수
        """
        self.sample_rate = sample_rate
        self.filter_length = filter_length
        self.adaptation_rate = adaptation_rate
        self.delay_samples = delay_samples

        # NLMS 필터 계수
        self._filter_coeffs = np.zeros(filter_length, dtype=np.float32)

        # 재생 참조 버퍼 (링 버퍼)
        self._playback_buffer = np.zeros(filter_length, dtype=np.float32)
        self._playback_reference: Optional[np.ndarray] = None
        self._has_playback_reference = False

        # 정규화 상수: 거의 무음인 참조(x·x ≈ 0)로 나눠 계수가 폭주하지 않게
        # 탭마다 크기 0.03(약 -30dB) 만큼 더한다 (1e-8 이던 때 마이크 0.1 → 49.8 실측)
        self._eps = filter_length * 1e-3

    @property
    def has_playback_reference(self) -> bool:
        """재생 참조가 설정되어 있는지 반환"""
        return self._has_playback_reference

    def set_playback_reference(self, audio: np.ndarray) -> None:
        """
        재생 참조 오디오 설정

        Args:
            audio: 재생 중인 오디오 데이터
        """
        self._playback_reference = audio.astype(np.float32)
        self._has_playback_reference = True

        # 재생 버퍼 업데이트
        if len(audio) >= self.filter_length:
            self._playback_buffer = audio[-self.filter_length:].copy()
        else:
            # 버퍼 시프트 및 새 데이터 추가
            shift = len(audio)
            self._playback_buffer[:-shift] = self._playback_buffer[shift:]
            self._playback_buffer[-shift:] = audio

    def clear_playback_reference(self) -> None:
        """재생 참조 클리어"""
        self._playback_reference = None
        self._has_playback_reference = False
        self._playback_buffer = np.zeros(self.filter_length, dtype=np.float32)

    def process(self, mic_input: np.ndarray) -> np.ndarray:
        """
        에코 제거 처리

        Args:
            mic_input: 마이크 입력 오디오

        Returns:
            에코가 제거된 오디오
        """
        mic_input = mic_input.astype(np.float32)

        # 재생 참조가 없으면 패스스루
        if not self._has_playback_reference:
            return mic_input

        output = np.zeros_like(mic_input)

        # 샘플별 NLMS 처리
        for i in range(len(mic_input)):
            # 재생 버퍼에서 필터 입력 구성
            if i < self.filter_length:
                # 이전 버퍼와 현재 재생 참조 결합
                x = np.concatenate([
                    self._playback_buffer[i:],
                    self._playback_reference[:i] if self._playback_reference is not None and i > 0 else np.array([])
                ])
            else:
                if self._playback_reference is not None:
                    x = self._playback_reference[i-self.filter_length:i]
                else:
                    x = np.zeros(self.filter_length, dtype=np.float32)

            # 참조가 마이크 청크보다 짧으면 창이 짧아지므로 앞을 0 으로 채운다
            if len(x) < self.filter_length:
                x = np.pad(x, (self.filter_length - len(x), 0))

            x = x.astype(np.float32)

            # 에코 추정
            echo_estimate = np.dot(self._filter_coeffs, x)

            # 에코 제거
            error = mic_input[i] - echo_estimate
            output[i] = error

            # NLMS 필터 업데이트
            norm = np.dot(x, x) + self._eps
            self._filter_coeffs += (self.adaptation_rate * error * x) / norm

        # 재생 버퍼 업데이트
        if self._playback_reference is not None:
            if len(self._playback_reference) >= self.filter_length:
                self._playback_buffer = self._playback_reference[-self.filter_length:].copy()
            else:
                shift = len(self._playback_reference)
                self._playback_buffer[:-shift] = self._playback_buffer[shift:]
                self._playback_buffer[-shift:] = self._playback_reference

        return output

    async def process_async(self, mic_input: np.ndarray) -> np.ndarray:
        """
        비동기 에코 제거 처리

        Args:
            mic_input: 마이크 입력 오디오

        Returns:
            에코가 제거된 오디오
        """
        return self.process(mic_input)

    def reset(self) -> None:
        """AEC 상태 리셋"""
        self._filter_coeffs = np.zeros(self.filter_length, dtype=np.float32)
        self._playback_buffer = np.zeros(self.filter_length, dtype=np.float32)
        self._playback_reference = None
        self._has_playback_reference = False

    def get_filter_coefficients(self) -> np.ndarray:
        """
        현재 필터 계수 반환

        Returns:
            필터 계수 배열
        """
        return self._filter_coeffs.copy()

    def get_echo_return_loss(self, mic_input: np.ndarray, output: np.ndarray) -> float:
        """
        Echo Return Loss Enhancement (ERLE) 계산

        Args:
            mic_input: 원본 마이크 입력
            output: 에코 제거 후 출력

        Returns:
            ERLE in dB
        """
        input_power = np.mean(mic_input ** 2)
        output_power = np.mean(output ** 2)

        if output_power < self._eps:
            return float('inf')

        return 10 * np.log10(input_power / output_power)
