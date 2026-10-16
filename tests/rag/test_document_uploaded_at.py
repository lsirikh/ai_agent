"""
문서 목록 업로드 시각 테스트

목록이 비어 있는 indexed_at 을 uploaded_at 으로 돌려줘 지식 베이스 화면에 '-' 로 보였다.
DB 에는 uploaded_at 이 채워져 있다.
"""

from datetime import datetime, timezone
from unittest.mock import patch

import pytest


class FakeConn:
    def __init__(self, rows):
        self.rows = rows

    async def fetch(self, query):
        return self.rows


class FakePool:
    def __init__(self, rows):
        self.conn = FakeConn(rows)

    def acquire(self):
        pool = self

        class Ctx:
            async def __aenter__(self):
                return pool.conn

            async def __aexit__(self, *exc):
                return False

        return Ctx()


@pytest.mark.asyncio
async def test_should_report_uploaded_at_from_upload_column() -> None:
    from services.rag.app import main

    uploaded = datetime(2026, 5, 7, 1, 33, 19, tzinfo=timezone.utc)
    row = {
        "id": "a9b8",
        "filename": "test_doc.txt",
        "chunk_count": 1,
        "metadata": "{}",
        "status": "active",
        "uploaded_at": uploaded,
        "indexed_at": None,
    }

    async def fake_pool():
        return FakePool([row])

    with patch.object(main, "get_pool", fake_pool):
        docs = await main.list_documents_pg()

    assert docs[0]["uploaded_at"] == uploaded.isoformat()
