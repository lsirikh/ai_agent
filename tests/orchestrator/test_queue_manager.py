"""
Sentence Queue Manager Tests

Phase 2.1: 문장 큐 관리자 테스트
LLM 토큰 스트리밍을 문장 단위로 분리하여 TTS로 전달
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestQueueManagerInitialization:
    """SentenceQueueManager 초기화 테스트"""

    def test_queue_manager_initialization(self):
        """기본 설정으로 초기화되어야 한다"""
        from services.orchestrator.app.queue_manager import SentenceQueueManager

        manager = SentenceQueueManager()

        assert manager is not None
        assert manager.min_sentence_length > 0
        assert manager.sentence_delimiters is not None

    def test_queue_manager_with_custom_config(self):
        """커스텀 설정으로 초기화할 수 있어야 한다"""
        from services.orchestrator.app.queue_manager import SentenceQueueManager

        manager = SentenceQueueManager(
            min_sentence_length=10,
            sentence_delimiters=[".", "?", "!"]
        )

        assert manager.min_sentence_length == 10
        assert "." in manager.sentence_delimiters


class TestTokenBuffering:
    """토큰 버퍼링 테스트"""

    def test_add_token_buffers_text(self):
        """토큰이 버퍼에 추가되어야 한다"""
        from services.orchestrator.app.queue_manager import SentenceQueueManager

        manager = SentenceQueueManager()

        manager.add_token("안녕")
        manager.add_token("하세요")

        assert manager.get_buffer() == "안녕하세요"

    def test_add_token_with_spaces(self):
        """공백 포함 토큰이 올바르게 처리되어야 한다"""
        from services.orchestrator.app.queue_manager import SentenceQueueManager

        manager = SentenceQueueManager()

        manager.add_token("Hello")
        manager.add_token(" ")
        manager.add_token("World")

        assert manager.get_buffer() == "Hello World"

    def test_buffer_cleared_after_sentence(self):
        """문장 완료 후 버퍼가 비워져야 한다"""
        from services.orchestrator.app.queue_manager import SentenceQueueManager

        manager = SentenceQueueManager(min_sentence_length=5)

        manager.add_token("안녕하세요.")

        sentences = manager.get_complete_sentences()
        assert len(sentences) == 1
        assert manager.get_buffer() == ""


class TestSentenceDetection:
    """문장 감지 테스트"""

    def test_sentence_detection_period(self):
        """마침표로 문장을 분리해야 한다"""
        from services.orchestrator.app.queue_manager import SentenceQueueManager

        manager = SentenceQueueManager(min_sentence_length=3)

        tokens = ["안녕", "하세요", ".", " ", "반갑", "습니다", "."]
        for token in tokens:
            manager.add_token(token)

        sentences = manager.get_complete_sentences()

        assert len(sentences) == 2
        assert "안녕하세요." in sentences[0]
        assert "반갑습니다." in sentences[1]

    def test_sentence_detection_question(self):
        """물음표로 문장을 분리해야 한다"""
        from services.orchestrator.app.queue_manager import SentenceQueueManager

        manager = SentenceQueueManager(min_sentence_length=3)

        tokens = ["오늘", " ", "날씨", "가", " ", "어때", "?"]
        for token in tokens:
            manager.add_token(token)

        sentences = manager.get_complete_sentences()

        assert len(sentences) == 1
        assert "?" in sentences[0]

    def test_sentence_detection_exclamation(self):
        """느낌표로 문장을 분리해야 한다"""
        from services.orchestrator.app.queue_manager import SentenceQueueManager

        manager = SentenceQueueManager(min_sentence_length=3)

        tokens = ["정말", " ", "좋아요", "!"]
        for token in tokens:
            manager.add_token(token)

        sentences = manager.get_complete_sentences()

        assert len(sentences) == 1
        assert "!" in sentences[0]

    def test_sentence_detection_korean_period(self):
        """한국어 마침표(。)도 인식해야 한다"""
        from services.orchestrator.app.queue_manager import SentenceQueueManager

        manager = SentenceQueueManager(min_sentence_length=3)

        manager.add_token("감사합니다。")

        sentences = manager.get_complete_sentences()

        assert len(sentences) == 1


class TestMinSentenceLength:
    """최소 문장 길이 테스트"""

    def test_min_sentence_length_enforced(self):
        """최소 길이 미달 시 문장으로 분리하지 않아야 한다"""
        from services.orchestrator.app.queue_manager import SentenceQueueManager

        manager = SentenceQueueManager(min_sentence_length=10)

        manager.add_token("네.")  # 2글자 - 최소 길이 미달

        sentences = manager.get_complete_sentences()

        assert len(sentences) == 0
        assert manager.get_buffer() == "네."

    def test_min_sentence_length_with_following_text(self):
        """짧은 문장 뒤에 긴 문장이 오면 함께 처리"""
        from services.orchestrator.app.queue_manager import SentenceQueueManager

        manager = SentenceQueueManager(min_sentence_length=10)

        manager.add_token("네. 그렇습니다. 이것은 긴 문장입니다.")

        sentences = manager.get_complete_sentences()

        # 짧은 문장들이 합쳐지거나 긴 문장만 분리됨
        assert len(sentences) >= 1


class TestFlushBuffer:
    """버퍼 플러시 테스트"""

    def test_flush_remaining_buffer(self):
        """남은 버퍼를 강제로 플러시할 수 있어야 한다"""
        from services.orchestrator.app.queue_manager import SentenceQueueManager

        manager = SentenceQueueManager(min_sentence_length=5)

        manager.add_token("미완성 문장")

        # 일반적으로는 문장이 안 나옴
        sentences = manager.get_complete_sentences()
        assert len(sentences) == 0

        # 플러시하면 남은 내용 반환
        remaining = manager.flush()
        assert remaining == "미완성 문장"
        assert manager.get_buffer() == ""

    def test_flush_empty_buffer(self):
        """빈 버퍼 플러시 시 빈 문자열 반환"""
        from services.orchestrator.app.queue_manager import SentenceQueueManager

        manager = SentenceQueueManager()

        remaining = manager.flush()

        assert remaining == ""


class TestBargeIn:
    """Barge-in 처리 테스트"""

    def test_clear_queue_on_barge_in(self):
        """Barge-in 시 큐와 버퍼가 비워져야 한다"""
        from services.orchestrator.app.queue_manager import SentenceQueueManager

        manager = SentenceQueueManager(min_sentence_length=3)

        # 문장 추가
        manager.add_token("안녕하세요.")
        manager.add_token(" 이것은 테스트입니다")

        # Barge-in 발생
        manager.clear_on_barge_in()

        assert manager.get_buffer() == ""
        assert len(manager.get_complete_sentences()) == 0

    def test_barge_in_returns_discarded_content(self):
        """Barge-in 시 버려진 내용을 반환해야 한다"""
        from services.orchestrator.app.queue_manager import SentenceQueueManager

        manager = SentenceQueueManager(min_sentence_length=3)

        manager.add_token("처리 중인 내용.")
        manager.add_token(" 더 많은 내용")

        discarded = manager.clear_on_barge_in()

        assert "더 많은 내용" in discarded or len(discarded) > 0


class TestAsyncQueueOperations:
    """비동기 큐 작업 테스트"""

    @pytest.mark.asyncio
    async def test_async_add_and_get(self):
        """비동기로 토큰 추가 및 문장 획득"""
        from services.orchestrator.app.queue_manager import SentenceQueueManager

        manager = SentenceQueueManager(min_sentence_length=3)

        await manager.add_token_async("안녕하세요.")

        sentences = await manager.get_sentences_async()

        assert len(sentences) == 1

    @pytest.mark.asyncio
    async def test_sentence_callback(self):
        """문장 완료 시 콜백 호출"""
        from services.orchestrator.app.queue_manager import SentenceQueueManager

        received_sentences = []

        async def on_sentence(sentence: str):
            received_sentences.append(sentence)

        manager = SentenceQueueManager(
            min_sentence_length=3,
            on_sentence_complete=on_sentence
        )

        await manager.add_token_async("첫 번째 문장.")
        await manager.add_token_async(" 두 번째 문장.")

        # 콜백이 호출되었는지 확인
        await asyncio.sleep(0.1)  # 콜백 처리 대기

        assert len(received_sentences) >= 1


class TestRedisIntegration:
    """Redis 통합 테스트 (Mock)"""

    @pytest.mark.asyncio
    async def test_tts_worker_publishes_to_redis(self):
        """TTS 요청이 Redis로 발행되어야 한다"""
        from services.orchestrator.app.queue_manager import SentenceQueueManager

        mock_redis = AsyncMock()

        manager = SentenceQueueManager(
            min_sentence_length=3,
            redis_client=mock_redis
        )

        await manager.add_token_async("테스트 문장입니다.")

        # process_sentences를 호출하면 Redis에 발행
        await manager.process_and_publish()

        # Redis publish가 호출되었는지 확인
        mock_redis.publish.assert_called()

    @pytest.mark.asyncio
    async def test_redis_message_format(self):
        """Redis 메시지 형식이 올바른지 확인"""
        from services.orchestrator.app.queue_manager import SentenceQueueManager

        mock_redis = AsyncMock()
        published_messages = []

        async def capture_publish(channel, message):
            published_messages.append({"channel": channel, "message": message})

        mock_redis.publish = capture_publish

        manager = SentenceQueueManager(
            min_sentence_length=3,
            redis_client=mock_redis,
            redis_channel="edgevoice:tts:request"
        )

        await manager.add_token_async("안녕하세요.")
        await manager.process_and_publish()

        assert len(published_messages) > 0
        assert published_messages[0]["channel"] == "edgevoice:tts:request"


class TestMultipleSentences:
    """다중 문장 처리 테스트"""

    def test_multiple_sentences_in_buffer(self):
        """버퍼에 여러 문장이 있을 때 모두 분리"""
        from services.orchestrator.app.queue_manager import SentenceQueueManager

        manager = SentenceQueueManager(min_sentence_length=3)

        text = "첫 번째. 두 번째. 세 번째."
        manager.add_token(text)

        sentences = manager.get_complete_sentences()

        assert len(sentences) == 3

    def test_mixed_delimiters(self):
        """다양한 구분자가 섞여 있을 때 처리"""
        from services.orchestrator.app.queue_manager import SentenceQueueManager

        manager = SentenceQueueManager(min_sentence_length=3)

        text = "이건 문장. 질문인가요? 느낌표야!"
        manager.add_token(text)

        sentences = manager.get_complete_sentences()

        assert len(sentences) == 3
