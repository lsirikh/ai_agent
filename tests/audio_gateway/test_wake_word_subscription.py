"""
Phase 36.2: Wake Word 구독 테스트

TDD Red Phase - G2 해결: Wake Word 감지 후 녹음 시작 로직
"""
import pytest
import sys
import os
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import json

# 서비스 경로 추가
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../services/audio_gateway'))


class TestWakeWordSubscriber:
    """Wake Word 이벤트 구독 테스트"""

    def test_wake_word_subscriber_function_exists(self):
        """
        wake_word_subscriber 함수가 main에 존재해야 함
        """
        from app import main

        assert hasattr(main, 'wake_word_subscriber'), "wake_word_subscriber 함수가 없음"

    def test_wake_word_channel_defined(self):
        """
        Wake Word 이벤트 채널이 정의되어 있어야 함
        """
        from app import main

        assert hasattr(main, 'WAKE_WORD_CHANNEL'), "WAKE_WORD_CHANNEL 상수가 없음"


class TestWakeWordEventHandling:
    """Wake Word 이벤트 처리 테스트"""

    @pytest.mark.asyncio
    async def test_wake_word_sets_listening_mode_true(self):
        """
        Wake Word 감지 이벤트 수신 시 listening_mode가 True로 설정되어야 함
        """
        from app import main

        # 초기 상태
        main._listening_mode = False

        # handle_wake_word_event 함수가 존재해야 함
        assert hasattr(main, 'handle_wake_word_event'), "handle_wake_word_event 함수가 없음"

        event_data = {
            "event": "wake_word_detected",
            "keyword": "에이전트",
            "confidence": 0.95
        }

        with patch.object(main, '_logger') as mock_logger:
            mock_logger.info = AsyncMock()

            await main.handle_wake_word_event(event_data)

            # listening_mode가 True가 되어야 함
            assert main._listening_mode is True

    @pytest.mark.asyncio
    async def test_wake_word_generates_session_id(self):
        """
        Wake Word 감지 시 새로운 session_id가 생성되어야 함
        """
        from app import main

        # _current_session 딕셔너리가 존재해야 함
        assert hasattr(main, '_current_session'), "_current_session이 없음"

        event_data = {
            "event": "wake_word_detected",
            "keyword": "에이전트"
        }

        with patch.object(main, '_logger') as mock_logger:
            mock_logger.info = AsyncMock()

            await main.handle_wake_word_event(event_data)

            # session_id가 생성되어야 함
            assert main._current_session.get("session_id") is not None
            assert len(main._current_session["session_id"]) > 0

    @pytest.mark.asyncio
    async def test_wake_word_logs_received_message(self):
        """
        Wake Word 감지 시 "Wake Word 수신완료" 로그가 기록되어야 함
        """
        from app import main

        event_data = {
            "event": "wake_word_detected",
            "keyword": "에이전트",
            "confidence": 0.92
        }

        with patch.object(main, '_logger') as mock_logger:
            mock_logger.info = AsyncMock()

            await main.handle_wake_word_event(event_data)

            # 로그 호출 확인
            mock_logger.info.assert_called()
            call_args_list = mock_logger.info.call_args_list

            # "wake_word_received" 이벤트가 로깅되어야 함
            event_names = [call[0][0] for call in call_args_list]
            assert "wake_word_received" in event_names


class TestLifespanWakeWordSubscriber:
    """lifespan에서 Wake Word Subscriber 시작 테스트"""

    def test_lifespan_starts_wake_word_subscriber(self):
        """
        lifespan에서 wake_word_subscriber 태스크가 시작되어야 함

        이 테스트는 코드 구조만 확인 (실제 asyncio 태스크 시작은 통합 테스트에서)
        """
        from app import main

        # wake_word_subscriber 함수가 async로 정의되어 있어야 함
        import asyncio
        assert asyncio.iscoroutinefunction(main.wake_word_subscriber)
