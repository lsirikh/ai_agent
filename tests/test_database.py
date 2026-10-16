"""
Test Database Schema

TDD Phase 0.3: PostgreSQL 테이블 스키마 존재 확인
"""
import os
import socket

import pytest

# 테스트 환경 설정
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
POSTGRES_USER = os.getenv("POSTGRES_USER", "edgevoice")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "edgevoice123")
POSTGRES_DB = os.getenv("POSTGRES_DB", "edgevoice")


def is_port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    """포트가 열려있는지 확인"""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False


POSTGRES_AVAILABLE = is_port_open(POSTGRES_HOST, POSTGRES_PORT)


async def get_connection():
    """PostgreSQL 연결 획득"""
    import asyncpg
    return await asyncpg.connect(
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
        database=POSTGRES_DB
    )


async def table_exists(table_name: str) -> bool:
    """테이블 존재 여부 확인"""
    conn = await get_connection()
    try:
        result = await conn.fetchval("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_name = $1
            )
        """, table_name)
        return result
    finally:
        await conn.close()


async def get_table_columns(table_name: str) -> list:
    """테이블 컬럼 정보 조회"""
    conn = await get_connection()
    try:
        rows = await conn.fetch("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_schema = 'public'
            AND table_name = $1
            ORDER BY ordinal_position
        """, table_name)
        return [dict(row) for row in rows]
    finally:
        await conn.close()


@pytest.mark.skipif(not POSTGRES_AVAILABLE, reason="PostgreSQL not available")
class TestSessionsTable:
    """sessions 테이블 테스트"""

    @pytest.mark.asyncio
    async def test_sessions_table_exists(self):
        """sessions 테이블이 존재해야 한다"""
        exists = await table_exists("sessions")
        assert exists, "Table 'sessions' should exist"

    @pytest.mark.asyncio
    async def test_sessions_has_id_column(self):
        """sessions 테이블에 id 컬럼이 있어야 한다"""
        columns = await get_table_columns("sessions")
        column_names = [c["column_name"] for c in columns]
        assert "id" in column_names, "sessions should have 'id' column"

    @pytest.mark.asyncio
    async def test_sessions_has_created_at_column(self):
        """sessions 테이블에 created_at 컬럼이 있어야 한다"""
        columns = await get_table_columns("sessions")
        column_names = [c["column_name"] for c in columns]
        assert "created_at" in column_names, "sessions should have 'created_at' column"

    @pytest.mark.asyncio
    async def test_sessions_has_metadata_column(self):
        """sessions 테이블에 metadata 컬럼이 있어야 한다"""
        columns = await get_table_columns("sessions")
        column_names = [c["column_name"] for c in columns]
        assert "metadata" in column_names, "sessions should have 'metadata' column"


@pytest.mark.skipif(not POSTGRES_AVAILABLE, reason="PostgreSQL not available")
class TestMessagesTable:
    """messages 테이블 테스트"""

    @pytest.mark.asyncio
    async def test_messages_table_exists(self):
        """messages 테이블이 존재해야 한다"""
        exists = await table_exists("messages")
        assert exists, "Table 'messages' should exist"

    @pytest.mark.asyncio
    async def test_messages_has_session_id_column(self):
        """messages 테이블에 session_id 컬럼이 있어야 한다"""
        columns = await get_table_columns("messages")
        column_names = [c["column_name"] for c in columns]
        assert "session_id" in column_names, "messages should have 'session_id' column"

    @pytest.mark.asyncio
    async def test_messages_has_role_column(self):
        """messages 테이블에 role 컬럼이 있어야 한다"""
        columns = await get_table_columns("messages")
        column_names = [c["column_name"] for c in columns]
        assert "role" in column_names, "messages should have 'role' column"

    @pytest.mark.asyncio
    async def test_messages_has_content_column(self):
        """messages 테이블에 content 컬럼이 있어야 한다"""
        columns = await get_table_columns("messages")
        column_names = [c["column_name"] for c in columns]
        assert "content" in column_names, "messages should have 'content' column"


@pytest.mark.skipif(not POSTGRES_AVAILABLE, reason="PostgreSQL not available")
class TestSettingsTable:
    """settings 테이블 테스트"""

    @pytest.mark.asyncio
    async def test_settings_table_exists(self):
        """settings 테이블이 존재해야 한다"""
        exists = await table_exists("settings")
        assert exists, "Table 'settings' should exist"

    @pytest.mark.asyncio
    async def test_settings_has_key_column(self):
        """settings 테이블에 key 컬럼이 있어야 한다"""
        columns = await get_table_columns("settings")
        column_names = [c["column_name"] for c in columns]
        assert "key" in column_names, "settings should have 'key' column"

    @pytest.mark.asyncio
    async def test_settings_has_value_column(self):
        """settings 테이블에 value 컬럼이 있어야 한다"""
        columns = await get_table_columns("settings")
        column_names = [c["column_name"] for c in columns]
        assert "value" in column_names, "settings should have 'value' column"

    @pytest.mark.asyncio
    async def test_settings_has_default_values(self):
        """settings 테이블에 기본 설정이 있어야 한다"""
        conn = await get_connection()
        try:
            count = await conn.fetchval("SELECT COUNT(*) FROM settings")
            assert count >= 4, "settings should have at least 4 default entries (llm, tts, stt, wake_word)"
        finally:
            await conn.close()


@pytest.mark.skipif(not POSTGRES_AVAILABLE, reason="PostgreSQL not available")
class TestPersonasTable:
    """personas 테이블 테스트"""

    @pytest.mark.asyncio
    async def test_personas_table_exists(self):
        """personas 테이블이 존재해야 한다"""
        exists = await table_exists("personas")
        assert exists, "Table 'personas' should exist"

    @pytest.mark.asyncio
    async def test_personas_has_name_column(self):
        """personas 테이블에 name 컬럼이 있어야 한다"""
        columns = await get_table_columns("personas")
        column_names = [c["column_name"] for c in columns]
        assert "name" in column_names, "personas should have 'name' column"

    @pytest.mark.asyncio
    async def test_personas_has_system_prompt_column(self):
        """personas 테이블에 system_prompt 컬럼이 있어야 한다"""
        columns = await get_table_columns("personas")
        column_names = [c["column_name"] for c in columns]
        assert "system_prompt" in column_names, "personas should have 'system_prompt' column"

    @pytest.mark.asyncio
    async def test_personas_has_default_persona(self):
        """personas 테이블에 기본 페르소나가 있어야 한다"""
        conn = await get_connection()
        try:
            count = await conn.fetchval("SELECT COUNT(*) FROM personas WHERE is_active = true")
            assert count >= 1, "personas should have at least 1 active persona"
        finally:
            await conn.close()


@pytest.mark.skipif(not POSTGRES_AVAILABLE, reason="PostgreSQL not available")
class TestDocumentsTable:
    """documents 테이블 테스트 (RAG용)"""

    @pytest.mark.asyncio
    async def test_documents_table_exists(self):
        """documents 테이블이 존재해야 한다"""
        exists = await table_exists("documents")
        assert exists, "Table 'documents' should exist"

    @pytest.mark.asyncio
    async def test_documents_has_filename_column(self):
        """documents 테이블에 filename 컬럼이 있어야 한다"""
        columns = await get_table_columns("documents")
        column_names = [c["column_name"] for c in columns]
        assert "filename" in column_names, "documents should have 'filename' column"
