"""
Embedding Service Tests

Phase 4.1: BGE-M3 기반 임베딩 서비스 테스트
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest


class TestEmbeddingModelLoading:
    """임베딩 모델 로드 테스트"""

    def test_embedding_model_loads(self):
        """BGE-M3 모델이 로드되어야 한다"""
        from services.embedding.app.embedder import Embedder

        with patch.object(Embedder, '_load_model') as mock_load:
            mock_load.return_value = MagicMock()
            embedder = Embedder()

            assert embedder is not None
            assert embedder.model is not None

    def test_embedder_with_custom_config(self):
        """커스텀 설정으로 초기화할 수 있어야 한다"""
        from services.embedding.app.embedder import Embedder

        with patch.object(Embedder, '_load_model') as mock_load:
            mock_load.return_value = MagicMock()
            embedder = Embedder(
                model_name="BAAI/bge-m3",
                max_length=512,
                batch_size=32
            )

            assert embedder.model_name == "BAAI/bge-m3"
            assert embedder.max_length == 512
            assert embedder.batch_size == 32

    def test_embedder_default_config(self):
        """기본 설정이 올바르게 적용되어야 한다"""
        from services.embedding.app.embedder import Embedder

        with patch.object(Embedder, '_load_model') as mock_load:
            mock_load.return_value = MagicMock()
            embedder = Embedder()

            assert embedder.model_name == "BAAI/bge-m3"
            assert embedder.max_length == 8192
            assert embedder.batch_size == 16


class TestTextEmbedding:
    """텍스트 임베딩 테스트"""

    def test_embed_text_returns_vector(self):
        """텍스트 임베딩이 벡터를 반환해야 한다"""
        from services.embedding.app.embedder import Embedder

        with patch.object(Embedder, '_load_model') as mock_load:
            mock_model = MagicMock()
            mock_load.return_value = mock_model

            embedder = Embedder()

            # Mock encode to return a vector
            mock_vector = np.random.randn(1024).astype(np.float32)
            embedder._encode = MagicMock(return_value=mock_vector)

            text = "안녕하세요, 테스트 문장입니다."
            vector = embedder.embed(text)

            assert vector is not None
            assert isinstance(vector, np.ndarray)
            assert vector.dtype == np.float32

    def test_embed_text_normalized(self):
        """임베딩 벡터가 정규화되어야 한다"""
        from services.embedding.app.embedder import Embedder

        with patch.object(Embedder, '_load_model') as mock_load:
            mock_load.return_value = MagicMock()
            embedder = Embedder(normalize=True)

            # Mock normalized vector
            mock_vector = np.random.randn(1024).astype(np.float32)
            mock_vector = mock_vector / np.linalg.norm(mock_vector)
            embedder._encode = MagicMock(return_value=mock_vector)

            text = "테스트 문장"
            vector = embedder.embed(text)

            # L2 norm should be approximately 1
            norm = np.linalg.norm(vector)
            assert np.isclose(norm, 1.0, atol=1e-5)

    def test_embed_empty_text(self):
        """빈 텍스트 처리가 올바르게 되어야 한다"""
        from services.embedding.app.embedder import Embedder

        with patch.object(Embedder, '_load_model') as mock_load:
            mock_load.return_value = MagicMock()
            embedder = Embedder()

            # Empty text should return zero vector or raise exception
            with pytest.raises(ValueError):
                embedder.embed("")


class TestBatchEmbedding:
    """배치 임베딩 테스트"""

    def test_embed_batch(self):
        """배치 임베딩이 동작해야 한다"""
        from services.embedding.app.embedder import Embedder

        with patch.object(Embedder, '_load_model') as mock_load:
            mock_load.return_value = MagicMock()
            embedder = Embedder()

            texts = [
                "첫 번째 문장입니다.",
                "두 번째 문장입니다.",
                "세 번째 문장입니다."
            ]

            # Mock batch encode
            mock_vectors = np.random.randn(3, 1024).astype(np.float32)
            embedder._encode_batch = MagicMock(return_value=mock_vectors)

            vectors = embedder.embed_batch(texts)

            assert vectors is not None
            assert len(vectors) == 3
            assert vectors.shape == (3, 1024)

    def test_embed_batch_preserves_order(self):
        """배치 임베딩이 순서를 유지해야 한다"""
        from services.embedding.app.embedder import Embedder

        with patch.object(Embedder, '_load_model') as mock_load:
            mock_load.return_value = MagicMock()
            embedder = Embedder()

            texts = ["A", "B", "C"]

            # Create distinct vectors for each text
            mock_vectors = np.array([
                [1.0] + [0.0] * 1023,
                [0.0, 1.0] + [0.0] * 1022,
                [0.0, 0.0, 1.0] + [0.0] * 1021
            ], dtype=np.float32)
            embedder._encode_batch = MagicMock(return_value=mock_vectors)

            vectors = embedder.embed_batch(texts)

            # Order should be preserved
            assert vectors[0][0] == 1.0
            assert vectors[1][1] == 1.0
            assert vectors[2][2] == 1.0

    def test_embed_batch_handles_large_batch(self):
        """큰 배치 처리가 청크 단위로 동작해야 한다"""
        from services.embedding.app.embedder import Embedder

        with patch.object(Embedder, '_load_model') as mock_load:
            mock_load.return_value = MagicMock()
            embedder = Embedder(batch_size=4)

            texts = [f"문장 {i}" for i in range(10)]

            # Mock batch encode for multiple calls
            def mock_encode(batch_texts):
                return np.random.randn(len(batch_texts), 1024).astype(np.float32)

            embedder._encode_batch = MagicMock(side_effect=mock_encode)

            vectors = embedder.embed_batch(texts)

            assert len(vectors) == 10
            # Should be called 3 times (4 + 4 + 2)
            assert embedder._encode_batch.call_count == 3


class TestEmbeddingDimension:
    """임베딩 차원 테스트"""

    def test_embedding_dimension(self):
        """임베딩 차원이 올바른지 검증"""
        from services.embedding.app.embedder import Embedder

        with patch.object(Embedder, '_load_model') as mock_load:
            mock_load.return_value = MagicMock()
            embedder = Embedder()

            # BGE-M3 has 1024 dimensions
            mock_vector = np.random.randn(1024).astype(np.float32)
            embedder._encode = MagicMock(return_value=mock_vector)

            vector = embedder.embed("테스트")

            assert embedder.embedding_dim == 1024
            assert len(vector) == 1024

    def test_get_embedding_dimension(self):
        """임베딩 차원 조회 메서드가 동작해야 한다"""
        from services.embedding.app.embedder import Embedder

        with patch.object(Embedder, '_load_model') as mock_load:
            mock_load.return_value = MagicMock()
            embedder = Embedder()
            embedder._embedding_dim = 1024

            dim = embedder.get_embedding_dimension()

            assert dim == 1024


class TestSimilarityComputation:
    """유사도 계산 테스트"""

    def test_cosine_similarity(self):
        """코사인 유사도 계산이 올바른지 확인"""
        from services.embedding.app.embedder import Embedder

        with patch.object(Embedder, '_load_model') as mock_load:
            mock_load.return_value = MagicMock()
            embedder = Embedder()

            # Identical vectors should have similarity 1.0
            vec1 = np.array([1.0, 0.0, 0.0], dtype=np.float32)
            vec2 = np.array([1.0, 0.0, 0.0], dtype=np.float32)

            similarity = embedder.cosine_similarity(vec1, vec2)
            assert np.isclose(similarity, 1.0, atol=1e-5)

            # Orthogonal vectors should have similarity 0.0
            vec3 = np.array([0.0, 1.0, 0.0], dtype=np.float32)
            similarity = embedder.cosine_similarity(vec1, vec3)
            assert np.isclose(similarity, 0.0, atol=1e-5)

    def test_batch_similarity(self):
        """배치 유사도 계산이 동작해야 한다"""
        from services.embedding.app.embedder import Embedder

        with patch.object(Embedder, '_load_model') as mock_load:
            mock_load.return_value = MagicMock()
            embedder = Embedder()

            query = np.array([1.0, 0.0, 0.0], dtype=np.float32)
            candidates = np.array([
                [1.0, 0.0, 0.0],
                [0.0, 1.0, 0.0],
                [0.5, 0.5, 0.0]
            ], dtype=np.float32)

            similarities = embedder.batch_cosine_similarity(query, candidates)

            assert len(similarities) == 3
            assert np.isclose(similarities[0], 1.0, atol=1e-5)
            assert np.isclose(similarities[1], 0.0, atol=1e-5)


class TestAsyncEmbedding:
    """비동기 임베딩 테스트"""

    @pytest.mark.asyncio
    async def test_async_embed(self):
        """비동기 임베딩이 동작해야 한다"""
        from services.embedding.app.embedder import Embedder

        with patch.object(Embedder, '_load_model') as mock_load:
            mock_load.return_value = MagicMock()
            embedder = Embedder()

            mock_vector = np.random.randn(1024).astype(np.float32)
            embedder._encode = MagicMock(return_value=mock_vector)

            vector = await embedder.embed_async("테스트 문장")

            assert vector is not None
            assert len(vector) == 1024

    @pytest.mark.asyncio
    async def test_async_embed_batch(self):
        """비동기 배치 임베딩이 동작해야 한다"""
        from services.embedding.app.embedder import Embedder

        with patch.object(Embedder, '_load_model') as mock_load:
            mock_load.return_value = MagicMock()
            embedder = Embedder()

            texts = ["문장 1", "문장 2", "문장 3"]
            mock_vectors = np.random.randn(3, 1024).astype(np.float32)
            embedder._encode_batch = MagicMock(return_value=mock_vectors)

            vectors = await embedder.embed_batch_async(texts)

            assert len(vectors) == 3


class TestModelCaching:
    """모델 캐싱 테스트"""

    def test_model_singleton(self):
        """모델이 싱글톤으로 관리되어야 한다"""
        from services.embedding.app.embedder import Embedder, get_embedder

        with patch.object(Embedder, '_load_model') as mock_load:
            mock_load.return_value = MagicMock()

            embedder1 = get_embedder()
            embedder2 = get_embedder()

            assert embedder1 is embedder2

    def test_model_warm_up(self):
        """모델 웜업이 동작해야 한다"""
        from services.embedding.app.embedder import Embedder

        with patch.object(Embedder, '_load_model') as mock_load:
            mock_load.return_value = MagicMock()
            embedder = Embedder()

            mock_vector = np.random.randn(1024).astype(np.float32)
            embedder._encode = MagicMock(return_value=mock_vector)

            # Warm up should embed a test sentence
            embedder.warm_up()

            embedder._encode.assert_called_once()
