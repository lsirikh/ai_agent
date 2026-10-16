"""
Orchestrator Main

Phase 2.3: 음성 대화 흐름을 관리하는 오케스트레이터
Redis 이벤트 기반으로 STT, LLM, TTS를 조율
"""
import asyncio
import json
import os
import re
import time
from typing import Any, Optional

from .backend_client import BackendClient
from .llm_client import LLMClient
from .pipeline_logger import get_logger
from .queue_manager import SentenceQueueManager
from .state_machine import OrchestratorStateMachine, State

# 한국어 TTS 가 읽을 수 없는 한자(중국어).
# Qwen 이 답 중간에 중국어로 넘어가는 경우가 있다.
HAN_CHARACTER_PATTERN = re.compile(r"[㐀-䶿一-鿿]")

DEFAULT_VOICE_SYSTEM_PROMPT = (
    "당신은 EdgeVoice 음성 비서입니다. 항상 한국어로만 답하고 "
    "중국어·한자·일본어는 절대 쓰지 마세요. "
    "답은 소리 내어 읽기 좋게 2~3문장으로 짧고 자연스럽게 말하고, "
    "목록 기호·마크다운·이모지는 쓰지 마세요."
)

# 녹음에 섞여 들어온 웨이크워드("Hey Jarvis", "헤이 자비스")를 STT 결과 앞에서 뗀다
WAKE_PHRASE_PATTERN = re.compile(
    r"^\s*(?:hey|hi|헤이|해이)[\s,.!~\-]*(?:jarvis|자비스|쟈비스)[\s,.!?~\-]*",
    re.IGNORECASE,
)


def strip_wake_phrase(text: str) -> str:
    return WAKE_PHRASE_PATTERN.sub("", text, count=1).strip()


ORDINALS = [
    "첫째", "둘째", "셋째", "넷째", "다섯째",
    "여섯째", "일곱째", "여덟째", "아홉째", "열째",
]
LIST_NUMBER_AT_LINE_START = re.compile(r"^\s*(\d{1,2})[.)]\s+")
LIST_NUMBER_AT_END = re.compile(r"\s+(\d{1,2})[.)]\s*$")
BULLET_AT_LINE_START = re.compile(r"^\s*[-*•]\s+")
MARKDOWN_MARKS = re.compile(r"\*\*|__|`|#+\s*")


def _ordinal(number: int) -> str:
    return ORDINALS[number - 1] if 1 <= number <= len(ORDINALS) else f"{number}번째"


def to_speech(
    sentence: str, pending_number: Optional[int]
) -> tuple[str, Optional[int]]:
    """
    TTS 가 자연스럽게 읽도록 한 문장을 다듬는다.

    - 줄 앞 번호 "1. " → "첫째, ", 글머리표·마크다운 기호 제거, ';' ':' → ','.
    - 문장 나누기로 끝에 떨어진 번호("…좋겠네요: 1.")는 떼고 다음 문장 앞에 붙인다.
    반환: (읽을 문장, 다음 문장 앞에 붙일 번호)
    """
    trailing = LIST_NUMBER_AT_END.search(sentence)
    next_number = int(trailing.group(1)) if trailing else None
    if trailing:
        sentence = sentence[: trailing.start()]

    lines = []
    for line in sentence.splitlines():
        line = BULLET_AT_LINE_START.sub("", line)
        line = LIST_NUMBER_AT_LINE_START.sub(
            lambda m: f"{_ordinal(int(m.group(1)))}, ", line
        )
        if line.strip():
            lines.append(line.strip())
    text = " ".join(lines)
    if pending_number is not None:
        text = f"{_ordinal(pending_number)}, {text}"
    text = MARKDOWN_MARKS.sub("", text)
    text = re.sub(r"\s*[;:]\s*", ", ", text)
    text = re.sub(r",\s*$", ".", re.sub(r"\s{2,}", " ", text)).strip()
    return text, next_number


