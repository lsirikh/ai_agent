"""
Backend - RAG Service Client

HTTP 기반 RAG 서비스 클라이언트 (Docker 환경용)

Phase 27.1: Knowledge Documents API 모듈 임포트 에러 수정
- 직접 모듈 임포트 대신 HTTP API 호출 방식으로 변경
- Docker 컨테이너 간 통신은 HTTP를 통해 수행
"""
import os
from typing import Any, Dict, List, Optional

import httpx


class RAGServiceClient:
    """
    RAG HTTP 클라이언트

    Docker 환경에서 직접 HTTP 호출로 RAG 서비스와 통신
    Knowledge API에서 사용
    """

    def __init__(self, base_url: Optional[str] = None):
        """
        RAGServiceClient 초기화

        Args:
            base_url: RAG 서비스 URL
        """
        self.base_url = base_url or os.getenv("RAG_SERVICE_URL", "http://rag:8006")
        self.timeout = httpx.Timeout(30.0)

    async def list_documents(self) -> List[Dict[str, Any]]:
        """문서 목록 조회"""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.get(f"{self.base_url}/documents")
                response.raise_for_status()
                data = response.json()
                # RAG 서비스는 {"documents": [...]} 형태로 반환
                if isinstance(data, dict):
                    return data.get("documents", [])
                return data if isinstance(data, list) else []
            except Exception:
                return []

    async def add_document(
        self,
        content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """문서 추가"""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/documents",
                json={"content": content, "metadata": metadata or {}}
            )
            response.raise_for_status()
            return response.json()

    async def delete_document(self, doc_id: str) -> Dict[str, Any]:
        """문서 삭제"""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.delete(f"{self.base_url}/documents/{doc_id}")
            response.raise_for_status()
            return response.json()

    async def search(
        self,
        query: str,
        top_k: int = 3,
        filter_metadata: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """문서 검색"""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(
                    f"{self.base_url}/retrieve",
                    json={
                        "query": query,
                        "top_k": top_k,
                        "filter": filter_metadata
                    }
                )
                response.raise_for_status()
                data = response.json()
                return data.get("results", [])
            except Exception:
                return []

    async def format_context(
        self,
        results: List[Dict[str, Any]]
    ) -> str:
        """검색 결과를 컨텍스트 형식으로 포맷"""
        # 로컬에서 포맷 처리 (RAG 서비스에 엔드포인트가 없을 수 있음)
        if not results:
            return ""

        context_parts = []
        for i, result in enumerate(results, 1):
            content = result.get("content", "")
            doc_id = result.get("doc_id", "unknown")
            score = result.get("score", 0)
            context_parts.append(f"[{i}] (score: {score:.2f}, doc: {doc_id})\n{content}")

        return "\n\n".join(context_parts)

    async def retrieve(
        self,
        query: str,
        top_k: int = 3,
        filter_metadata: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """검색 (chat_service 호환용 별칭)"""
        return await self.search(query, top_k=top_k, filter_metadata=filter_metadata)


# 싱글톤 클라이언트 인스턴스
_rag_client: Optional[RAGServiceClient] = None


def get_rag_client() -> RAGServiceClient:
    """RAG 클라이언트 인스턴스 반환"""
    global _rag_client
    if _rag_client is None:
        _rag_client = RAGServiceClient()
    return _rag_client


# 하위 호환성을 위한 별칭
SimpleRAGClient = RAGServiceClient
