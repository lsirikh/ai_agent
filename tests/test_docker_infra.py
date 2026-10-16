"""
Test Docker Infrastructure Services

TDD Phase 0.2: Redis, PostgreSQL, ChromaDB 연결 테스트

Note: 이 테스트는 Docker 서비스가 실행 중일 때만 동작합니다.
      Docker가 없으면 테스트가 skip됩니다.
"""
import os
import socket

import pytest

# 테스트 환경 설정
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
POSTGRES_USER = os.getenv("POSTGRES_USER", "edgevoice")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "edgevoice123")
POSTGRES_DB = os.getenv("POSTGRES_DB", "edgevoice")
CHROMADB_HOST = os.getenv("CHROMADB_HOST", "localhost")
CHROMADB_PORT = int(os.getenv("CHROMADB_PORT", "8010"))


def is_port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    """포트가 열려있는지 확인"""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False


# Docker 서비스 가용성 체크
REDIS_AVAILABLE = is_port_open(REDIS_HOST, REDIS_PORT)
POSTGRES_AVAILABLE = is_port_open(POSTGRES_HOST, POSTGRES_PORT)
CHROMADB_AVAILABLE = is_port_open(CHROMADB_HOST, CHROMADB_PORT)


@pytest.mark.skipif(not REDIS_AVAILABLE, reason="Redis not available")
class TestRedisConnection:
    """Redis 연결 테스트"""

    @pytest.mark.asyncio
    async def test_redis_connection(self):
        """Redis 서버에 연결하고 PING 명령이 성공해야 한다"""
        import redis.asyncio as redis

        client = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            decode_responses=True
        )
        try:
            result = await client.ping()
            assert result is True, "Redis PING should return True"
        finally:
            await client.aclose()

    @pytest.mark.asyncio
    async def test_redis_set_get(self):
        """Redis SET/GET 명령이 정상 동작해야 한다"""
        import redis.asyncio as redis

        client = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            decode_responses=True
        )
        try:
            test_key = "edgevoice:test:key"
            test_value = "test_value"

            await client.set(test_key, test_value)
            result = await client.get(test_key)
            assert result == test_value, f"Expected {test_value}, got {result}"

            # 정리
            await client.delete(test_key)
        finally:
            await client.aclose()

    @pytest.mark.asyncio
    async def test_redis_pubsub(self):
        """Redis Pub/Sub이 정상 동작해야 한다"""
        import asyncio

        import redis.asyncio as redis

        client = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            decode_responses=True
        )
        try:
            channel = "edgevoice:test:channel"
            received_messages = []

            pubsub = client.pubsub()
            await pubsub.subscribe(channel)

            # 메시지 발행
            await client.publish(channel, "test_message")

            # 메시지 수신 (타임아웃 포함)
            async def receive():
                async for message in pubsub.listen():
                    if message["type"] == "message":
                        received_messages.append(message["data"])
                        break

            await asyncio.wait_for(receive(), timeout=2.0)
            assert "test_message" in received_messages

            await pubsub.unsubscribe(channel)
        finally:
            await client.aclose()


@pytest.mark.skipif(not POSTGRES_AVAILABLE, reason="PostgreSQL not available")
class TestPostgresConnection:
    """PostgreSQL 연결 테스트"""

    @pytest.mark.asyncio
    async def test_postgres_connection(self):
        """PostgreSQL 서버에 연결할 수 있어야 한다"""
        import asyncpg

        conn = await asyncpg.connect(
            host=POSTGRES_HOST,
            port=POSTGRES_PORT,
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD,
            database=POSTGRES_DB
        )
        try:
            result = await conn.fetchval("SELECT 1")
            assert result == 1, "PostgreSQL SELECT 1 should return 1"
        finally:
            await conn.close()

    @pytest.mark.asyncio
    async def test_postgres_version(self):
        """PostgreSQL 버전이 16 이상이어야 한다"""
        import asyncpg

        conn = await asyncpg.connect(
            host=POSTGRES_HOST,
            port=POSTGRES_PORT,
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD,
            database=POSTGRES_DB
        )
        try:
            version = await conn.fetchval("SHOW server_version")
            major_version = int(version.split(".")[0])
            assert major_version >= 16, f"PostgreSQL version should be >= 16, got {version}"
        finally:
            await conn.close()


@pytest.mark.skipif(not CHROMADB_AVAILABLE, reason="ChromaDB not available")
class TestChromaDBConnection:
    """ChromaDB 연결 테스트"""

    def test_chromadb_connection(self):
        """ChromaDB 서버에 연결할 수 있어야 한다"""
        import chromadb

        client = chromadb.HttpClient(
            host=CHROMADB_HOST,
            port=CHROMADB_PORT
        )
        # heartbeat 체크
        heartbeat = client.heartbeat()
        assert heartbeat is not None, "ChromaDB heartbeat should return a value"

    def test_chromadb_create_collection(self):
        """ChromaDB에서 컬렉션을 생성할 수 있어야 한다"""
        import chromadb

        client = chromadb.HttpClient(
            host=CHROMADB_HOST,
            port=CHROMADB_PORT
        )
        collection_name = "edgevoice_test_collection"

        # 기존 컬렉션 삭제 (있으면)
        try:
            client.delete_collection(collection_name)
        except Exception:
            pass

        # 컬렉션 생성
        collection = client.create_collection(name=collection_name)
        assert collection is not None
        assert collection.name == collection_name

        # 정리
        client.delete_collection(collection_name)

    def test_chromadb_add_and_query(self):
        """ChromaDB에서 문서 추가 및 검색이 가능해야 한다"""
        import chromadb

        client = chromadb.HttpClient(
            host=CHROMADB_HOST,
            port=CHROMADB_PORT
        )
        collection_name = "edgevoice_test_query"

        # 기존 컬렉션 삭제 (있으면)
        try:
            client.delete_collection(collection_name)
        except Exception:
            pass

        collection = client.create_collection(name=collection_name)

        # 문서 추가
        collection.add(
            documents=["테스트 문서입니다"],
            ids=["doc1"]
        )

        # 검색
        results = collection.query(
            query_texts=["테스트"],
            n_results=1
        )
        assert len(results["documents"][0]) == 1
        assert "테스트" in results["documents"][0][0]

        # 정리
        client.delete_collection(collection_name)
