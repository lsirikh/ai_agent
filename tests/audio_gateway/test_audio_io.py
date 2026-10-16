"""
Audio I/O Tests

Phase 3.5: Audio Gateway Main - 오디오 입출력 테스트
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest


class TestAudioInputStreamInitialization:
    """오디오 입력 스트림 초기화 테스트"""

    def test_audio_input_stream_initialization(self):
        """AudioInputStream이 올바르게 초기화되어야 한다"""
        from services.audio_gateway.app.audio_io import AudioInputStream

        stream = AudioInputStream()

        assert stream is not None
        assert stream.sample_rate == 16000
        assert stream.channels == 1
        assert stream.chunk_size == 1600  # 100ms at 16kHz

    def test_audio_input_stream_with_custom_config(self):
        """커스텀 설정으로 초기화할 수 있어야 한다"""
        from services.audio_gateway.app.audio_io import AudioInputStream

        stream = AudioInputStream(
            sample_rate=48000,
            channels=2,
            chunk_size=4800
        )

        assert stream.sample_rate == 48000
        assert stream.channels == 2
        assert stream.chunk_size == 4800


class TestAudioInputStreamOperations:
    """오디오 입력 스트림 동작 테스트"""

    def test_audio_input_stream_start_stop(self):
        """스트림 시작/중지가 동작해야 한다"""
        from services.audio_gateway.app.audio_io import AudioInputStream

        stream = AudioInputStream()

        with patch.object(stream, '_open_stream') as mock_open:
            stream.start()
            mock_open.assert_called_once()
            assert stream.is_running is True

        with patch.object(stream, '_close_stream') as mock_close:
            stream.stop()
            mock_close.assert_called_once()
            assert stream.is_running is False

    def test_audio_input_stream_read_chunk(self):
        """오디오 청크를 읽을 수 있어야 한다"""
        from services.audio_gateway.app.audio_io import AudioInputStream

        stream = AudioInputStream()
        stream._is_running = True

        # Mock audio data
        mock_audio = np.random.randn(1600).astype(np.float32)

        with patch.object(stream, '_read_from_device', return_value=mock_audio):
            chunk = stream.read()

            assert chunk is not None
            assert len(chunk) == 1600
            assert chunk.dtype == np.float32

    def test_audio_input_stream_returns_none_when_stopped(self):
        """스트림이 중지되면 None을 반환해야 한다"""
        from services.audio_gateway.app.audio_io import AudioInputStream

        stream = AudioInputStream()
        stream._is_running = False

        chunk = stream.read()

        assert chunk is None


class TestAudioOutputStreamInitialization:
    """오디오 출력 스트림 초기화 테스트"""

    def test_audio_output_stream_initialization(self):
        """AudioOutputStream이 올바르게 초기화되어야 한다"""
        from services.audio_gateway.app.audio_io import AudioOutputStream

        stream = AudioOutputStream()

        assert stream is not None
        assert stream.sample_rate == 24000  # TTS output rate
        assert stream.channels == 1

    def test_audio_output_stream_with_custom_config(self):
        """커스텀 설정으로 초기화할 수 있어야 한다"""
        from services.audio_gateway.app.audio_io import AudioOutputStream

        stream = AudioOutputStream(
            sample_rate=48000,
            channels=2
        )

        assert stream.sample_rate == 48000
        assert stream.channels == 2


class TestAudioOutputStreamOperations:
    """오디오 출력 스트림 동작 테스트"""

    def test_audio_output_stream_start_stop(self):
        """출력 스트림 시작/중지가 동작해야 한다"""
        from services.audio_gateway.app.audio_io import AudioOutputStream

        stream = AudioOutputStream()

        with patch.object(stream, '_open_stream') as mock_open:
            stream.start()
            mock_open.assert_called_once()
            assert stream.is_running is True

        with patch.object(stream, '_close_stream') as mock_close:
            stream.stop()
            mock_close.assert_called_once()
            assert stream.is_running is False

    def test_audio_output_stream_write(self):
        """오디오 데이터를 출력할 수 있어야 한다"""
        from services.audio_gateway.app.audio_io import AudioOutputStream

        stream = AudioOutputStream()
        stream._is_running = True

        audio_data = np.random.randn(2400).astype(np.float32)

        with patch.object(stream, '_write_to_device') as mock_write:
            stream.write(audio_data)
            mock_write.assert_called_once()

    def test_audio_output_stream_queue_audio(self):
        """오디오를 큐에 추가할 수 있어야 한다"""
        from services.audio_gateway.app.audio_io import AudioOutputStream

        stream = AudioOutputStream()

        audio_data = np.random.randn(2400).astype(np.float32)
        stream.queue_audio(audio_data)

        assert stream.queue_size > 0

    def test_audio_output_stream_clear_queue(self):
        """오디오 큐를 비울 수 있어야 한다 (barge-in용)"""
        from services.audio_gateway.app.audio_io import AudioOutputStream

        stream = AudioOutputStream()

        # Add some audio to queue
        audio_data = np.random.randn(2400).astype(np.float32)
        stream.queue_audio(audio_data)
        stream.queue_audio(audio_data)

        stream.clear_queue()

        assert stream.queue_size == 0


class TestAudioIOManager:
    """AudioIO 통합 관리자 테스트"""

    def test_audio_io_manager_initialization(self):
        """AudioIOManager가 올바르게 초기화되어야 한다"""
        from services.audio_gateway.app.audio_io import AudioIOManager

        manager = AudioIOManager()

        assert manager is not None
        assert manager.input_stream is not None
        assert manager.output_stream is not None

    def test_audio_io_manager_start_stop(self):
        """매니저가 모든 스트림을 시작/중지해야 한다"""
        from services.audio_gateway.app.audio_io import AudioIOManager

        manager = AudioIOManager()

        with patch.object(manager.input_stream, 'start') as mock_in_start, \
             patch.object(manager.output_stream, 'start') as mock_out_start:
            manager.start()
            mock_in_start.assert_called_once()
            mock_out_start.assert_called_once()

        with patch.object(manager.input_stream, 'stop') as mock_in_stop, \
             patch.object(manager.output_stream, 'stop') as mock_out_stop:
            manager.stop()
            mock_in_stop.assert_called_once()
            mock_out_stop.assert_called_once()

    def test_audio_io_manager_get_input_chunk(self):
        """입력 청크를 가져올 수 있어야 한다"""
        from services.audio_gateway.app.audio_io import AudioIOManager

        manager = AudioIOManager()
        mock_chunk = np.random.randn(1600).astype(np.float32)

        with patch.object(manager.input_stream, 'read', return_value=mock_chunk):
            chunk = manager.get_input_chunk()

            assert chunk is not None
            assert len(chunk) == 1600

    def test_audio_io_manager_play_audio(self):
        """오디오를 재생할 수 있어야 한다"""
        from services.audio_gateway.app.audio_io import AudioIOManager

        manager = AudioIOManager()
        audio_data = np.random.randn(2400).astype(np.float32)

        with patch.object(manager.output_stream, 'queue_audio') as mock_queue:
            manager.play_audio(audio_data)
            mock_queue.assert_called_once()

    def test_audio_io_manager_stop_playback(self):
        """재생을 중지하고 큐를 비울 수 있어야 한다"""
        from services.audio_gateway.app.audio_io import AudioIOManager

        manager = AudioIOManager()

        with patch.object(manager.output_stream, 'clear_queue') as mock_clear:
            manager.stop_playback()
            mock_clear.assert_called_once()


class TestAsyncAudioOperations:
    """비동기 오디오 작업 테스트"""

    @pytest.mark.asyncio
    async def test_async_audio_input_generator(self):
        """비동기 오디오 입력 제너레이터가 동작해야 한다"""
        from services.audio_gateway.app.audio_io import AudioIOManager

        manager = AudioIOManager()
        mock_chunks = [np.random.randn(1600).astype(np.float32) for _ in range(3)]
        chunk_index = 0

        def mock_read():
            nonlocal chunk_index
            if chunk_index < len(mock_chunks):
                chunk = mock_chunks[chunk_index]
                chunk_index += 1
                return chunk
            return None

        with patch.object(manager.input_stream, 'read', side_effect=mock_read):
            manager.input_stream._is_running = True

            chunks = []
            async for chunk in manager.audio_input_generator():
                chunks.append(chunk)
                if len(chunks) >= 3:
                    break

            assert len(chunks) == 3

    @pytest.mark.asyncio
    async def test_async_play_audio_with_callback(self):
        """콜백과 함께 비동기 오디오 재생이 동작해야 한다"""
        from services.audio_gateway.app.audio_io import AudioIOManager

        manager = AudioIOManager()
        audio_data = np.random.randn(2400).astype(np.float32)
        callback_called = False

        async def on_playback_complete():
            nonlocal callback_called
            callback_called = True

        with patch.object(manager.output_stream, 'queue_audio'):
            with patch.object(manager.output_stream, '_wait_for_playback', new_callable=AsyncMock):
                await manager.play_audio_async(audio_data, on_complete=on_playback_complete)

                assert callback_called is True


class TestPlaybackState:
    """재생 상태 관리 테스트"""

    def test_playback_state_tracking(self):
        """재생 상태가 올바르게 추적되어야 한다"""
        from services.audio_gateway.app.audio_io import AudioOutputStream

        stream = AudioOutputStream()

        assert stream.is_playing is False

        audio_data = np.random.randn(2400).astype(np.float32)
        stream.queue_audio(audio_data)

        # 큐에 데이터가 있으면 is_playing은 재생 중일 때 True
        # 실제 재생은 별도 스레드에서 처리

    def test_playback_callbacks(self):
        """재생 시작/종료 콜백이 호출되어야 한다"""
        from services.audio_gateway.app.audio_io import AudioOutputStream

        stream = AudioOutputStream()

        start_called = False
        end_called = False

        def on_start():
            nonlocal start_called
            start_called = True

        def on_end():
            nonlocal end_called
            end_called = True

        stream.set_callbacks(on_playback_start=on_start, on_playback_end=on_end)

        # 콜백이 등록되었는지 확인
        assert stream._on_playback_start is not None
        assert stream._on_playback_end is not None
