"""
Audio I/O

Phase 3.5: Audio Gateway Main - 오디오 입출력 관리
Phase 37: Real-time microphone/speaker access via sounddevice
"""
import asyncio
import logging
import os
import queue
import threading
from typing import Any, AsyncIterator, Callable, Optional

import numpy as np

# Phase 37: sounddevice import with fallback
try:
    import sounddevice as sd
    SOUNDDEVICE_AVAILABLE = True
except ImportError:
    SOUNDDEVICE_AVAILABLE = False

logger = logging.getLogger(__name__)


class AudioInputStream:
    """
    오디오 입력 스트림

    Phase 37: sounddevice를 사용한 실제 마이크 입력 구현

    Attributes:
        sample_rate: 오디오 샘플레이트
        channels: 채널 수
        chunk_size: 청크 크기 (샘플 수)
        device: 오디오 입력 디바이스
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        channels: int = 1,
        chunk_size: int = 1600,  # 100ms at 16kHz
        device: Optional[str] = None
    ):
        """
        AudioInputStream 초기화

        Args:
            sample_rate: 오디오 샘플레이트 (Hz)
            channels: 채널 수
            chunk_size: 청크 크기 (샘플 수)
            device: 오디오 디바이스 (None=default, 'hw:0,0' 형식)
        """
        self.sample_rate = sample_rate
        self.channels = channels
        self.chunk_size = chunk_size

        # Phase 37: 디바이스 설정
        self._device = device
        if device == "default" or device is None:
            self._device = None  # sounddevice 기본값 사용

        self._is_running = False
        self._stream: Optional[Any] = None
        self._audio_queue: queue.Queue = queue.Queue(maxsize=100)
        self._overflow_count = 0

    @property
    def is_running(self) -> bool:
        """스트림이 실행 중인지 반환"""
        return self._is_running

    def _audio_callback(
        self,
        indata: np.ndarray,
        frames: int,
        time_info: Any,
        status: Any
    ) -> None:
        """
        sounddevice 콜백 - 오디오 데이터를 큐에 추가

        Phase 37: 실제 마이크 콜백 구현
        """
        if status:
            logger.warning(f"Audio input status: {status}")

        # float32로 변환하여 큐에 추가
        audio = indata.copy().flatten().astype(np.float32)

        try:
            self._audio_queue.put_nowait(audio)
        except queue.Full:
            self._overflow_count += 1
            if self._overflow_count % 100 == 0:
                logger.warning(
                    f"Audio queue overflow (dropped {self._overflow_count} frames)"
                )

    def start(self) -> None:
        """입력 스트림 시작"""
        if not SOUNDDEVICE_AVAILABLE:
            logger.warning("sounddevice not available, using mock mode")
            self._is_running = True
            return

        try:
            logger.info(
                f"Starting audio input: device={self._device}, "
                f"rate={self.sample_rate}, chunk={self.chunk_size}"
            )

            self._stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype=np.float32,
                blocksize=self.chunk_size,
                device=self._device,
                callback=self._audio_callback
            )
            self._stream.start()
            self._is_running = True
            logger.info("Audio input stream started successfully")

        except Exception as e:
            logger.error(f"Failed to start audio input: {e}")
            # 실패해도 mock 모드로 계속 동작
            self._is_running = True

    def stop(self) -> None:
        """입력 스트림 중지"""
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception as e:
                logger.warning(f"Error stopping audio stream: {e}")
            self._stream = None

        self._is_running = False
        logger.info("Audio input stream stopped")

    def read(self) -> Optional[np.ndarray]:
        """
        오디오 청크 읽기 (동기)

        Returns:
            오디오 데이터 (float32) 또는 None (스트림 중지 시)
        """
        if not self._is_running:
            return None

        try:
            return self._audio_queue.get(timeout=0.1)
        except queue.Empty:
            return None

    async def read_async(self) -> Optional[np.ndarray]:
        """
        비동기 오디오 청크 읽기

        Phase 37: 비동기 컨텍스트에서 사용

        Returns:
            오디오 데이터 (float32) 또는 None
        """
        if not self._is_running:
            return None

        try:
            # 논블로킹으로 큐에서 가져오기
            return self._audio_queue.get_nowait()
        except queue.Empty:
            # 짧은 대기 후 재시도
            await asyncio.sleep(0.01)
            try:
                return self._audio_queue.get_nowait()
            except queue.Empty:
                return None


class AudioOutputStream:
    """
    오디오 출력 스트림

    Phase 37: sounddevice를 사용한 실제 스피커 출력 구현

    Attributes:
        sample_rate: 오디오 샘플레이트
        channels: 채널 수
        device: 오디오 출력 디바이스
    """

    def __init__(
        self,
        sample_rate: int = 24000,  # TTS output rate
        channels: int = 1,
        device: Optional[str] = None
    ):
        """
        AudioOutputStream 초기화

        Args:
            sample_rate: 오디오 샘플레이트 (Hz)
            channels: 채널 수
            device: 오디오 디바이스 (None=default)
        """
        self.sample_rate = sample_rate
        self.channels = channels

        # Phase 37: 디바이스 설정
        self._device = device
        if device == "default" or device is None:
            self._device = None

        self._is_running = False
        self._stream: Optional[Any] = None
        self._audio_queue: queue.Queue = queue.Queue()
        self._is_playing = False
        self._playback_thread: Optional[threading.Thread] = None

        # 콜백
        self._on_playback_start: Optional[Callable] = None
        self._on_playback_end: Optional[Callable] = None

    @property
    def is_running(self) -> bool:
        """스트림이 실행 중인지 반환"""
        return self._is_running

    @property
    def is_playing(self) -> bool:
        """현재 재생 중인지 반환"""
        return self._is_playing

    @property
    def queue_size(self) -> int:
        """큐에 있는 오디오 청크 수"""
        return self._audio_queue.qsize()

    def _playback_worker(self) -> None:
        """
        재생 워커 스레드

        Phase 37: 큐에서 오디오를 가져와 재생
        """
        while self._is_running:
            try:
                audio = self._audio_queue.get(timeout=0.1)

                if not self._is_playing:
                    self._is_playing = True
                    if self._on_playback_start:
                        self._on_playback_start()

                self._write_to_device(audio)

                if self._audio_queue.empty():
                    self._is_playing = False
                    if self._on_playback_end:
                        self._on_playback_end()

            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Playback error: {e}")

    def start(self) -> None:
        """출력 스트림 시작"""
        if not SOUNDDEVICE_AVAILABLE:
            logger.warning("sounddevice not available, using mock mode")
            self._is_running = True
            return

        try:
            logger.info(
                f"Starting audio output: device={self._device}, "
                f"rate={self.sample_rate}"
            )

            self._is_running = True

            # 재생 워커 스레드 시작
            self._playback_thread = threading.Thread(
                target=self._playback_worker,
                daemon=True
            )
            self._playback_thread.start()

            logger.info("Audio output stream started successfully")

        except Exception as e:
            logger.error(f"Failed to start audio output: {e}")
            self._is_running = True  # mock 모드

    def stop(self) -> None:
        """출력 스트림 중지"""
        self._is_running = False

        if self._playback_thread is not None:
            self._playback_thread.join(timeout=1.0)
            self._playback_thread = None

        logger.info("Audio output stream stopped")

    def _write_to_device(self, audio: np.ndarray) -> None:
        """
        오디오 디바이스에 데이터 쓰기

        Phase 37: sounddevice.play() 사용

        Args:
            audio: 오디오 데이터
        """
        if not SOUNDDEVICE_AVAILABLE:
            return

        try:
            # sounddevice.play()는 블로킹이므로 재생 완료까지 대기
            sd.play(audio.astype(np.float32), self.sample_rate, device=self._device)
            sd.wait()
        except Exception as e:
            logger.error(f"Error writing to audio device: {e}")

    async def _wait_for_playback(self) -> None:
        """재생 완료 대기"""
        while not self._audio_queue.empty() or self._is_playing:
            await asyncio.sleep(0.01)

    def write(self, audio: np.ndarray) -> None:
        """
        오디오 데이터 직접 출력 (동기)

        Args:
            audio: 오디오 데이터 (float32)
        """
        if not self._is_running:
            return

        self._write_to_device(audio)

    def queue_audio(self, audio: np.ndarray) -> None:
        """
        오디오를 재생 큐에 추가

        Args:
            audio: 오디오 데이터 (float32)
        """
        self._audio_queue.put(audio)

    def clear_queue(self) -> None:
        """
        재생 큐 비우기 (barge-in 시 사용)
        """
        while not self._audio_queue.empty():
            try:
                self._audio_queue.get_nowait()
            except queue.Empty:
                break

        self._is_playing = False

        # 현재 재생 중인 오디오도 중지
        if SOUNDDEVICE_AVAILABLE:
            try:
                sd.stop()
            except Exception:
                pass

    def set_callbacks(
        self,
        on_playback_start: Optional[Callable] = None,
        on_playback_end: Optional[Callable] = None
    ) -> None:
        """
        재생 콜백 설정

        Args:
            on_playback_start: 재생 시작 콜백
            on_playback_end: 재생 종료 콜백
        """
        self._on_playback_start = on_playback_start
        self._on_playback_end = on_playback_end


class AudioIOManager:
    """
    오디오 I/O 통합 관리자

    Phase 37: 환경 변수 기반 디바이스 설정 지원

    입력 스트림과 출력 스트림을 통합 관리합니다.
    """

    def __init__(
        self,
        input_sample_rate: int = 16000,
        output_sample_rate: int = 24000,
        input_chunk_size: int = 1600,
        input_device: Optional[str] = None,
        output_device: Optional[str] = None
    ):
        """
        AudioIOManager 초기화

        Args:
            input_sample_rate: 입력 샘플레이트
            output_sample_rate: 출력 샘플레이트
            input_chunk_size: 입력 청크 크기
            input_device: 입력 디바이스 (환경 변수 우선)
            output_device: 출력 디바이스 (환경 변수 우선)
        """
        # Phase 37: 환경 변수에서 디바이스 설정 로드
        self._input_device = os.getenv("AUDIO_INPUT_DEVICE", input_device)
        self._output_device = os.getenv("AUDIO_OUTPUT_DEVICE", output_device)

        # 샘플레이트/청크 크기도 환경 변수에서 로드
        input_sample_rate = int(os.getenv("AUDIO_SAMPLE_RATE", str(input_sample_rate)))
        input_chunk_size = int(os.getenv("AUDIO_CHUNK_SIZE", str(input_chunk_size)))

        self.input_stream = AudioInputStream(
            sample_rate=input_sample_rate,
            chunk_size=input_chunk_size,
            device=self._input_device
        )
        self.output_stream = AudioOutputStream(
            sample_rate=output_sample_rate,
            device=self._output_device
        )

        logger.info(
            f"AudioIOManager initialized: "
            f"input_device={self._input_device}, "
            f"output_device={self._output_device}, "
            f"input_rate={input_sample_rate}, "
            f"output_rate={output_sample_rate}, "
            f"chunk_size={input_chunk_size}"
        )

    def start(self) -> None:
        """모든 스트림 시작"""
        self.input_stream.start()
        self.output_stream.start()

    def stop(self) -> None:
        """모든 스트림 중지"""
        self.input_stream.stop()
        self.output_stream.stop()

    def get_input_chunk(self) -> Optional[np.ndarray]:
        """
        입력 오디오 청크 가져오기

        Returns:
            오디오 데이터 또는 None
        """
        return self.input_stream.read()

    async def get_input_chunk_async(self) -> Optional[np.ndarray]:
        """
        비동기 입력 오디오 청크 가져오기

        Phase 37: 비동기 컨텍스트용

        Returns:
            오디오 데이터 또는 None
        """
        return await self.input_stream.read_async()

    def play_audio(self, audio: np.ndarray) -> None:
        """
        오디오 재생 큐에 추가

        Args:
            audio: 오디오 데이터
        """
        self.output_stream.queue_audio(audio)

    def stop_playback(self) -> None:
        """
        재생 중지 및 큐 비우기
        """
        self.output_stream.clear_queue()

    async def audio_input_generator(self) -> AsyncIterator[np.ndarray]:
        """
        비동기 오디오 입력 제너레이터

        Yields:
            오디오 청크
        """
        while self.input_stream.is_running:
            chunk = await self.input_stream.read_async()
            if chunk is not None:
                yield chunk
            else:
                await asyncio.sleep(0.01)

    async def play_audio_async(
        self,
        audio: np.ndarray,
        on_complete: Optional[Callable] = None
    ) -> None:
        """
        비동기 오디오 재생

        Args:
            audio: 오디오 데이터
            on_complete: 재생 완료 콜백
        """
        self.output_stream.queue_audio(audio)
        await self.output_stream._wait_for_playback()

        if on_complete:
            await on_complete()


def list_audio_devices() -> dict:
    """
    사용 가능한 오디오 디바이스 목록 반환

    Phase 37: 디바이스 디버깅용

    Returns:
        디바이스 정보 딕셔너리
    """
    if not SOUNDDEVICE_AVAILABLE:
        return {"error": "sounddevice not available"}

    try:
        devices = sd.query_devices()
        default_input = sd.default.device[0]
        default_output = sd.default.device[1]

        return {
            "devices": [
                {
                    "index": i,
                    "name": d["name"],
                    "hostapi": d["hostapi"],
                    "max_input_channels": d["max_input_channels"],
                    "max_output_channels": d["max_output_channels"],
                    "default_samplerate": d["default_samplerate"],
                    "is_default_input": i == default_input,
                    "is_default_output": i == default_output
                }
                for i, d in enumerate(devices)
            ],
            "default_input": default_input,
            "default_output": default_output
        }
    except Exception as e:
        return {"error": str(e)}
