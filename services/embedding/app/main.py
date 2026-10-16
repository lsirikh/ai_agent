"""
Embedding Service Main

Phase 4.1: Embedding Service FastAPI 애플리케이션
"""
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .embedder import Embedder, get_embedder

# FastAPI 앱 생성
app = FastAPI(
    title="Embedding Service",
    description="EdgeVoice Embedding Service - BGE-M3 based text embeddings",
    version="0.1.0"
)

# 전역 임베더 인스턴스 (lazy loading)
_embedder: Optional[Embedder] = None


def get_embedder_instance() -> Embedder:
    """임베더 인스턴스 반환 (lazy loading)"""
    global _embedder
    if _embedder is None:
        _embedder = get_embedder()
    return _embedder


# Pydantic 모델
class EmbedRequest(BaseModel):
    text: str


class EmbedResponse(BaseModel):
    embedding: List[float]
    dimension: int


class BatchEmbedRequest(BaseModel):
    texts: List[str]


class BatchEmbedResponse(BaseModel):
    embeddings: List[List[float]]
    count: int


class SimilarityRequest(BaseModel):
    text1: str
    text2: str


class SimilarityResponse(BaseModel):
    similarity: float


# Health 엔드포인트
@app.get("/health")
async def health():
    """
    헬스 체크 엔드포인트 - 단순 생존 확인만

    Returns:
        서비스 상태 정보
    """
    embedder = get_embedder_instance()
    return {
        "status": "healthy",
        "service": "embedding",
        "model_loaded": embedder.model is not None
    }


@app.get("/info")
async def get_service_info():
    """
    서비스 상세 정보 조회 (Phase 28.1)

    Dashboard에서 사용할 서비스 정보를 반환합니다.
    /health와 분리하여 상세 정보만 제공합니다.
    """
    import os
    embedder = get_embedder_instance()
    device = os.getenv("DEVICE", "cpu")

    return {
        "service": "embedding",
        "model": {
            "name": embedder.model_name,
            "dimension": embedder.embedding_dim,
            "device": device
        },
        "status": "ready"
    }


# Embed 엔드포인트
@app.post("/embed", response_model=EmbedResponse)
async def embed(request: EmbedRequest):
    """
    단일 텍스트 임베딩

    Args:
        request: 텍스트 요청

    Returns:
        임베딩 벡터
    """
    if not request.text or not request.text.strip():
        raise HTTPException(status_code=400, detail="Text cannot be empty")

    embedder = get_embedder_instance()

    try:
        vector = await embedder.embed_async(request.text)
        return EmbedResponse(
            embedding=vector.tolist(),
            dimension=len(vector)
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Batch Embed 엔드포인트
@app.post("/embed/batch", response_model=BatchEmbedResponse)
async def embed_batch(request: BatchEmbedRequest):
    """
    배치 텍스트 임베딩

    Args:
        request: 텍스트 리스트 요청

    Returns:
        임베딩 벡터 리스트
    """
    if not request.texts:
        return BatchEmbedResponse(embeddings=[], count=0)

    embedder = get_embedder_instance()

    try:
        vectors = await embedder.embed_batch_async(request.texts)
        return BatchEmbedResponse(
            embeddings=[v.tolist() for v in vectors],
            count=len(vectors)
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Similarity 엔드포인트
@app.post("/similarity", response_model=SimilarityResponse)
async def similarity(request: SimilarityRequest):
    """
    두 텍스트 간 유사도 계산

    Args:
        request: 두 텍스트 요청

    Returns:
        코사인 유사도
    """
    if not request.text1 or not request.text2:
        raise HTTPException(status_code=400, detail="Both texts are required")

    embedder = get_embedder_instance()

    try:
        vec1 = await embedder.embed_async(request.text1)
        vec2 = await embedder.embed_async(request.text2)
        sim = embedder.cosine_similarity(vec1, vec2)

        return SimilarityResponse(similarity=sim)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# 애플리케이션 이벤트
@app.on_event("startup")
async def startup_event():
    """애플리케이션 시작 시 초기화"""
    embedder = get_embedder_instance()
    embedder.warm_up()


@app.on_event("shutdown")
async def shutdown_event():
    """애플리케이션 종료 시 정리"""
    pass
