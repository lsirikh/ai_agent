"""
Phase 35.7.1: AudioRecorder 클래스 테스트

TDD Red Phase - H2 해결: STT 호출 연동을 위한 오디오 녹음기
"""
import pytest
import sys
import os
import numpy as np
import io
import wave

# 서비스 경로 추가
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../services/audio_gateway'))


class TestAudioRecorderClass:
    """AudioRecorder 클래스 존재 테스트"""

    def test_audio_recorder_class_exists(self):
        """
        AudioRecorder 클래스가 audio_recorder 모듈에 존재해야 함
        """
        from app.audio_recorder import AudioRecorder

        assert AudioRecorder is not None

    def test_audio_recorder_init_with_sample_rate(self):
        """
        AudioRecorder가 sample_rate 파라미터로 초기화되어야 함
        """
        from app.audio_recorder import AudioRecorder

        recorder = AudioRecorder(sample_rate=16000)

        assert recorder.sample_rate == 16000


class TestAudioRecorderRecording:
    """AudioRecorder 녹음 기능 테스트"""

    def test_audio_recorder_start_clears_buffer(self):
        """
        start() 호출 시 버퍼가 초기화되어야 함
        """
        from app.audio_recorder import AudioRecorder

        recorder = AudioRecorder()

        # 먼저 청크 추가
        chunk = np.ones(1600, dtype=np.float32)
        recorder.add_chunk(chunk)

        # start() 호출
        recorder.start()

        # 버퍼가 비어있어야 함
        assert len(recorder._buffer) == 0

    def test_audio_recorder_add_chunk_appends_to_buffer(self):
        """
        add_chunk() 호출 시 버퍼에 오디오 데이터가 추가되어야 함
        """
        from app.audio_recorder import AudioRecorder

        recorder = AudioRecorder()
        recorder.start()

        chunk1 = np.ones(1600, dtype=np.float32) * 0.5
        chunk2 = np.ones(1600, dtype=np.float32) * 0.3

        recorder.add_chunk(chunk1)
        recorder.add_chunk(chunk2)

        # 버퍼에 2개 청크가 추가되어야 함
        assert len(recorder._buffer) == 2

    def test_audio_recorder_stop_returns_concatenated_audio(self):
        """
        stop() 호출 시 모든 청크가 연결된 오디오 데이터를 반환해야 함
        """
        from app.audio_recorder import AudioRecorder

        recorder = AudioRecorder()
        recorder.start()

        chunk1 = np.ones(1600, dtype=np.float32) * 0.5
        chunk2 = np.ones(800, dtype=np.float32) * 0.3

        recorder.add_chunk(chunk1)
        recorder.add_chunk(chunk2)

        result = recorder.stop()

        # 결과가 numpy array
        assert isinstance(result, np.ndarray)
        # 전체 길이가 합쳐진 것과 같아야 함
        assert len(result) == 2400
        # float32 타입
        assert result.dtype == np.float32

    def test_audio_recorder_is_recording_property(self):
        """
        is_recording 프로퍼티가 녹음 상태를 반환해야 함
        """
        from app.audio_recorder import AudioRecorder

        recorder = AudioRecorder()

        assert recorder.is_recording is False

        recorder.start()
        assert recorder.is_recording is True

        recorder.stop()
        assert recorder.is_recording is False


class TestAudioRecorderWavConversion:
    """AudioRecorder WAV 변환 테스트"""

    def test_audio_recorder_to_wav_bytes_returns_valid_wav(self):
        """
        to_wav_bytes() 메서드가 유효한 WAV 바이트를 반환해야 함
        """
        from app.audio_recorder import AudioRecorder

        recorder = AudioRecorder(sample_rate=16000)
        recorder.start()

        # 오디오 청크 추가
        chunk = np.sin(np.linspace(0, 2 * np.pi, 1600)).astype(np.float32)
        recorder.add_chunk(chunk)

        audio_data = recorder.stop()
        wav_bytes = recorder.to_wav_bytes(audio_data)

        # 바이트 타입
        assert isinstance(wav_bytes, bytes)

        # WAV 헤더 확인 (RIFF)
        assert wav_bytes[:4] == b'RIFF'

        # WAV 포맷 확인
        assert wav_bytes[8:12] == b'WAVE'

    def test_audio_recorder_to_wav_bytes_has_correct_sample_rate(self):
        """
        to_wav_bytes()가 올바른 샘플레이트로 WAV를 생성해야 함
        """
        from app.audio_recorder import AudioRecorder

        recorder = AudioRecorder(sample_rate=16000)
        recorder.start()

        chunk = np.ones(1600, dtype=np.float32) * 0.5
        recorder.add_chunk(chunk)

        audio_data = recorder.stop()
        wav_bytes = recorder.to_wav_bytes(audio_data)

        # WAV 파일로 읽어서 샘플레이트 확인
        with wave.open(io.BytesIO(wav_bytes), 'rb') as wav_file:
            assert wav_file.getframerate() == 16000
            assert wav_file.getnchannels() == 1  # 모노
            assert wav_file.getsampwidth() == 2  # 16-bit


class TestAudioRecorderDuration:
    """AudioRecorder 녹음 시간 테스트"""

    def test_audio_recorder_get_duration_seconds(self):
        """
        get_duration_seconds() 메서드가 녹음 시간을 반환해야 함
        """
        from app.audio_recorder import AudioRecorder

        recorder = AudioRecorder(sample_rate=16000)
        recorder.start()

        # 1초분량 오디오 (16000 samples @ 16kHz)
        chunk = np.ones(16000, dtype=np.float32)
        recorder.add_chunk(chunk)

        duration = recorder.get_duration_seconds()

        assert abs(duration - 1.0) < 0.01  # 약 1초

    def test_audio_recorder_empty_returns_zero_duration(self):
        """
        버퍼가 비어있을 때 0을 반환해야 함
        """
        from app.audio_recorder import AudioRecorder

        recorder = AudioRecorder()
        recorder.start()

        duration = recorder.get_duration_seconds()

        assert duration == 0.0
