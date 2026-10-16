"""
EdgeVoice RAG Service API

독립형 RAG (Retrieval-Augmented Generation) 서비스
문서 저장, 임베딩, 검색 기능 제공
Phase 60: PostgreSQL + pgvector 영속화
"""
import json
import logging
import os
import uuid
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# ============================================
# Configuration
# ============================================

EMBEDDING_SERVICE_URL = os.getenv("EMBEDDING_SERVICE_URL", "http://localhost:11004")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://edgevoice:edgevoice@localhost:5432/edgevoice")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")


# ============================================
# Pydantic Models
# ============================================

class DocumentAddRequest(BaseModel):
    content: str
    metadata: Optional[Dict[str, Any]] = None
    doc_id: Optional[str] = None


class DocumentAddResponse(BaseModel):
    doc_id: str
    chunk_count: int


class SearchRequest(BaseModel):
    query: str
    top_k: Optional[int] = 3
    filter_metadata: Optional[Dict[str, Any]] = None


class SearchResult(BaseModel):
    content: str
    score: float
    metadata: Dict[str, Any]
    doc_id: str


class SearchResponse(BaseModel):
    results: List[SearchResult]
    query: str


# ============================================
# PostgreSQL Connection Pool
# ============================================

_pool = None


async def get_pool():
    global _pool
    if _pool is None:
        import asyncpg
        _pool = await asyncpg.create_pool(
            DATABASE_URL,
            min_size=2,
            max_size=10,
            command_timeout=60.0
        )
        # pgvector 타입 등록
        async with _pool.acquire() as conn:
            await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
            # vector 타입을 text로 변환하여 처리
    return _pool


async def close_pool():
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


# ============================================
# PostgreSQL Storage Functions
# ============================================

async def store_document_pg(
    doc_id: str,
    content: str,
    chunks: List[str],
    embeddings: List[List[float]],
    metadata: Optional[Dict[str, Any]] = None
) -> int:
    """문서 + 청크 + 벡터를 트랜잭션으로 저장"""
    pool = await get_pool()
    meta = metadata or {}
    meta_json = json.dumps(meta)

    async with pool.acquire() as conn:
        async with conn.transaction():
            # documents 테이블에 저장
            await conn.execute(
                """
                INSERT INTO documents (id, filename, status, chunk_count, metadata)
                VALUES ($1, $2, 'indexed', $3, $4::jsonb)
                ON CONFLICT (id) DO UPDATE SET
                    status = 'indexed',
                    chunk_count = $3,
                    metadata = $4::jsonb,
                    indexed_at = NOW()
                """,
                uuid.UUID(doc_id),
                meta.get("filename", "uploaded_document"),
                len(chunks),
                meta_json
            )

            # 기존 청크 삭제 (재인덱싱 시)
            await conn.execute(
                "DELETE FROM document_chunks WHERE document_id = $1",
                uuid.UUID(doc_id)
            )

            # 청크 + 벡터 저장
            for i, (chunk, emb) in enumerate(zip(chunks, embeddings)):
                emb_str = "[" + ",".join(str(v) for v in emb) + "]"
                await conn.execute(
                    """
                    INSERT INTO document_chunks
                        (document_id, chunk_index, content, embedding, metadata)
                    VALUES ($1, $2, $3, $4::vector, $5::jsonb)
                    """,
                    uuid.UUID(doc_id),
                    i,
                    chunk,
                    emb_str,
                    meta_json
                )

    return len(chunks)


async def search_pg(
    query_embedding: List[float],
    top_k: int = 3,
    filter_metadata: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """pgvector 코사인 유사도 검색"""
    pool = await get_pool()
    emb_str = "[" + ",".join(str(v) for v in query_embedding) + "]"

    async with pool.acquire() as conn:
        if filter_metadata:
            filter_json = json.dumps(filter_metadata)
            rows = await conn.fetch(
                """
                SELECT dc.content, dc.metadata, dc.document_id,
                       1 - (dc.embedding <=> $1::vector) AS score
                FROM document_chunks dc
                WHERE dc.embedding IS NOT NULL
                  AND dc.metadata @> $3::jsonb
                ORDER BY dc.embedding <=> $1::vector
                LIMIT $2
                """,
                emb_str, top_k, filter_json
            )
        else:
            rows = await conn.fetch(
                """
                SELECT dc.content, dc.metadata, dc.document_id,
                       1 - (dc.embedding <=> $1::vector) AS score
                FROM document_chunks dc
                WHERE dc.embedding IS NOT NULL
                ORDER BY dc.embedding <=> $1::vector
                LIMIT $2
                """,
                emb_str, top_k
            )

    results = []
    for row in rows:
        meta = json.loads(row["metadata"]) if isinstance(row["metadata"], str) else row["metadata"]
        results.append({
            "content": row["content"],
            "score": float(row["score"]),
            "metadata": meta or {},
            "doc_id": str(row["document_id"])
        })

    return results


async def delete_document_pg(doc_id: str) -> bool:
    """문서 삭제 (CASCADE로 청크 자동 삭제)"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM documents WHERE id = $1",
            uuid.UUID(doc_id)
        )
        return result != "DELETE 0"


async def list_documents_pg() -> List[Dict[str, Any]]:
    """문서 목록 조회"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, filename, chunk_count, metadata, status, uploaded_at, indexed_at
            FROM documents
            WHERE status != 'deleted'
            ORDER BY uploaded_at DESC NULLS LAST
            """
        )

    return [
        {
            "doc_id": str(row["id"]),
            "metadata": json.loads(row["metadata"]) if isinstance(row["metadata"], str) else (row["metadata"] or {}),
            "chunk_count": row["chunk_count"] or 0,
            "filename": row["filename"],
            "status": row["status"],
            # indexed_at 은 비어 있다 — 올린 시각은 uploaded_at
            "uploaded_at": (
                row["uploaded_at"].isoformat() if row["uploaded_at"] else None
            )
        }
        for row in rows
    ]


async def get_document_count() -> tuple:
    """문서/청크 수 조회"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        doc_count = await conn.fetchval(
            "SELECT COUNT(*) FROM documents WHERE status != 'deleted'"
        )
        chunk_count = await conn.fetchval(
            "SELECT COUNT(*) FROM document_chunks WHERE embedding IS NOT NULL"
        )
    return doc_count or 0, chunk_count or 0


