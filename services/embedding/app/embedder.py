"""
Embedding Service

Phase 4.1: BGE-M3 기반 텍스트 임베딩 서비스
"""
import asyncio
import logging
import os
from typing import List, Optional, Union

import numpy as np

logger = logging.getLogger(__name__)


# 싱글톤 인스턴스
_embedder_instance: Optional["Embedder"] = None


def get_embedder() -> "Embedder":
    """
    Embedder 싱글톤 인스턴스 반환

    Returns:
        Embedder 인스턴스
    """
    global _embedder_instance
    if _embedder_instance is None:
        _embedder_instance = Embedder()
    return _embedder_instance


class Embedder:
    """
    텍스트 임베딩 생성기

    BGE-M3 모델을 사용하여 텍스트를 벡터로 변환합니다.

    Attributes:
        model_name: 사용할 모델 이름
        max_length: 최대 토큰 길이
        batch_size: 배치 크기
        normalize: 벡터 정규화 여부
    """

    def __init__(
        self,
        model_name: str = "BAAI/bge-m3",
        max_length: int = 8192,
        batch_size: int = 16,
        normalize: bool = True
    ):
        """
        Embedder 초기화

        Args:
            model_name: 사용할 모델 이름
            max_length: 최대 토큰 길이
            batch_size: 배치 처리 크기
            normalize: 출력 벡터 정규화 여부
        """
        self.model_name = model_name
        self.max_length = max_length
        self.batch_size = batch_size
        self.normalize = normalize
        self._embedding_dim = 1024  # BGE-M3 default

        # 모델 로드
        self.model = self._load_model()

    def _load_model(self):
        """
        임베딩 모델 로드

        Returns:
            로드된 SentenceTransformer 모델 또는 None (로드 실패 시)
        """
        try:
            import torch
            from sentence_transformers import SentenceTransformer

            model_path = os.getenv("MODEL_PATH", "/models")
            device = os.getenv("DEVICE", "cuda" if torch.cuda.is_available() else "cpu")

            if os.path.exists(model_path) and any(
                f.endswith((".bin", ".safetensors"))
                for f in os.listdir(model_path)
            ):
                logger.info("Loading model from local path: %s (device=%s)", model_path, device)
                model = SentenceTransformer(model_path, device=device)
            else:
                logger.info("Loading model from hub: %s (device=%s)", self.model_name, device)
                model = SentenceTransformer(self.model_name, device=device)

            self._embedding_dim = model.get_sentence_embedding_dimension()
            logger.info("Model loaded successfully. Dimension: %d", self._embedding_dim)
            return model

        except Exception as e:
            logger.error("Failed to load embedding model: %s", e)
            return None

    @property
    def embedding_dim(self) -> int:
        """임베딩 차원 반환"""
        return self._embedding_dim

    def get_embedding_dimension(self) -> int:
        """
        임베딩 차원 조회

        Returns:
            임베딩 벡터 차원
        """
        return self._embedding_dim

    def _encode(self, text: str) -> np.ndarray:
        """
        단일 텍스트 인코딩

        Args:
            text: 인코딩할 텍스트

        Returns:
            임베딩 벡터
        """
        if self.model is None:
            return np.zeros(self._embedding_dim, dtype=np.float32)
        vector = self.model.encode(text, normalize_embeddings=self.normalize)
        return vector.astype(np.float32)

    def _encode_batch(self, texts: List[str]) -> np.ndarray:
        """
        배치 텍스트 인코딩

        Args:
            texts: 인코딩할 텍스트 리스트

        Returns:
            임베딩 벡터 배열
        """
        if self.model is None:
            return np.zeros((len(texts), self._embedding_dim), dtype=np.float32)
        vectors = self.model.encode(
            texts, normalize_embeddings=self.normalize, batch_size=self.batch_size
        )
        return vectors.astype(np.float32)

    def embed(self, text: str) -> np.ndarray:
        """
        텍스트를 임베딩 벡터로 변환

        Args:
            text: 임베딩할 텍스트

        Returns:
            임베딩 벡터 (float32)

        Raises:
            ValueError: 빈 텍스트인 경우
        """
        if not text or not text.strip():
            raise ValueError("Text cannot be empty")

        vector = self._encode(text)

        if self.normalize:
            norm = np.linalg.norm(vector)
            if norm > 0:
                vector = vector / norm

        return vector.astype(np.float32)

    def embed_batch(self, texts: List[str]) -> np.ndarray:
        """
        텍스트 배치를 임베딩 벡터로 변환

        Args:
            texts: 임베딩할 텍스트 리스트

        Returns:
            임베딩 벡터 배열 (N x embedding_dim)
        """
        if not texts:
            return np.array([], dtype=np.float32).reshape(0, self._embedding_dim)

        all_vectors = []

        # 배치 단위로 처리
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i:i + self.batch_size]
            vectors = self._encode_batch(batch)
            all_vectors.append(vectors)

        result = np.vstack(all_vectors)

        if self.normalize:
            norms = np.linalg.norm(result, axis=1, keepdims=True)
            norms = np.where(norms > 0, norms, 1)  # Avoid division by zero
            result = result / norms

        return result.astype(np.float32)

    async def embed_async(self, text: str) -> np.ndarray:
        """
        비동기 텍스트 임베딩

        Args:
            text: 임베딩할 텍스트

        Returns:
            임베딩 벡터
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.embed, text)

    async def embed_batch_async(self, texts: List[str]) -> np.ndarray:
        """
        비동기 배치 임베딩

        Args:
            texts: 임베딩할 텍스트 리스트

        Returns:
            임베딩 벡터 배열
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.embed_batch, texts)

    def cosine_similarity(self, vec1: np.ndarray, vec2: np.ndarray) -> float:
        """
        두 벡터 간 코사인 유사도 계산

        Args:
            vec1: 첫 번째 벡터
            vec2: 두 번째 벡터

        Returns:
            코사인 유사도 (-1 ~ 1)
        """
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return float(np.dot(vec1, vec2) / (norm1 * norm2))

    def batch_cosine_similarity(
        self,
        query: np.ndarray,
        candidates: np.ndarray
    ) -> np.ndarray:
        """
        쿼리 벡터와 후보 벡터들 간의 코사인 유사도 계산

        Args:
            query: 쿼리 벡터 (1D)
            candidates: 후보 벡터 배열 (2D: N x dim)

        Returns:
            유사도 배열 (N,)
        """
        query_norm = np.linalg.norm(query)
        if query_norm == 0:
            return np.zeros(len(candidates), dtype=np.float32)

        query_normalized = query / query_norm

        candidates_norms = np.linalg.norm(candidates, axis=1, keepdims=True)
        candidates_norms = np.where(candidates_norms > 0, candidates_norms, 1)
        candidates_normalized = candidates / candidates_norms

        similarities = np.dot(candidates_normalized, query_normalized)
        return similarities.astype(np.float32)

    def warm_up(self) -> None:
        """
        모델 웜업

        첫 번째 인퍼런스 지연을 줄이기 위해 테스트 문장을 임베딩합니다.
        """
        test_text = "This is a warm-up sentence for the embedding model."
        self._encode(test_text)
