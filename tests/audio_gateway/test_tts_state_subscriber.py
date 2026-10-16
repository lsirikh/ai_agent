"""
Phase 35.3.2: TTS 상태 이벤트 구독 테스트

TDD Red Phase - TTS 상태 변경 시 PlaybackState 업데이트 테스트
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import sys
import os
import json
import asyncio

# 서비스 경로 추가
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../services/audio_gateway'))


class TestTTSStateSubscriberFunction:
    """TTS 상태 구독 함수 존재 테스트"""

    def test_tts_state_subscriber_function_exists(self):
        """
        tts_state_subscriber 함수가 main 모듈에 존재해야 함
        """
        from app import main

        assert hasattr(main, 'tts_state_subscriber'), \
            "main module should have 'tts_state_subscriber' function"

    @pytest.mark.asyncio
    async def test_tts_state_subscriber_is_async(self):
        """
        tts_state_subscriber 함수가 async 함수여야 함
        """
        from app import main

        # async 함수인지 확인
        assert asyncio.iscoroutinefunction(main.tts_state_subscriber), \
            "tts_state_subscriber should be an async function"


def create_mock_pubsub(messages):
    """헬퍼: 메시지 목록을 반환하는 mock pubsub 생성"""

    async def mock_listen():
        for msg in messages:
            yield msg
        # 메시지 처리 후 종료
        raise asyncio.CancelledError()

    mock_pubsub = AsyncMock()
    mock_pubsub.subscribe = AsyncMock()
    mock_pubsub.unsubscribe = AsyncMock()
    mock_pubsub.listen = mock_listen

    return mock_pubsub


def create_mock_logger():
    """헬퍼: mock logger 생성"""
    mock_logger = AsyncMock()
    mock_logger.info = AsyncMock()
    mock_logger.warning = AsyncMock()
    mock_logger.error = AsyncMock()
    mock_logger.debug = AsyncMock()
    return mock_logger


class TestTTSStatePlaybackControl:
    """TTS 상태에 따른 PlaybackState 제어 테스트"""

    @pytest.mark.asyncio
    async def test_tts_started_sets_playback_state_playing(self):
        """
        TTS 시작 이벤트 수신 시 PlaybackState.PLAYING으로 설정해야 함
        """
        from app.barge_in import BargeInDetector, PlaybackState
        from app import main

        # Setup - 새로운 detector 생성
        detector = BargeInDetector()
        detector.set_playback_state(PlaybackState.IDLE)

        # TTS 시작 메시지 시뮬레이션
        tts_started_message = {
            "type": "message",
            "data": json.dumps({
                "event": "tts_started",
                "session_id": "test-session"
            }).encode()
        }

        mock_pubsub = create_mock_pubsub([tts_started_message])
        mock_redis = MagicMock()
        mock_redis.pubsub.return_value = mock_pubsub
        mock_logger = create_mock_logger()

        # 전역 변수 패치
        original_detector = main.barge_in_detector
        original_redis = main.redis_client
        original_logger = main._logger

        try:
            main.barge_in_detector = detector
            main.redis_client = mock_redis
            main._logger = mock_logger

            try:
                await asyncio.wait_for(
                    main.tts_state_subscriber(),
                    timeout=1.0
                )
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass

            # TTS 시작 후 PLAYING 상태여야 함
            assert detector.playback_state == PlaybackState.PLAYING, \
                "PlaybackState should be PLAYING after TTS started"
        finally:
            main.barge_in_detector = original_detector
            main.redis_client = original_redis
            main._logger = original_logger

    @pytest.mark.asyncio
    async def test_tts_complete_sets_playback_state_idle(self):
        """
        TTS 완료 이벤트 수신 시 PlaybackState.IDLE로 설정해야 함
        """
        from app.barge_in import BargeInDetector, PlaybackState
        from app import main

        # Setup - 초기 PLAYING 상태
        detector = BargeInDetector()
        detector.set_playback_state(PlaybackState.PLAYING)

        # TTS 완료 메시지 시뮬레이션
        tts_complete_message = {
            "type": "message",
            "data": json.dumps({
                "event": "tts_complete",
                "session_id": "test-session"
            }).encode()
        }

        mock_pubsub = create_mock_pubsub([tts_complete_message])
        mock_redis = MagicMock()
        mock_redis.pubsub.return_value = mock_pubsub
        mock_logger = create_mock_logger()

        original_detector = main.barge_in_detector
        original_redis = main.redis_client
        original_logger = main._logger

        try:
            main.barge_in_detector = detector
            main.redis_client = mock_redis
            main._logger = mock_logger

            try:
                await asyncio.wait_for(
                    main.tts_state_subscriber(),
                    timeout=1.0
                )
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass

            # TTS 완료 후 IDLE 상태여야 함
            assert detector.playback_state == PlaybackState.IDLE, \
                "PlaybackState should be IDLE after TTS complete"
        finally:
            main.barge_in_detector = original_detector
            main.redis_client = original_redis
            main._logger = original_logger


class TestTTSStateAECIntegration:
    """TTS 상태 변경 시 AEC 연동 테스트"""

    @pytest.mark.asyncio
    async def test_tts_complete_clears_aec_reference(self):
        """
        TTS 완료 이벤트 수신 시 AEC playback reference를 초기화해야 함
        """
        from app.aec import AcousticEchoCanceller
        from app.barge_in import BargeInDetector, PlaybackState
        from app import main
        import numpy as np

        # Setup
        aec_instance = AcousticEchoCanceller()
        # 먼저 playback reference 설정
        dummy_audio = np.ones(1600, dtype=np.float32) * 0.5
        aec_instance.set_playback_reference(dummy_audio)

        assert aec_instance.has_playback_reference is True, \
            "AEC should have playback reference before test"

        detector = BargeInDetector()
        detector.set_playback_state(PlaybackState.PLAYING)

        # TTS 완료 메시지
        tts_complete_message = {
            "type": "message",
            "data": json.dumps({
                "event": "tts_complete",
                "session_id": "test-session"
            }).encode()
        }

        mock_pubsub = create_mock_pubsub([tts_complete_message])
        mock_redis = MagicMock()
        mock_redis.pubsub.return_value = mock_pubsub
        mock_logger = create_mock_logger()

        original_detector = main.barge_in_detector
        original_aec = main.aec
        original_redis = main.redis_client
        original_logger = main._logger

        try:
            main.barge_in_detector = detector
            main.aec = aec_instance
            main.redis_client = mock_redis
            main._logger = mock_logger

            try:
                await asyncio.wait_for(
                    main.tts_state_subscriber(),
                    timeout=1.0
                )
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass

            # TTS 완료 후 AEC reference가 초기화되어야 함
            assert aec_instance.has_playback_reference is False, \
                "AEC playback reference should be cleared after TTS complete"
        finally:
            main.barge_in_detector = original_detector
            main.aec = original_aec
            main.redis_client = original_redis
            main._logger = original_logger