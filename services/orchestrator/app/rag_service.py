"""
RAG Service

Phase 4.2: Retrieval-Augmented Generation 서비스
"""
import asyncio
import re
import uuid
from typing import Any, Dict, List, Optional

import numpy as np

from services.embedding.app.embedder import get_embedder


class RAGService:
    """
    RAG (Retrieval-Augmented Generation) 서비스

    문서를 청크로 분리하고, 임베딩하여 저장하며,
    쿼리에 대해 관련 컨텍스트를 검색합니다.

    Attributes:
        chunk_size: 청크 크기 (문자 수)
        chunk_overlap: 청크 오버랩 (문자 수)
        top_k: 검색 결과 개수
    """

    def __init__(
        self,
        chunk_size: int = 256,
        chunk_overlap: int = 32,
        top_k: int = 3
    ):
        """
        RAGService 초기화

        Args:
            chunk_size: 청크 크기 (문자 수)
            chunk_overlap: 청크 간 오버랩 (문자 수)
            top_k: 검색 시 반환할 결과 개수
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.top_k = top_k

        # 임베더 초기화
        self.embedder = get_embedder()
        self._embedding_dim = 1024  # BGE-M3 default

        # 인메모리 문서 저장소
        self._documents: Dict[str, Dict[str, Any]] = {}
        self._chunks: List[Dict[str, Any]] = []
        self._embeddings: Optional[np.ndarray] = None

    @property
    def document_count(self) -> int:
        """저장된 문서 수"""
        return len(self._documents)

    @property
    def chunk_count(self) -> int:
        """저장된 청크 수"""
        return len(self._chunks)

    def chunk_text(self, text: str) -> List[str]:
        """
        텍스트를 청크로 분리

        문장 경계를 고려하여 청크를 분리합니다.

        Args:
            text: 분리할 텍스트

        Returns:
            청크 리스트
        """
        if not text or not text.strip():
            return []

        text = text.strip()

        # 짧은 텍스트는 그대로 반환
        if len(text) <= self.chunk_size:
            return [text]

        chunks = []
        sentences = self._split_into_sentences(text)

        current_chunk = ""

        for sentence in sentences:
            # 현재 청크 + 새 문장이 청크 크기를 초과하는지 확인
            potential_chunk = current_chunk + sentence if current_chunk else sentence

            if len(potential_chunk) <= self.chunk_size:
                current_chunk = potential_chunk
            else:
                # 현재 청크 저장
                if current_chunk:
                    chunks.append(current_chunk.strip())

                # 오버랩 처리
                if self.chunk_overlap > 0 and current_chunk:
                    # 오버랩 부분 추출
                    overlap_text = current_chunk[-self.chunk_overlap:]
                    current_chunk = overlap_text + sentence
                else:
                    current_chunk = sentence

                # 긴 문장 처리 (문장이 청크 크기보다 큰 경우)
                while len(current_chunk) > self.chunk_size:
                    chunks.append(current_chunk[:self.chunk_size].strip())
                    current_chunk = current_chunk[self.chunk_size - self.chunk_overlap:]

        # 마지막 청크 추가
        if current_chunk.strip():
            chunks.append(current_chunk.strip())

        return chunks

    def _split_into_sentences(self, text: str) -> List[str]:
        """
        텍스트를 문장으로 분리

        Args:
            text: 분리할 텍스트

        Returns:
            문장 리스트
        """
        # 문장 끝 패턴 (한국어/영어)
        pattern = r'(?<=[.!?。？！])\s+'
        sentences = re.split(pattern, text)
        return [s.strip() + " " for s in sentences if s.strip()]

    def add_document(
        self,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        doc_id: Optional[str] = None
    ) -> str:
        """
        문서 추가

        Args:
            content: 문서 내용
            metadata: 메타데이터
            doc_id: 문서 ID (없으면 자동 생성)

        Returns:
            문서 ID
        """
        if doc_id is None:
            doc_id = str(uuid.uuid4())

        # 문서 청킹
        chunks = self.chunk_text(content)

        # 청크 임베딩
        if chunks:
            embeddings = self.embedder.embed_batch(chunks)

            # 청크 저장
            chunk_start_idx = len(self._chunks)
            for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
                self._chunks.append({
                    "doc_id": doc_id,
                    "chunk_idx": i,
                    "content": chunk,
                    "metadata": metadata or {}
                })

            # 임베딩 저장
            if self._embeddings is None:
                self._embeddings = embeddings
            else:
                self._embeddings = np.vstack([self._embeddings, embeddings])

        # 문서 메타데이터 저장
        self._documents[doc_id] = {
            "content": content,
            "metadata": metadata or {},
            "chunk_count": len(chunks)
        }

        return doc_id

    async def add_document_async(
        self,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        doc_id: Optional[str] = None
    ) -> str:
        """
        비동기 문서 추가

        Args:
            content: 문서 내용
            metadata: 메타데이터
            doc_id: 문서 ID

        Returns:
            문서 ID
        """
        if doc_id is None:
            doc_id = str(uuid.uuid4())

        chunks = self.chunk_text(content)

        if chunks:
            embeddings = await self.embedder.embed_batch_async(chunks)

            chunk_start_idx = len(self._chunks)
            for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
                self._chunks.append({
                    "doc_id": doc_id,
                    "chunk_idx": i,
                    "content": chunk,
                    "metadata": metadata or {}
                })

            if self._embeddings is None:
                self._embeddings = embeddings
            else:
                self._embeddings = np.vstack([self._embeddings, embeddings])

        self._documents[doc_id] = {
            "content": content,
            "metadata": metadata or {},
            "chunk_count": len(chunks)
        }

        return doc_id

    def delete_document(self, doc_id: str) -> bool:
        """
        문서 삭제

        Args:
            doc_id: 삭제할 문서 ID

        Returns:
            삭제 성공 여부
        """
        if doc_id not in self._documents:
            return False

        # 해당 문서의 청크 인덱스 찾기
        indices_to_remove = [
            i for i, chunk in enumerate(self._chunks)
            if chunk["doc_id"] == doc_id
        ]

        # 청크 및 임베딩 삭제
        if indices_to_remove:
            # 역순으로 삭제하여 인덱스 문제 방지
            for idx in sorted(indices_to_remove, reverse=True):
                self._chunks.pop(idx)

            # 임베딩 재구성
            if self._embeddings is not None:
                mask = np.ones(len(self._embeddings), dtype=bool)
                mask[indices_to_remove] = False
                self._embeddings = self._embeddings[mask]

                if len(self._embeddings) == 0:
                    self._embeddings = None

        # 문서 메타데이터 삭제
        del self._documents[doc_id]

        return True

    def list_documents(self) -> List[Dict[str, Any]]:
        """
        문서 목록 조회

        Returns:
            문서 정보 리스트
        """
        return [
            {
                "doc_id": doc_id,
                "metadata": info["metadata"],
                "chunk_count": info["chunk_count"]
            }
            for doc_id, info in self._documents.items()
        ]

    def retrieve(
        self,
        query: str,
        top_k: Optional[int] = None,
        filter_metadata: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        관련 컨텍스트 검색

        Args:
            query: 검색 쿼리
            top_k: 반환할 결과 개수 (기본값: self.top_k)
            filter_metadata: 메타데이터 필터

        Returns:
            검색 결과 리스트 (content, score, metadata 포함)
        """
        if not self._chunks or self._embeddings is None:
            return []

        k = top_k or self.top_k

        # 쿼리 임베딩
        query_embedding = self.embedder.embed(query)

        # 필터 적용
        if filter_metadata:
            filtered_indices = [
                i for i, chunk in enumerate(self._chunks)
                if all(
                    chunk["metadata"].get(key) == value
                    for key, value in filter_metadata.items()
                )
            ]

            if not filtered_indices:
                return []

            filtered_embeddings = self._embeddings[filtered_indices]
            filtered_chunks = [self._chunks[i] for i in filtered_indices]
        else:
            filtered_embeddings = self._embeddings
            filtered_chunks = self._chunks

        # 유사도 계산
        similarities = self.embedder.batch_cosine_similarity(
            query_embedding,
            filtered_embeddings
        )

        # top_k 결과 선택 (필터된 결과 수보다 많으면 제한)
        actual_k = min(k, len(filtered_chunks))
        top_indices = np.argsort(similarities)[::-1][:actual_k]

        results = []
        for idx in top_indices:
            if idx < len(filtered_chunks):
                chunk = filtered_chunks[idx]
                results.append({
                    "content": chunk["content"],
                    "score": float(similarities[idx]),
                    "metadata": chunk["metadata"],
                    "doc_id": chunk["doc_id"]
                })

        return results

    async def retrieve_async(
        self,
        query: str,
        top_k: Optional[int] = None,
        filter_metadata: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        비동기 검색

        Args:
            query: 검색 쿼리
            top_k: 반환할 결과 개수
            filter_metadata: 메타데이터 필터

        Returns:
            검색 결과 리스트
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.retrieve(query, top_k, filter_metadata)
        )

    def format_context(
        self,
        results: List[Dict[str, Any]],
        separator: str = "\n\n"
    ) -> str:
        """
        검색 결과를 LLM 컨텍스트로 포맷팅

        Args:
            results: 검색 결과 리스트
            separator: 구분자

        Returns:
            포맷팅된 컨텍스트 문자열
        """
        if not results:
            return ""

        contents = [result["content"] for result in results]
        return separator.join(contents)

    def clear(self) -> None:
        """모든 데이터 초기화"""
        self._documents.clear()
        self._chunks.clear()
        self._embeddings = None
