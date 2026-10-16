"""
통합 대화 (음성 + 텍스트가 하나의 활성 세션을 공유)

- 활성 세션은 DB(settings 'active_session')에 두어 재시작 후에도 이어진다.
  "새 대화" 때만 바뀐다.
- 메시지가 저장될 때마다 Redis 로 발행해 /api/chat/stream 구독자(채팅창)에
  실시간으로 보낸다.
- 오래된 턴은 롤링 요약으로 접는다(원문은 지우지 않는다).
"""

import asyncio
import json
import os
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from shared.context_builder import (
    DEFAULT_MAX_MODEL_LEN,
    TEXT_MAX_TOKENS,
    estimate_tokens,
    split_for_summary,
)

from ..constants.redis_channels import RedisChannels
from ..database import get_db_manager
from ..repositories import MessageRepository, SessionRepository

# 예전 DB 에도 적용되도록 시작 시 실행한다 (init.sql 과 같은 내용)
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS session_summaries (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    summary TEXT NOT NULL,
    covered_until_message_id UUID NOT NULL,
    token_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_session_summaries_session
    ON session_summaries(session_id, created_at DESC);
-- 도구 결과 메시지(role='tool')
ALTER TABLE messages DROP CONSTRAINT IF EXISTS messages_role_check;
ALTER TABLE messages ADD CONSTRAINT messages_role_check
    CHECK (role IN ('user', 'assistant', 'system', 'tool'));
"""

SUMMARY_SYSTEM_PROMPT = (
    "당신은 대화 요약기입니다. 사용자와 AI 비서의 이전 대화를 "
    "이어지는 대화에 필요한 사실(사용자 이름·선호·결정·할 일·질문의 맥락) 위주로 "
    "한국어로 간결하게 요약하세요. "
    "기존 요약이 있으면 합쳐서 하나의 요약으로 만드세요. 요약문만 출력하세요."
)
SUMMARY_MAX_TOKENS = 512
SUMMARY_TEMPERATURE = 0.2

_redis = None
_summarizing: set = set()


def is_available() -> bool:
    """Postgres 가 연결돼 있어야 통합 대화를 쓴다(없으면 각 라우트의 기존 동작)."""
    return get_db_manager().is_connected


async def ensure_schema() -> None:
    async with get_db_manager().pool.acquire() as conn:
        await conn.execute(SCHEMA_SQL)


def _get_redis():
    global _redis
    if _redis is None:
        import redis.asyncio as redis

        _redis = redis.Redis(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", "6379")),
            decode_responses=True,
        )
    return _redis


def subscribe_messages():
    """채팅 메시지 채널 pubsub (호출한 쪽이 subscribe/close 한다)."""
    return _get_redis().pubsub()


async def publish_message(message: dict) -> None:
    try:
        await _get_redis().publish(
            RedisChannels.CHAT_MESSAGE, json.dumps(message, ensure_ascii=False)
        )
    except Exception as e:
        print(f"[Conversation] publish failed: {e}")


def to_public(message: dict) -> dict:
    """DB 메시지 → API/SSE 형식."""
    created_at = message.get("created_at")
    return {
        "id": str(message["id"]),
        "session_id": str(message["session_id"]),
        "role": message["role"],
        "content": message["content"],
        "source": message.get("source") or "web",
        "sources": message.get("rag_sources") or [],
        "created_at": created_at.isoformat()
        if hasattr(created_at, "isoformat")
        else created_at,
    }


async def start_new_session() -> str:
    """새 통합 세션을 만들고 활성으로 지정한다("새 대화")."""
    repo = SessionRepository()
    session_id = await repo.create(session_type="unified", source="api")
    await repo.set_active(session_id)
    return str(session_id)


async def get_active_session_id() -> str:
    """활성 세션 ID. 없으면 만든다."""
    session_id = await SessionRepository().get_active()
    if session_id is None:
        return await start_new_session()
    return str(session_id)


async def resolve_session_id(session_id: Optional[str]) -> str:
    """
    요청의 session_id 를 실제 세션으로 맞춘다.
    없거나 UUID 가 아니거나 DB 에 없는 세션이면 활성 세션을 쓴다
    (히스토리가 흩어지지 않게).
    """
    if session_id:
        try:
            uuid = UUID(session_id)
        except ValueError:
            uuid = None
        if uuid and await SessionRepository().get_by_id(uuid):
            return str(uuid)
    return await get_active_session_id()


async def save_message(
    session_id: str,
    role: str,
    content: str,
    source: str = "web",
    rag_sources: Optional[list] = None,
) -> dict:
    """메시지를 저장하고 채팅 스트림으로 발행한다."""
    uuid = UUID(session_id)
    message_id = await MessageRepository().create(
        uuid, role, content, rag_sources=rag_sources, source=source
    )
    message = to_public(
        {
            "id": message_id,
            "session_id": uuid,
            "role": role,
            "content": content,
            "source": source,
            "rag_sources": rag_sources or [],
            "created_at": datetime.now(timezone.utc),
        }
    )
    await publish_message(message)
    return message


async def list_messages(session_id: str) -> list:
    """세션의 전체 메시지(시간순)."""
    rows = await MessageRepository().get_by_session(UUID(session_id))
    return [to_public(m) for m in rows]


async def _uncovered(session_id: str) -> tuple:
    """(요약 행 또는 None, 요약에 덮이지 않은 메시지들)"""
    uuid = UUID(session_id)
    summary = await SessionRepository().get_summary(uuid)
    messages = await MessageRepository().get_by_session(uuid, include_system=False)
    if summary:
        covered = str(summary["covered_until_message_id"])
        ids = [str(m["id"]) for m in messages]
        if covered in ids:
            messages = messages[ids.index(covered) + 1 :]
    # 도구 결과는 화면 기록용 — 프롬프트·요약에는 답(assistant)만 이어진다
    return summary, [m for m in messages if m["role"] != "tool"]


async def get_context(session_id: str) -> dict:
    """프롬프트용: 최신 요약 + 요약 이후 메시지(role/content)."""
    summary, messages = await _uncovered(session_id)
    return {
        "session_id": session_id,
        "summary": summary["summary"] if summary else None,
        "messages": [{"role": m["role"], "content": m["content"]} for m in messages],
        "message_count": len(messages),
    }


async def maybe_summarize(session_id: str, llm_client: Any) -> bool:
    """
    최근 턴이 입력 예산의 75% 를 넘으면 오래된 턴을 한국어 요약으로 접는다.
    실패하면 아무것도 하지 않는다
    — 다음 프롬프트는 ContextBuilder 가 오래된 턴을 잘라 맞춘다.
    """
    summary, messages = await _uncovered(session_id)
    fold = split_for_summary(messages, DEFAULT_MAX_MODEL_LEN, TEXT_MAX_TOKENS)
    if fold == 0:
        return False

    folded = messages[:fold]
    transcript = "\n".join(
        f"{'사용자' if m['role'] == 'user' else 'AI'}: {m['content']}" for m in folded
    )
    prior = f"[기존 요약]\n{summary['summary']}\n\n" if summary else ""
    try:
        text = await llm_client.complete(
            [
                {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
                {"role": "user", "content": f"{prior}[대화]\n{transcript}"},
            ],
            max_tokens=SUMMARY_MAX_TOKENS,
            temperature=SUMMARY_TEMPERATURE,
        )
    except Exception as e:
        print(f"[Conversation] summary failed, falling back to truncation: {e}")
        return False

    text = (text or "").strip()
    if not text:
        return False
    await SessionRepository().add_summary(
        UUID(session_id), text, folded[-1]["id"], estimate_tokens(text)
    )
    return True


def schedule_summary(session_id: str, llm_client: Any) -> None:
    """턴이 끝난 뒤 비동기로 요약한다(같은 세션은 한 번에 하나만)."""
    if llm_client is None or session_id in _summarizing:
        return

    async def run() -> None:
        try:
            await maybe_summarize(session_id, llm_client)
        finally:
            _summarizing.discard(session_id)

    _summarizing.add(session_id)
    asyncio.create_task(run())
