"""
Sentence Queue Manager

Phase 2.1: LLM 토큰 스트리밍을 문장 단위로 분리하여 TTS로 전달
"""
import asyncio
import json
import re
from typing import Any, Callable, Optional


class SentenceQueueManager:
    """
    문장 큐 관리자

    LLM에서 스트리밍되는 토큰을 버퍼링하고,
    완성된 문장을 감지하여 TTS로 전달합니다.

    Attributes:
        min_sentence_length: 최소 문장 길이 (이보다 짧으면 다음 문장과 합침)
        sentence_delimiters: 문장 구분자 목록
        on_sentence_complete: 문장 완료 시 호출되는 콜백
    """

    DEFAULT_DELIMITERS = [".", "?", "!", "。", "？", "！"]

    def __init__(
        self,
        min_sentence_length: int = 5,
        sentence_delimiters: Optional[list[str]] = None,
        on_sentence_complete: Optional[Callable[[str], Any]] = None,
        redis_client: Optional[Any] = None,
        redis_channel: str = "edgevoice:tts:request"
    ):
        """
        SentenceQueueManager 초기화

        Args:
            min_sentence_length: 최소 문장 길이
            sentence_delimiters: 문장 구분자 목록
            on_sentence_complete: 문장 완료 콜백 (async 함수)
            redis_client: Redis 클라이언트 (비동기)
            redis_channel: Redis 발행 채널
        """
        self.min_sentence_length = min_sentence_length
        self.sentence_delimiters = sentence_delimiters or self.DEFAULT_DELIMITERS
        self.on_sentence_complete = on_sentence_complete
        self.redis_client = redis_client
        self.redis_channel = redis_channel

        # 내부 상태
        self._buffer: str = ""
        self._pending_sentences: list[str] = []
        self._lock = asyncio.Lock()

        # 정규식 패턴 생성 (문장 구분자로 분리)
        escaped_delimiters = [re.escape(d) for d in self.sentence_delimiters]
        self._split_pattern = re.compile(
            f"([{''.join(escaped_delimiters)}])"
        )

    def add_token(self, token: str) -> None:
        """
        토큰을 버퍼에 추가

        Args:
            token: LLM에서 생성된 토큰
        """
        self._buffer += token
        self._process_buffer()

    async def add_token_async(self, token: str) -> None:
        """
        비동기로 토큰을 버퍼에 추가

        Args:
            token: LLM에서 생성된 토큰
        """
        async with self._lock:
            self._buffer += token
            self._process_buffer()

            # 콜백 호출
            if self.on_sentence_complete and self._pending_sentences:
                for sentence in self._pending_sentences:
                    if asyncio.iscoroutinefunction(self.on_sentence_complete):
                        await self.on_sentence_complete(sentence)
                    else:
                        self.on_sentence_complete(sentence)

    def _process_buffer(self) -> None:
        """버퍼를 처리하여 완성된 문장 추출"""
        if not self._buffer:
            return

        # 문장 구분자로 분리
        parts = self._split_pattern.split(self._buffer)

        # 완성된 문장 추출
        current_sentence = ""
        for i, part in enumerate(parts):
            current_sentence += part

            # 구분자인 경우 문장 완료 체크
            if part in self.sentence_delimiters:
                stripped = current_sentence.strip()
                if len(stripped) >= self.min_sentence_length:
                    self._pending_sentences.append(stripped)
                    current_sentence = ""
                # 짧은 문장은 버퍼에 유지 (다음 문장과 합칠 수 있음)

        # 남은 부분은 버퍼에 유지
        self._buffer = current_sentence

    def get_buffer(self) -> str:
        """현재 버퍼 내용 반환"""
        return self._buffer

    def get_complete_sentences(self) -> list[str]:
        """
        완성된 문장 목록 반환 및 클리어

        Returns:
            완성된 문장 리스트
        """
        sentences = self._pending_sentences.copy()
        self._pending_sentences.clear()
        return sentences

    async def get_sentences_async(self) -> list[str]:
        """
        비동기로 완성된 문장 목록 반환

        Returns:
            완성된 문장 리스트
        """
        async with self._lock:
            return self.get_complete_sentences()

    def flush(self) -> str:
        """
        버퍼의 남은 내용을 강제로 반환

        Returns:
            버퍼에 남아있던 텍스트
        """
        remaining = self._buffer
        self._buffer = ""
        return remaining

    def clear_on_barge_in(self) -> str:
        """
        Barge-in 발생 시 모든 큐와 버퍼 클리어

        Returns:
            버려진 내용 (디버깅용)
        """
        discarded_buffer = self._buffer
        discarded_sentences = self._pending_sentences.copy()

        self._buffer = ""
        self._pending_sentences.clear()

        # 버려진 내용 조합
        all_discarded = " ".join(discarded_sentences)
        if discarded_buffer:
            all_discarded += " " + discarded_buffer

        return all_discarded.strip()

    async def process_and_publish(self) -> None:
        """
        완성된 문장을 Redis로 발행
        """
        if not self.redis_client:
            return

        async with self._lock:
            sentences = self.get_complete_sentences()

            for sentence in sentences:
                message = json.dumps({
                    "type": "tts_request",
                    "text": sentence
                })
                await self.redis_client.publish(self.redis_channel, message)

    async def stream_tokens(
        self,
        token_generator,
        auto_publish: bool = True
    ):
        """
        토큰 제너레이터에서 토큰을 받아 처리

        Args:
            token_generator: 토큰을 생성하는 async generator
            auto_publish: True이면 자동으로 Redis 발행

        Yields:
            완성된 문장
        """
        async for token in token_generator:
            await self.add_token_async(token)

            sentences = await self.get_sentences_async()
            for sentence in sentences:
                if auto_publish and self.redis_client:
                    message = json.dumps({
                        "type": "tts_request",
                        "text": sentence
                    })
                    await self.redis_client.publish(self.redis_channel, message)

                yield sentence

        # 스트림 종료 시 남은 버퍼 처리
        remaining = self.flush()
        if remaining and len(remaining.strip()) >= self.min_sentence_length:
            if auto_publish and self.redis_client:
                message = json.dumps({
                    "type": "tts_request",
                    "text": remaining
                })
                await self.redis_client.publish(self.redis_channel, message)

            yield remaining