# ============================================
# Text Chunking
# ============================================

def chunk_text(text: str, chunk_size: int = 256, chunk_overlap: int = 32) -> List[str]:
    """텍스트를 청크로 분리"""
    if not text or not text.strip():
        return []

    text = text.strip()

    if len(text) <= chunk_size:
        return [text]

    chunks = []
    start = 0

    while start < len(text):
        end = start + chunk_size

        if end < len(text):
            for sep in ['. ', '! ', '? ', '。', '！', '？']:
                last_sep = text[start:end].rfind(sep)
                if last_sep > chunk_size // 2:
                    end = start + last_sep + len(sep)
                    break

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        start = end - chunk_overlap

    return chunks


# ============================================
# Embedding Service Client
# ============================================

async def get_embedding(text: str) -> List[float]:
    """Embedding 서비스에서 단일 텍스트 임베딩 획득"""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{EMBEDDING_SERVICE_URL}/embed",
            json={"text": text}
        )
        response.raise_for_status()
        data = response.json()
        return data["embedding"]


async def get_embeddings_batch(texts: List[str]) -> List[List[float]]:
    """Embedding 서비스에서 배치 임베딩 획득"""
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            f"{EMBEDDING_SERVICE_URL}/embed/batch",
            json={"texts": texts}
        )
        response.raise_for_status()
        data = response.json()
        return data["embeddings"]


# ============================================
# FastAPI App
# ============================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """앱 시작/종료 시 DB 풀 관리"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        doc_count = await conn.fetchval(
            "SELECT COUNT(*) FROM documents WHERE status != 'deleted'"
        )
        chunk_count = await conn.fetchval(
            "SELECT COUNT(*) FROM document_chunks WHERE embedding IS NOT NULL"
        )
    logger.info("RAG service started. Documents: %d, Chunks with embeddings: %d", doc_count, chunk_count)
    yield
    await close_pool()
    logger.info("RAG service stopped.")


app = FastAPI(
    title="EdgeVoice RAG Service",
    description="Document storage and retrieval service with pgvector",
    version="2.0.0",
    lifespan=lifespan
)


@app.get("/health")
async def health_check():
    """헬스 체크"""
    return {
        "status": "healthy",
        "service": "rag"
    }


@app.get("/info")
async def get_service_info():
    """서비스 상세 정보 조회"""
    doc_count, chunk_count = await get_document_count()
    return {
        "service": "rag",
        "settings": {
            "embedding_service_url": EMBEDDING_SERVICE_URL,
            "storage": "postgresql+pgvector",
            "top_k": 5,
            "similarity_threshold": 0.7
        },
        "stats": {
            "document_count": doc_count,
            "chunk_count": chunk_count
        },
        "status": "ready"
    }


@app.post("/documents", response_model=DocumentAddResponse)
async def add_document(request: DocumentAddRequest):
    """문서 추가 (임베딩 → PostgreSQL 저장)"""
    doc_id = request.doc_id or str(uuid.uuid4())

    chunks = chunk_text(request.content)

    if not chunks:
        raise HTTPException(status_code=400, detail="Empty document")

    try:
        embeddings = await get_embeddings_batch(chunks)

        chunk_count = await store_document_pg(
            doc_id=doc_id,
            content=request.content,
            chunks=chunks,
            embeddings=embeddings,
            metadata=request.metadata
        )

        return DocumentAddResponse(doc_id=doc_id, chunk_count=chunk_count)

    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Embedding service error: {str(e)}")
    except Exception as e:
        logger.error("Failed to store document: %s", e)
        raise HTTPException(status_code=500, detail=f"Storage error: {str(e)}")


@app.delete("/documents/{doc_id}")
async def delete_document(doc_id: str):
    """문서 삭제"""
    success = await delete_document_pg(doc_id)
    if not success:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"status": "deleted", "doc_id": doc_id}


@app.get("/documents")
async def list_documents():
    """문서 목록"""
    docs = await list_documents_pg()
    return {"documents": docs}


@app.post("/search", response_model=SearchResponse)
async def search(request: SearchRequest):
    """벡터 유사도 검색 (pgvector)"""
    try:
        query_embedding = await get_embedding(request.query)

        results = await search_pg(
            query_embedding=query_embedding,
            top_k=request.top_k or 3,
            filter_metadata=request.filter_metadata
        )

        return SearchResponse(
            results=[SearchResult(**r) for r in results],
            query=request.query
        )

    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"Embedding service error: {str(e)}")


@app.post("/retrieve")
async def retrieve(request: SearchRequest):
    """검색 및 컨텍스트 반환 (LLM용)"""
    search_response = await search(request)

    context = "\n\n".join([r.content for r in search_response.results])

    return {
        "context": context,
        "results": search_response.results,
        "query": request.query
    }
