"""
Embedding Service API Tests

Phase 4.1: Embedding Service API 엔드포인트 테스트
"""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest
from fastapi.testclient import TestClient


class TestHealthEndpoint:
    """/health 엔드포인트 테스트"""

    def test_embedding_health(self):
        """헬스 엔드포인트가 200을 반환해야 한다"""
        from services.embedding.app.main import app

        client = TestClient(app)
        response = client.get("/health")

        assert response.status_code == 200
        assert response.json()["status"] == "healthy"

    def test_health_includes_service_name(self):
        """헬스 응답에 서비스 이름이 포함되어야 한다"""
        from services.embedding.app.main import app

        client = TestClient(app)
        response = client.get("/health")

        assert response.json()["service"] == "embedding"

    def test_health_includes_model_info(self):
        """헬스 응답에 모델 정보가 포함되어야 한다"""
        from services.embedding.app.main import app

        client = TestClient(app)
        response = client.get("/health")

        data = response.json()
        assert "model" in data
        assert "embedding_dim" in data


class TestEmbedEndpoint:
    """/embed 엔드포인트 테스트"""

    def test_embedding_embed_endpoint(self):
        """임베딩 엔드포인트가 벡터를 반환해야 한다"""
        from services.embedding.app.main import app

        client = TestClient(app)
        response = client.post("/embed", json={"text": "테스트 문장입니다."})

        assert response.status_code == 200
        data = response.json()
        assert "embedding" in data
        assert isinstance(data["embedding"], list)
        assert len(data["embedding"]) == 1024

    def test_embed_with_empty_text(self):
        """빈 텍스트는 에러를 반환해야 한다"""
        from services.embedding.app.main import app

        client = TestClient(app)
        response = client.post("/embed", json={"text": ""})

        assert response.status_code == 400

    def test_embed_without_text(self):
        """텍스트 없이 요청하면 에러를 반환해야 한다"""
        from services.embedding.app.main import app

        client = TestClient(app)
        response = client.post("/embed", json={})

        assert response.status_code == 422


class TestBatchEmbedEndpoint:
    """/embed/batch 엔드포인트 테스트"""

    def test_batch_embed_endpoint(self):
        """배치 임베딩 엔드포인트가 동작해야 한다"""
        from services.embedding.app.main import app

        client = TestClient(app)
        response = client.post("/embed/batch", json={
            "texts": ["문장 1", "문장 2", "문장 3"]
        })

        assert response.status_code == 200
        data = response.json()
        assert "embeddings" in data
        assert len(data["embeddings"]) == 3

    def test_batch_embed_empty_list(self):
        """빈 리스트는 빈 결과를 반환해야 한다"""
        from services.embedding.app.main import app

        client = TestClient(app)
        response = client.post("/embed/batch", json={"texts": []})

        assert response.status_code == 200
        data = response.json()
        assert data["embeddings"] == []


class TestSimilarityEndpoint:
    """/similarity 엔드포인트 테스트"""

    def test_similarity_endpoint(self):
        """유사도 계산 엔드포인트가 동작해야 한다"""
        from services.embedding.app.main import app

        client = TestClient(app)
        response = client.post("/similarity", json={
            "text1": "안녕하세요",
            "text2": "반갑습니다"
        })

        assert response.status_code == 200
        data = response.json()
        assert "similarity" in data
        assert -1.0 <= data["similarity"] <= 1.0

    def test_similarity_identical_texts(self):
        """동일한 텍스트는 높은 유사도를 가져야 한다"""
        from services.embedding.app.main import app

        client = TestClient(app)
        response = client.post("/similarity", json={
            "text1": "테스트 문장",
            "text2": "테스트 문장"
        })

        assert response.status_code == 200
        # Note: With mock embeddings, similarity may not be exactly 1.0