class Orchestrator:
    """
    음성 대화 오케스트레이터

    역할:
    - Wake Word 감지 후 음성 입력 수신
    - STT 결과를 LLM으로 전달
    - LLM 응답을 문장 단위로 분리하여 TTS로 전달
    - Barge-in 감지 시 응답 중단 및 새 입력 수신
    - 대화 컨텍스트 관리

    Attributes:
        state_machine: 상태 머신
        queue_manager: 문장 큐 관리자
        llm_client: LLM 클라이언트
        redis: Redis 클라이언트
    """

    # Redis 채널
    CHANNELS = {
        "wake_word": "edgevoice:wake_word:detected",
        "stt_result": "edgevoice:stt:result",
        "stt_partial": "edgevoice:stt:partial",
        "barge_in": "edgevoice:barge_in:detected",
        "tts_request": "edgevoice:tts:request",
        "tts_complete": "edgevoice:tts:complete",
        "state_change": "edgevoice:orchestrator:state"
    }

    # 백엔드 StateManager 의 ORCHESTRATOR_STATE_KEY 와 같은 키
    STATE_KEY = "orchestrator:state"
    STATE_KEY_TTL_SECONDS = 300

    # 듣기 상태에서 발화·end_pause·STT 처리를 기다리는 여유 시간
    UTTERANCE_GRACE_SECONDS = 30.0

    # 지식 베이스(RAG). 실측: 관련 질문 0.53~0.70, 인사말 0.49~0.50
    RAG_URL = os.getenv("RAG_SERVICE_URL", "http://rag:8006")
    RAG_MIN_SCORE = float(os.getenv("RAG_MIN_SCORE", "0.52"))

    # 마지막 TTS 요청 후 완료 신호를 기다리는 최대 시간
    TTS_COMPLETE_TIMEOUT_SECONDS = 60.0

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        redis_client: Optional[Any] = None,
        listening_timeout: float = 10.0,
        end_pause_seconds: float = 2.0,
        environment: str = "development",
        backend_client: Optional[BackendClient] = None
    ):
        """
        Orchestrator 초기화

        Args:
            llm_client: LLM 클라이언트 (기본: 새로 생성)
            redis_client: Redis 클라이언트 (기본: 새로 연결)
            listening_timeout: LISTENING 상태 타임아웃 (초)
            end_pause_seconds: 음성 종료 감지를 위한 무음 시간 (초) - Phase 50
            environment: 환경 설정
            backend_client: 활성 세션·대화 저장용 백엔드 클라이언트
                (기본: BACKEND_URL 이 있으면 생성, 없으면 메모리 컨텍스트만 사용)
        """
        self.backend_client = backend_client
        if self.backend_client is None and os.getenv("BACKEND_URL"):
            self.backend_client = BackendClient()
        self.environment = environment
        self.listening_timeout = listening_timeout
        # Phase 50: End Pause 설정
        self.end_pause_seconds = end_pause_seconds

        # 상태 머신 초기화
        self.state_machine = OrchestratorStateMachine(
            on_state_change=self._on_state_change
        )

        # LLM 클라이언트 (음성 경로는 한국어로 짧게 답하도록 시스템 프롬프트를 준다)
        self.llm_client = llm_client or LLMClient(
            environment=environment,
            system_prompt=os.getenv("VOICE_SYSTEM_PROMPT", DEFAULT_VOICE_SYSTEM_PROMPT),
        )

        # Redis 클라이언트 (lazy initialization)
        self.redis = redis_client
        if self.redis is None:
            self.redis = self._setup_redis()

        # 문장 큐 관리자
        self.queue_manager = SentenceQueueManager(
            redis_client=self.redis,
            redis_channel=self.CHANNELS["tts_request"]
        )

        # 내부 상태
        self._listening_task: Optional[asyncio.Task] = None

        # 이번 턴에 보냈지만 아직 완료되지 않은 TTS 문장 수
        self._pending_tts = 0
        self._tts_watchdog: Optional[asyncio.Task] = None

        # 문장 끝에 떨어진 목록 번호(다음 문장 앞에 '첫째,' 처럼 붙인다)
        self._pending_list_number: Optional[int] = None
        self._processing_task: Optional[asyncio.Task] = None
        self._is_running = False

        # TTS 설정 (Phase 8.3)
        self._current_session_id: Optional[str] = None
        self._tts_voice: str = os.getenv("TTS_VOICE", "af_heart")
        self._tts_speed: float = float(os.getenv("TTS_SPEED", "1.0"))

        # Pipeline Logger (Phase 17)
        self._logger = get_logger("orchestrator")

    def _setup_redis(self) -> Any:
        """Redis 클라이언트 설정 (Mock 반환 for testing)"""
        try:
            import redis.asyncio as redis
            redis_host = os.getenv("REDIS_HOST", "localhost")
            redis_port = int(os.getenv("REDIS_PORT", "6379"))
            return redis.Redis(host=redis_host, port=redis_port, decode_responses=True)
        except Exception:
            return None

    def _on_state_change(self, old_state: State, new_state: State) -> None:
        """상태 변경 콜백"""
        # Redis로 상태 변경 브로드캐스트 (비동기로 처리)
        if self.redis:
            asyncio.create_task(self._publish_state_change(old_state, new_state))

    async def _publish_state_change(self, old_state: State, new_state: State) -> None:
        """상태 변경을 Redis로 발행"""
        if self.redis:
            message = json.dumps({
                "type": "state_change",
                "old_state": old_state.name,
                "new_state": new_state.name,
                # Phase 50: 상태 변경 시 설정 정보도 포함
                "settings": {
                    "end_pause_seconds": self.end_pause_seconds,
                    "listening_timeout_seconds": self.listening_timeout
                }
            })
            try:
                await self.redis.publish(self.CHANNELS["state_change"], message)
            except Exception:
                pass

            # 백엔드 /api/status/stream 은 이 키를 읽는다 (없으면 항상 OFF 로 보인다)
            current = json.dumps({
                "state": new_state.name,
                "session_id": self._current_session_id,
                "timestamp": time.time()
            })
            try:
                await self.redis.set(self.STATE_KEY, current, ex=self.STATE_KEY_TTL_SECONDS)
            except Exception:
                pass

    async def broadcast_settings(self) -> None:
        """
        Phase 50: 현재 설정을 Redis로 브로드캐스트

        Audio Gateway 등 다른 서비스가 설정 변경을 수신할 수 있도록 합니다.
        """
        if not self.redis:
            return

        message = json.dumps({
            "type": "settings_update",
            "current_state": self.state_machine.current_state.name,
            "settings": {
                "end_pause_seconds": self.end_pause_seconds,
                "listening_timeout_seconds": self.listening_timeout
            },
            "timestamp": time.time()
        })

        try:
            await self.redis.publish(self.CHANNELS["state_change"], message)
            await self._logger.log(
                event="settings_broadcast",
                data={
                    "message": f"Settings broadcast: end_pause={self.end_pause_seconds}s",
                    "end_pause_seconds": self.end_pause_seconds,
                    "listening_timeout_seconds": self.listening_timeout
                }
            )
        except Exception as e:
            await self._logger.log(
                event="settings_broadcast_failed",
                data={"error": str(e)},
                level="error"
            )

    async def handle_wake_word(self) -> bool:
        """
        Wake Word 감지 이벤트 처리

        Returns:
            처리 성공 여부
        """
        # Phase 32: IDLE → READY 별칭이므로 READY도 허용
        if self.state_machine.current_state not in (State.IDLE, State.READY):
            await self._logger.log(
                event="wake_word_ignored",
                session_id=self._current_session_id,
                data={"current_state": self.state_machine.current_state.name},
                level="warning"
            )
            return False

        success = self.state_machine.transition_to(State.LISTENING)

        if success:
            await self._logger.log(
                event="wake_word_detected",
                session_id=self._current_session_id,
                data={"message": "Wake word detected, transitioning to LISTENING state"}
            )
            # 타임아웃 타이머 시작
            self._start_listening_timeout()

        return success

    async def handle_stt_result(self, text: str) -> None:
        """
        STT 결과 처리

        Args:
            text: 인식된 텍스트
        """
        if self.state_machine.current_state != State.LISTENING:
            return

        text = strip_wake_phrase(text)
        if not text:
            # 웨이크워드만 들렸으면 LLM 을 부르지 않고 대기로 돌아간다
            self._cancel_listening_timeout()
            self.state_machine.transition_to(State.READY)
            return

        await self._logger.log(
            event="stt_result_received",
            session_id=self._current_session_id,
            data={
                "message": f"STT result received: {text[:50]}{'...' if len(text) > 50 else ''}",
                "text_length": len(text)
            }
        )

        # 타임아웃 타이머 취소
        self._cancel_listening_timeout()

        # Phase 32: LISTENING → STT_PROCESSING → LLM_PROCESSING
        self.state_machine.transition_to(State.STT_PROCESSING)
        self.state_machine.transition_to(State.LLM_PROCESSING)

        # LLM 처리 시작
        await self.process_user_input(text)

    async def handle_barge_in(self) -> bool:
        """
        Barge-in 이벤트 처리

        Returns:
            처리 성공 여부
        """
        await self._logger.log(
            event="barge_in_detected",
            session_id=self._current_session_id,
            data={"message": "Barge-in detected, interrupting current response"}
        )

        # 진행 중인 처리 취소
        if self._processing_task and not self._processing_task.done():
            self._processing_task.cancel()

        # 큐 클리어 (남은 문장의 완료는 더 기다리지 않는다)
        self.queue_manager.clear_on_barge_in()
        self._pending_tts = 0

        # 상태 전이
        return self.state_machine.handle_barge_in()

    async def handle_timeout(self) -> bool:
        """
        타임아웃 이벤트 처리

        Returns:
            처리 성공 여부
        """
        return self.state_machine.handle_timeout()

    async def handle_speaking_complete(self) -> bool:
        """
        TTS 출력 완료 처리

        Returns:
            처리 성공 여부
        """
        # TTS 는 문장마다 완료를 알린다 → 마지막 문장이 끝날 때 READY
        if self.state_machine.current_state in (State.SPEAKING, State.TTS_PROCESSING):
            self._pending_tts = max(0, self._pending_tts - 1)
            if self._pending_tts == 0:
                return self._finish_turn()
        return False

    def _finish_turn(self) -> bool:
        """한 턴을 끝내고 READY 로 돌아간다(진행 중 상태가 아니면 그대로 둔다)."""
        self._pending_tts = 0
        if self._tts_watchdog and not self._tts_watchdog.done():
            self._tts_watchdog.cancel()
        if self.state_machine.current_state in (
            State.STT_PROCESSING, State.LLM_PROCESSING, State.TTS_PROCESSING, State.SPEAKING
        ):
            return self.state_machine.transition_to(State.READY)
        return False

    def _start_tts_watchdog(self) -> None:
        """TTS 완료 신호가 끝내 오지 않아도 비서가 멈추지 않도록 READY 로 되돌린다."""
        if self._tts_watchdog and not self._tts_watchdog.done():
            self._tts_watchdog.cancel()

        async def watchdog() -> None:
            await asyncio.sleep(self.TTS_COMPLETE_TIMEOUT_SECONDS)
            self._finish_turn()

        self._tts_watchdog = asyncio.create_task(watchdog())

    async def process_user_input(self, text: str) -> None:
        """
        사용자 입력 처리 (LLM 호출)

        Args:
            text: 사용자 입력 텍스트
        """
        # 사용자 메시지는 generate_stream 이 요청에 붙이므로 여기서 컨텍스트에 미리 넣지 않는다
        # (응답이 끝나면 _process_llm_stream 이 user/assistant 를 함께 기록)

        # LLM 스트리밍 처리
        self._processing_task = asyncio.create_task(
            self._process_llm_stream(text)
        )

        try:
            await self._processing_task
        except asyncio.CancelledError:
            # Barge-in으로 인한 취소
            pass

    async def _search_knowledge(self, query: str) -> list[dict[str, Any]]:
        """RAG 서비스 검색 결과(content·score·metadata). 실패하면 빈 목록."""
        import httpx

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.post(
                    f"{self.RAG_URL}/retrieve", json={"query": query, "top_k": 3}
                )
                response.raise_for_status()
                return response.json().get("results") or []
        except Exception:
            return []

    async def _relevant_knowledge(self, query: str) -> list[dict[str, Any]]:
        """기준 점수 이상인 근거만 LLM 형식({content, source})으로."""
        results = await self._search_knowledge(query)
        return [
            {
                "content": r.get("content", ""),
                "source": (r.get("metadata") or {}).get("filename", "문서"),
            }
            for r in results
            if r.get("score", 0) >= self.RAG_MIN_SCORE
        ]

    async def _process_llm_stream(self, text: str) -> None:
        """
        LLM 스트리밍 응답 처리

        Args:
            text: 사용자 입력 텍스트
        """
        first_sentence_sent = False
        self._pending_list_number = None
        full_response = ""
        llm_start_time = time.time()

        # 채팅과 같은 활성 세션의 히스토리로 답한다
        # (인식 문장은 히스토리를 읽은 뒤 저장)
        history, summary = await self._load_session_context()
        await self._save_voice_message("user", text)

        await self._logger.log(
            event="llm_processing_started",
            session_id=self._current_session_id,
            data={"message": "LLM processing started", "input_text": text[:100]}
        )

        try:
            # 채팅과 같은 지식 베이스에서 근거를 찾아 이번 질문에 붙인다
            knowledge = await self._relevant_knowledge(text)
            async for token in self.llm_client.generate_stream(
                text, history=history, summary=summary, rag_context=knowledge or None
            ):
                # 토큰을 큐 매니저에 추가
                await self.queue_manager.add_token_async(token)
                full_response += token

                # 완성된 문장 확인
                sentences = self.queue_manager.get_complete_sentences()

                for sentence in sentences:
                    # Phase 32: 첫 문장에서 TTS_PROCESSING 상태로 전이
                    if not first_sentence_sent:
                        # LLM_PROCESSING 또는 PROCESSING(별칭)에서 TTS_PROCESSING으로 전이
                        if self.state_machine.current_state in (State.LLM_PROCESSING, State.PROCESSING):
                            self.state_machine.transition_to(State.TTS_PROCESSING)
                        first_sentence_sent = True

                    # TTS 요청 발행
                    await self._speak(sentence)

            # 남은 버퍼 처리
            remaining = self.queue_manager.flush()
            if remaining and len(remaining.strip()) > 0:
                if not first_sentence_sent:
                    if self.state_machine.current_state in (State.LLM_PROCESSING, State.PROCESSING):
                        self.state_machine.transition_to(State.TTS_PROCESSING)
                await self._speak(remaining)

            # 어시스턴트 응답을 컨텍스트에 추가
            if hasattr(self.llm_client, 'add_to_context') and full_response:
                self.llm_client.add_to_context("user", text)
                self.llm_client.add_to_context("assistant", full_response)

            # 끼어들기로 잘린 답은 여기까지 오지 않으므로 저장되지 않는다
            if full_response:
                await self._save_voice_message("assistant", full_response)

            # TTS 가 아직 말하는 중이면 마지막 문장의 tts:complete 에서 READY 로 간다.
            # 보낸 문장이 없으면(빈 응답) 바로 READY.
            if self._pending_tts <= 0:
                self._finish_turn()
            else:
                self._start_tts_watchdog()

            llm_duration = int((time.time() - llm_start_time) * 1000)
            await self._logger.log(
                event="llm_processing_completed",
                session_id=self._current_session_id,
                data={
                    "message": f"LLM processing completed ({llm_duration}ms)",
                    "duration_ms": llm_duration,
                    "response_length": len(full_response)
                }
            )

        except asyncio.CancelledError:
            await self._logger.log(
                event="llm_processing_cancelled",
                session_id=self._current_session_id,
                data={"message": "LLM processing cancelled (barge-in)"}
            )
            raise
        except Exception as e:
            await self._logger.log(
                event="llm_processing_error",
                session_id=self._current_session_id,
                data={"message": f"LLM processing error: {str(e)}", "error": str(e)},
                level="error"
            )
            # 에러 시 IDLE로 복귀
            self.state_machine.reset()

    async def _load_session_context(self) -> tuple[Optional[list], Optional[str]]:
        """
        활성 세션의 (히스토리, 요약).
        백엔드가 없거나 실패하면 (None, None) → LLM 메모리 컨텍스트를 쓴다.
        """
        if not self.backend_client:
            return None, None
        try:
            self._current_session_id = await self.backend_client.get_active_session()
            context = await self.backend_client.get_context(self._current_session_id)
            return context.get("messages", []), context.get("summary")
        except Exception as e:
            await self._logger.log(
                event="session_context_failed",
                session_id=self._current_session_id,
                data={"message": f"Session context unavailable: {e}", "error": str(e)},
                level="warning"
            )
            return None, None

    async def _save_voice_message(self, role: str, content: str) -> None:
        """음성 턴을 활성 세션에 source='voice' 로 저장한다(채팅창에도 바로 뜬다)."""
        if not self.backend_client or not self.backend_client.current_session_id:
            return
        try:
            await self.backend_client.save_message(
                role=role, content=content, source="voice"
            )
        except Exception as e:
            await self._logger.log(
                event="voice_message_save_failed",
                session_id=self._current_session_id,
                data={"message": f"Failed to save voice message: {e}", "error": str(e)},
                level="warning"
            )

    async def _speak(self, sentence: str) -> None:
        """한국어로 읽을 수 있는 문장만 TTS 로 보낸다(한자가 섞인 문장은 건너뛴다)."""
        if HAN_CHARACTER_PATTERN.search(sentence):
            await self._logger.log(
                event="tts_sentence_skipped",
                session_id=self._current_session_id,
                data={"message": f"Skipped non-Korean sentence: {sentence[:50]}"},
            )
            return
        speech, self._pending_list_number = to_speech(
            sentence, self._pending_list_number
        )
        if speech:
            await self.publish_tts_request(speech)

    async def publish_tts_request(self, text: str) -> None:
        """
        TTS 요청을 Redis로 발행

        Args:
            text: 합성할 텍스트
        """
        await self._logger.log(
            event="tts_request_sent",
            session_id=self._current_session_id,
            data={
                "message": f"TTS request sent: {text[:50]}{'...' if len(text) > 50 else ''}",
                "text_length": len(text),
                "voice": self._tts_voice
            }
        )

        self._pending_tts += 1

        if self.redis:
            message = json.dumps({
                "session_id": self._current_session_id,
                "text": text,
                "voice": self._tts_voice,
                "speed": self._tts_speed,
                "timestamp": time.time()
            })
            try:
                await self.redis.publish(self.CHANNELS["tts_request"], message)
            except Exception as e:
                await self._logger.log(
                    event="tts_request_failed",
                    session_id=self._current_session_id,
                    data={
                        "message": f"Failed to publish TTS request: {str(e)}",
                        "error": str(e)
                    },
                    level="error"
                )

    async def subscribe_events(self) -> None:
        """Redis 이벤트 구독 시작"""
        if not self.redis:
            return

        pubsub = self.redis.pubsub()
        await pubsub.subscribe(
            self.CHANNELS["wake_word"],
            self.CHANNELS["stt_result"],
            self.CHANNELS["barge_in"],
            self.CHANNELS["tts_complete"]
        )

    async def reset_session(self) -> None:
        """세션 초기화 (대화 컨텍스트 클리어)"""
        if hasattr(self.llm_client, 'clear_context'):
            self.llm_client.clear_context()

        self.queue_manager.clear_on_barge_in()
        self.state_machine.reset()

    def _start_listening_timeout(self) -> None:
        """LISTENING 타임아웃 타이머 시작"""
        if self._listening_task:
            self._listening_task.cancel()

        async def timeout_handler():
            # 말 시작 대기(listening_timeout) + 말하는 시간·end_pause·STT 처리 여유.
            # 말이 아예 없으면 게이트웨이가 먼저 듣기를 끝낸다.
            await asyncio.sleep(self.listening_timeout + self.UTTERANCE_GRACE_SECONDS)
            if self.state_machine.current_state == State.LISTENING:
                await self.handle_timeout()

        self._listening_task = asyncio.create_task(timeout_handler())

    def _cancel_listening_timeout(self) -> None:
        """LISTENING 타임아웃 타이머 취소"""
        if self._listening_task and not self._listening_task.done():
            self._listening_task.cancel()
            self._listening_task = None

    async def run(self) -> None:
        """오케스트레이터 메인 루프 실행"""
        self._is_running = True

        if not self.redis:
            print("Redis not available, running in standalone mode")
            return

        pubsub = self.redis.pubsub()
        await pubsub.subscribe(
            self.CHANNELS["wake_word"],
            self.CHANNELS["stt_result"],
            self.CHANNELS["barge_in"],
            self.CHANNELS["tts_complete"]
        )

        try:
            async for message in pubsub.listen():
                if not self._is_running:
                    break

                if message["type"] != "message":
                    continue

                channel = message["channel"]
                data = json.loads(message["data"])

                await self._handle_message(channel, data)

        except asyncio.CancelledError:
            pass
        finally:
            await pubsub.unsubscribe()

    async def _handle_message(self, channel: str, data: dict) -> None:
        """
        Redis 메시지 처리

        Args:
            channel: 채널 이름
            data: 메시지 데이터
        """
        if channel == self.CHANNELS["wake_word"]:
            await self.handle_wake_word()

        elif channel == self.CHANNELS["stt_result"]:
            text = data.get("text", "")
            if text:
                await self.handle_stt_result(text)

        elif channel == self.CHANNELS["barge_in"]:
            await self.handle_barge_in()

        elif channel == self.CHANNELS["tts_complete"]:
            await self.handle_speaking_complete()

    async def stop(self) -> None:
        """오케스트레이터 중지"""
        self._is_running = False

        if self._listening_task:
            self._listening_task.cancel()

        if self._processing_task:
            self._processing_task.cancel()

        if self.redis:
            await self.redis.aclose()

    def get_status(self) -> dict:
        """현재 상태 정보 반환"""
        return {
            "state": self.state_machine.current_state.name,
            "state_info": self.state_machine.get_state_info(),
            "environment": self.environment,
            "is_running": self._is_running
        }
