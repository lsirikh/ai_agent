"""
Backend API - Chat RAG Integration

Phase 9.3: 채팅과 RAG 통합 클래스
"""
from typing import Any, Optional


class ChatRAGIntegration:
    """
    채팅과 RAG 통합 클래스

    RAG 서비스를 통해 관련 문서를 검색하고
    채팅 컨텍스트로 포맷팅하는 역할
    """

    def __init__(
        self,
        rag_service: Optional[Any] = None,
        embedding_service: Optional[Any] = None
    ):
        """
        ChatRAGIntegration 초기화

        Args:
            rag_service: RAG 서비스
            embedding_service: 임베딩 서비스
        """
        self.rag_service = rag_service
        self.embedding_service = embedding_service

    async def get_context_for_query(
        self,
        query: str,
        top_k: int = 3,
        score_threshold: float = 0.5
    ) -> tuple[Optional[str], list]:
        """
        쿼리에 대한 RAG 컨텍스트 검색

        Args:
            query: 검색 쿼리
            top_k: 반환할 최대 문서 수
            score_threshold: 최소 점수 임계값

        Returns:
            (formatted_context, sources) 튜플
        """
        if not self.rag_service:
            return None, []

        try:
            # RAG 검색 수행
            results = self.rag_service.retrieve(query, top_k=top_k)

            if not results:
                return None, []

            # 점수 필터링
            filtered_results = [
                r for r in results
                if r.get("score", 0) >= score_threshold
            ]

            if not filtered_results:
                return None, []

            # 컨텍스트 포맷팅
            context_parts = []
            sources = []

            for i, result in enumerate(filtered_results, 1):
                context_parts.append(f"[문서 {i}]\n{result['content']}")
                sources.append({
                    "doc_id": result.get("doc_id", ""),
                    "filename": result.get("metadata", {}).get("filename", "unknown"),
                    "score": result.get("score", 0)
                })

            formatted_context = "\n\n---\n\n".join(context_parts)

            return formatted_context, sources

        except Exception:
            return None, []

    def format_context_for_prompt(
        self,
        context: str,
        sources: list
    ) -> str:
        """
        컨텍스트를 프롬프트용으로 포맷팅

        Args:
            context: RAG 컨텍스트
            sources: 출처 목록

        Returns:
            프롬프트에 삽입할 포맷된 컨텍스트
        """
        if not context:
            return ""

        source_info = ""
        if sources:
            source_names = [s.get("filename", "unknown") for s in sources]
            source_info = f"\n\n출처: {', '.join(source_names)}"

        return f"""관련 문서에서 찾은 정보:

{context}
{source_info}"""
