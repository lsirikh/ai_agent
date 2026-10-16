"""
Backend API - Persistent History Store

Phase 9.4: PostgreSQL 기반 대화 기록 저장소
"""
import json
import uuid as uuid_lib
from typing import Optional


def to_session_uuid(session_id: str) -> uuid_lib.UUID:
    """
    세션 ID → UUID. UUID 가 아닌 ID(예: "session-1a2b")는 매번 같은 UUID 로 바꾼다
    (예전처럼 메시지마다 새 UUID 를 만들면 한 세션의 히스토리가 흩어진다).
    """
    try:
        return uuid_lib.UUID(session_id)
    except (ValueError, TypeError, AttributeError):
        return uuid_lib.uuid5(uuid_lib.NAMESPACE_URL, f"edgevoice-session:{session_id}")


class PersistentHistoryStore:
    """
    PostgreSQL 기반 대화 기록 저장소

    대화 메시지를 영구적으로 저장하고 조회하는 기능 제공
    """

    def __init__(self, database_url: str):
        """
        PersistentHistoryStore 초기화

        Args:
            database_url: PostgreSQL 데이터베이스 URL
        """
        self.database_url = database_url
        self.pool = None

    async def connect(self):
        """
        데이터베이스 연결

        asyncpg 연결 풀 생성
        """
        try:
            import asyncpg
            self.pool = await asyncpg.create_pool(self.database_url)
        except ImportError:
            pass  # asyncpg가 없으면 무시

    async def disconnect(self):
        """데이터베이스 연결 해제"""
        if self.pool:
            await self.pool.close()

    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: Optional[dict] = None
    ) -> str:
        """
        메시지 저장

        Args:
            session_id: 세션 ID
            role: 역할 ("user" 또는 "assistant")
            content: 메시지 내용
            metadata: 추가 메타데이터 (rag_used, sources 등)

        Returns:
            저장된 메시지 ID
        """
        if not self.pool:
            return ""

        async with self.pool.acquire() as conn:
            # session이 없으면 먼저 생성
            session_uuid = to_session_uuid(session_id)

            # Session 존재 확인 및 생성
            await conn.execute("""
                INSERT INTO sessions (id)
                VALUES ($1)
                ON CONFLICT (id) DO NOTHING
            """, session_uuid)

            # metadata에서 rag_sources 추출
            rag_sources = []
            if metadata and "sources" in metadata:
                rag_sources = metadata["sources"]

            msg_id = await conn.fetchval("""
                INSERT INTO messages (session_id, role, content, rag_sources)
                VALUES ($1, $2, $3, $4)
                RETURNING id
            """, session_uuid, role, content, json.dumps(rag_sources))

            return str(msg_id)

    async def get_session_messages(
        self,
        session_id: str,
        limit: int = 100
    ) -> list:
        """
        세션의 메시지 조회

        Args:
            session_id: 세션 ID
            limit: 최대 조회 수

        Returns:
            메시지 목록
        """
        if not self.pool:
            return []

        async with self.pool.acquire() as conn:
            session_uuid = to_session_uuid(session_id)

            rows = await conn.fetch("""
                SELECT id, session_id, role, content, rag_sources, created_at
                FROM messages
                WHERE session_id = $1
                ORDER BY created_at DESC
                LIMIT $2
            """, session_uuid, limit)

            # role, content만 포함하여 반환 (Sliding Window용)
            return [{"role": row["role"], "content": row["content"]} for row in rows]

    async def get_all_sessions(self, limit: int = 50) -> list:
        """
        모든 세션 목록 조회

        Args:
            limit: 최대 조회 수

        Returns:
            세션 목록
        """
        if not self.pool:
            return []

        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT DISTINCT session_id,
                       MIN(created_at) as first_message,
                       MAX(created_at) as last_message,
                       COUNT(*) as message_count
                FROM messages
                GROUP BY session_id
                ORDER BY last_message DESC
                LIMIT $1
            """, limit)

            return [dict(row) for row in rows]

    async def delete_session(self, session_id: str) -> bool:
        """
        세션 삭제

        Args:
            session_id: 세션 ID

        Returns:
            삭제 성공 여부
        """
        if not self.pool:
            return False

        async with self.pool.acquire() as conn:
            result = await conn.execute("""
                DELETE FROM messages
                WHERE session_id = $1
            """, session_id)

            return "DELETE" in result
