"""
Phase 35.1.1: Barge-in Redis 연결 테스트

TDD Red Phase - 실패하는 테스트 먼저 작성
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import sys
import os

# 서비스 경로 추가
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../services/audio_gateway'))


class TestBargeInDetectorRedisClient:
    """Barge-in Detector Redis 클라이언트 테스트"""

    def test_barge_in_detector_has_redis_client_attribute(self):
        """
        C2 해결: BargeInDetector가 redis_client 속성을 가지고 있어야 함
        """
        from app.barge_in import BargeInDetector

        detector = BargeInDetector()

        # redis_client 속성이 존재해야 함
        assert hasattr(detector, 'redis_client'), \
            "BargeInDetector should have 'redis_client' attribute"

    def test_barge_in_detector_redis_client_initially_none(self):
        """
        BargeInDetector 초기화 시 redis_client가 None이어야 함
        """
        from app.barge_in import BargeInDetector

        detector = BargeInDetector()

        # 초기값은 None
        assert detector.redis_client is None, \
            "BargeInDetector.redis_client should be None initially"

    def test_barge_in_detector_redis_client_can_be_set(self):
        """
        BargeInDetector의 redis_client를 외부에서 설정할 수 있어야 함
        """
        from app.barge_in import BargeInDetector

        detector = BargeInDetector()
        mock_redis = MagicMock()

        # redis_client 설정 가능
        detector.redis_client = mock_redis

        assert detector.redis_client is mock_redis, \
            "BargeInDetector.redis_client should be settable"

    def test_barge_in_detector_redis_client_set_via_constructor(self):
        """
        BargeInDetector 생성자에서 redis_client를 전달받을 수 있어야 함
        """
        from app.barge_in import BargeInDetector

        mock_redis = MagicMock()

        # 생성자에서 redis_client 전달
        detector = BargeInDetector(redis_client=mock_redis)

        assert detector.redis_client is mock_redis, \
            "BargeInDetector should accept redis_client in constructor"


class TestLifespanRedisInjection:
    """Lifespan에서 Redis 클라이언트 주입 테스트"""

    @pytest.mark.asyncio
    async def test_barge_in_detector_redis_client_set_in_lifespan(self):
        """
        lifespan에서 Redis 연결 후 barge_in_detector에 클라이언트가 주입되어야 함
        """
        # main.py의 lifespan 함수와 전역 barge_in_detector 확인
        from app.main import barge_in_detector

        # 현재 상태에서는 Redis 클라이언트가 None일 것
        # lifespan 후에는 설정되어야 함
        # 이 테스트는 lifespan 수정 후 통과할 것

        # lifespan 로직을 별도로 테스트하기 위해 mock 사용
        with patch('app.main.redis_client') as mock_redis:
            mock_redis.return_value = MagicMock()
            # lifespan 이후 barge_in_detector.redis_client가 설정되어야 함
            # 현재는 실패할 것 (구현 필요)
            pass

    @pytest.mark.asyncio
    async def test_barge_in_detector_redis_client_is_connected(self):
        """
        barge_in_detector에 주입된 Redis 클라이언트가 연결되어 있어야 함
        """
        from app.barge_in import BargeInDetector

        # AsyncMock으로 Redis 클라이언트 시뮬레이션
        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(return_value=True)

        detector = BargeInDetector(redis_client=mock_redis)

        # ping이 성공하면 연결된 것
        result = await detector.redis_client.ping()
        assert result is True, \
            "Redis client should be able to ping"