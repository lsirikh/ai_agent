"""
Audio Recorder

Phase 35.7.1: STT 호출을 위한 오디오 녹음기
음성 감지 시 오디오 데이터를 버퍼에 저장하고 WAV 형식으로 변환
"""
import io
import wave
from typing import List, Optional

import numpy as np


class AudioRecorder:
    """
    오디오 녹음기

    음성 감지 시 오디오 청크를 버퍼에 저장하고
    STT 서비스 호출을 위해 WAV 형식으로 변환합니다.

    Attributes:
        sample_rate: 오디오 샘플레이트 (Hz)
        channels: 오디오 채널 수 (모노=1)
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        channels: int = 1
    ):
        """
        AudioRecorder 초기화

        Args:
            sample_rate: 오디오 샘플레이트 (Hz)
            channels: 오디오 채널 수
        """
        self.sample_rate = sample_rate
        self.channels = channels

        # 내부 상태
        self._buffer: List[np.ndarray] = []
        self._is_recording = False

    @property
    def is_recording(self) -> bool:
        """녹음 중인지 반환"""
        return self._is_recording

    def start(self) -> None:
        """
        녹음 시작

        버퍼를 초기화하고 녹음 상태를 활성화합니다.
        """
        self._buffer = []
        self._is_recording = True

    def add_chunk(self, audio_chunk: np.ndarray) -> None:
        """
        오디오 청크 추가

        Args:
            audio_chunk: 오디오 데이터 (float32 배열)
        """
        self._buffer.append(audio_chunk.astype(np.float32))

    def stop(self) -> np.ndarray:
        """
        녹음 중지 및 오디오 반환

        Returns:
            연결된 오디오 데이터 (float32 배열)
        """
        self._is_recording = False

        if not self._buffer:
            return np.array([], dtype=np.float32)

        # 모든 청크 연결
        result = np.concatenate(self._buffer)
        return result

    def get_duration_seconds(self) -> float:
        """
        현재 버퍼의 녹음 시간 반환

        Returns:
            녹음 시간 (초)
        """
        if not self._buffer:
            return 0.0

        total_samples = sum(len(chunk) for chunk in self._buffer)
        return total_samples / self.sample_rate

    def to_wav_bytes(self, audio_data: np.ndarray) -> bytes:
        """
        오디오 데이터를 WAV 바이트로 변환

        Args:
            audio_data: 오디오 데이터 (float32 배열, -1.0 ~ 1.0)

        Returns:
            WAV 형식의 바이트 데이터
        """
        # float32 (-1.0 ~ 1.0)를 int16 (-32768 ~ 32767)로 변환
        audio_int16 = (audio_data * 32767).astype(np.int16)

        # 메모리 버퍼에 WAV 작성
        buffer = io.BytesIO()

        with wave.open(buffer, 'wb') as wav_file:
            wav_file.setnchannels(self.channels)
            wav_file.setsampwidth(2)  # 16-bit = 2 bytes
            wav_file.setframerate(self.sample_rate)
            wav_file.writeframes(audio_int16.tobytes())

        return buffer.getvalue()

    def clear(self) -> None:
        """버퍼 초기화"""
        self._buffer = []
        self._is_recording = False
