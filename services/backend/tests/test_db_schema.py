"""
Test: DB Schema Migration
Phase 18.3.2: 세션/메시지 테이블 컬럼 확장

TDD Red Phase: 이 테스트는 처음에 실패해야 합니다.

Note: These tests verify that the migration SQL file contains the required
column definitions. Actual database testing requires a running PostgreSQL.
"""
import os
import pytest


# Path: services/backend/tests -> services/backend -> services -> AI agent -> config/postgres/init.sql
INIT_SQL_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
    "config", "postgres", "init.sql"
)


def read_init_sql() -> str:
    """Read the init.sql file content"""
    with open(INIT_SQL_PATH, "r", encoding="utf-8") as f:
        return f.read()


def test_sessions_table_has_type_column():
    """sessions 테이블에 type 컬럼이 정의되어 있는지 확인"""
    sql_content = read_init_sql()

    # sessions 테이블 정의 부분에서 type 컬럼 확인
    # CREATE TABLE sessions에 session_type VARCHAR가 있어야 함
    lines = sql_content.split('\n')
    in_sessions_table = False
    has_type = False

    for line in lines:
        if 'CREATE TABLE' in line and 'sessions' in line and 'active_sessions' not in line:
            in_sessions_table = True
        elif in_sessions_table and ');' in line:
            in_sessions_table = False
        elif in_sessions_table and ('session_type' in line.lower() or 'type VARCHAR' in line):
            has_type = True
            break

    assert has_type, "init.sql에 sessions.session_type 컬럼 정의가 없습니다"


def test_sessions_table_has_source_column():
    """sessions 테이블에 source 컬럼이 정의되어 있는지 확인"""
    sql_content = read_init_sql()

    # sessions 테이블 정의 부분에서 source 컬럼 확인
    lines = sql_content.split('\n')
    in_sessions_table = False
    has_source = False

    for line in lines:
        if 'CREATE TABLE' in line and 'sessions' in line and 'active_sessions' not in line:
            in_sessions_table = True
        elif in_sessions_table and ');' in line:
            in_sessions_table = False
        elif in_sessions_table and 'source' in line.lower() and 'rag_sources' not in line.lower():
            has_source = True
            break

    assert has_source, "init.sql에 sessions.source 컬럼 정의가 없습니다"


def test_messages_table_has_source_column():
    """messages 테이블에 source 컬럼이 정의되어 있는지 확인"""
    sql_content = read_init_sql()

    # messages 테이블에 message_source 또는 source 컬럼이 있어야 함
    # role, content 다음에 source가 나와야 함
    lines = sql_content.split('\n')
    in_messages_table = False
    has_source = False

    for line in lines:
        if 'CREATE TABLE' in line and 'messages' in line:
            in_messages_table = True
        elif in_messages_table and ');' in line:
            in_messages_table = False
        elif in_messages_table and 'source' in line.lower() and 'rag_sources' not in line.lower():
            has_source = True
            break

    assert has_source, "init.sql에 messages.source 컬럼 정의가 없습니다"


def test_messages_table_has_audio_url_column():
    """messages 테이블에 audio_url 컬럼이 정의되어 있는지 확인"""
    sql_content = read_init_sql()

    # messages 테이블에 audio_url 컬럼이 있어야 함
    lines = sql_content.split('\n')
    in_messages_table = False
    has_audio_url = False

    for line in lines:
        if 'CREATE TABLE' in line and 'messages' in line:
            in_messages_table = True
        elif in_messages_table and ');' in line:
            in_messages_table = False
        elif in_messages_table and 'audio_url' in line.lower():
            has_audio_url = True
            break

    assert has_audio_url, "init.sql에 messages.audio_url 컬럼 정의가 없습니다"
