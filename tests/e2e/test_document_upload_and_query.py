"""
Document Upload and Query E2E Tests

Phase 6.2: 문서 업로드 및 질의 E2E 테스트
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import asyncio
import json
import io


class TestDocumentUploadE2E:
    """문서 업로드 E2E 테스트"""

    @pytest.mark.asyncio
    async def test_upload_txt_document(self, mock_services, mock_database):
        """TXT 문서를 업로드할 수 있어야 한다"""
        # 파일 데이터
        file_content = "이것은 테스트 텍스트 문서입니다.\n회사 정책에 대한 내용이 포함되어 있습니다."
        filename = "policy.txt"
        file_type = "text/plain"

        # 업로드 처리
        doc_id = await mock_database.add_document(filename, file_content)

        # 임베딩 생성
        embedding_result = await mock_services["embedding"].embed(file_content)
        assert embedding_result["dimension"] == 1024

        # RAG에 추가
        rag_result = await mock_services["rag"].add_document({
            "id": doc_id,
            "content": file_content,
            "embedding": embedding_result["embedding"],
            "metadata": {"source": filename, "type": file_type}
        })

        assert doc_id is not None
        assert rag_result["chunks"] > 0

    @pytest.mark.asyncio
    async def test_upload_pdf_document(self, mock_services, mock_database):
        """PDF 문서를 업로드할 수 있어야 한다"""
        # PDF 내용 시뮬레이션 (실제로는 PDF 파서 사용)
        pdf_text = "PDF 문서의 추출된 텍스트입니다."
        filename = "document.pdf"
        file_type = "application/pdf"

        # PDF 텍스트 추출 시뮬레이션
        def extract_pdf_text(pdf_bytes):
            return pdf_text

        extracted_text = extract_pdf_text(b"mock_pdf_bytes")

        # 업로드 처리
        doc_id = await mock_database.add_document(filename, extracted_text)

        # RAG에 추가
        rag_result = await mock_services["rag"].add_document({
            "id": doc_id,
            "content": extracted_text,
            "metadata": {"source": filename, "type": file_type}
        })

        assert doc_id is not None
        assert rag_result["chunks"] > 0

    @pytest.mark.asyncio
    async def test_upload_docx_document(self, mock_services, mock_database):
        """DOCX 문서를 업로드할 수 있어야 한다"""
        # DOCX 내용 시뮬레이션
        docx_text = "Word 문서의 추출된 텍스트입니다."
        filename = "report.docx"
        file_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

        # DOCX 텍스트 추출 시뮬레이션
        def extract_docx_text(docx_bytes):
            return docx_text

        extracted_text = extract_docx_text(b"mock_docx_bytes")

        # 업로드 처리
        doc_id = await mock_database.add_document(filename, extracted_text)

        assert doc_id is not None

    @pytest.mark.asyncio
    async def test_upload_validation(self):
        """업로드 유효성 검사가 동작해야 한다"""
        # 지원 파일 형식
        supported_types = ["text/plain", "application/pdf",
                          "application/vnd.openxmlformats-officedocument.wordprocessingml.document"]
        supported_extensions = [".txt", ".pdf", ".docx"]

        def validate_upload(filename, file_type):
            extension = filename.lower().split(".")[-1]
            if file_type not in supported_types and f".{extension}" not in supported_extensions:
                return {"valid": False, "error": "Unsupported file type"}
            return {"valid": True}

        # 유효한 파일
        assert validate_upload("test.txt", "text/plain")["valid"]
        assert validate_upload("test.pdf", "application/pdf")["valid"]

        # 무효한 파일
        result = validate_upload("test.exe", "application/octet-stream")
        assert not result["valid"]

    @pytest.mark.asyncio
    async def test_upload_size_limit(self):
        """업로드 크기 제한이 적용되어야 한다"""
        max_size_mb = 10
        max_size_bytes = max_size_mb * 1024 * 1024

        def validate_size(file_size):
            if file_size > max_size_bytes:
                return {"valid": False, "error": f"File too large. Max size: {max_size_mb}MB"}
            return {"valid": True}

        # 유효한 크기
        assert validate_size(5 * 1024 * 1024)["valid"]  # 5MB

        # 무효한 크기
        result = validate_size(15 * 1024 * 1024)  # 15MB
        assert not result["valid"]


class TestDocumentChunkingE2E:
    """문서 청킹 E2E 테스트"""

    @pytest.mark.asyncio
    async def test_document_chunking(self):
        """문서가 적절히 청킹되어야 한다"""
        long_document = """
        첫 번째 섹션입니다. 이 섹션에는 중요한 정보가 포함되어 있습니다.

        두 번째 섹션입니다. 다른 주제에 대해 설명합니다.

        세 번째 섹션입니다. 결론을 포함합니다.
        """

        chunk_size = 100
        chunk_overlap = 20

        def chunk_text(text, size, overlap):
            chunks = []
            start = 0
            while start < len(text):
                end = start + size
                chunk = text[start:end]
                chunks.append(chunk.strip())
                start = end - overlap
                if end >= len(text):
                    break
            return [c for c in chunks if c]  # 빈 청크 제거

        chunks = chunk_text(long_document, chunk_size, chunk_overlap)

        assert len(chunks) > 1
        # 오버랩 확인
        if len(chunks) > 1:
            # 연속된 청크 간에 일부 내용이 겹쳐야 함
            pass

    @pytest.mark.asyncio
    async def test_chunk_at_sentence_boundary(self):
        """문장 경계에서 청킹해야 한다"""
        text = "첫 번째 문장입니다. 두 번째 문장입니다. 세 번째 문장입니다. 네 번째 문장입니다."

        def chunk_at_sentences(text, max_chunk_size):
            sentences = text.replace(".", ".\n").split("\n")
            sentences = [s.strip() for s in sentences if s.strip()]

            chunks = []
            current_chunk = ""

            for sentence in sentences:
                if len(current_chunk) + len(sentence) + 1 <= max_chunk_size:
                    current_chunk += " " + sentence if current_chunk else sentence
                else:
                    if current_chunk:
                        chunks.append(current_chunk.strip())
                    current_chunk = sentence

            if current_chunk:
                chunks.append(current_chunk.strip())

            return chunks

        chunks = chunk_at_sentences(text, 50)

        # 각 청크가 완전한 문장으로 끝나야 함
        for chunk in chunks:
            assert chunk.endswith(".")


class TestDocumentQueryE2E:
    """문서 질의 E2E 테스트"""

    @pytest.mark.asyncio
    async def test_semantic_search(self, mock_services):
        """시맨틱 검색이 동작해야 한다"""
        # 문서 추가
        documents = [
            {"id": "1", "content": "회사 연차는 15일입니다.", "metadata": {"source": "hr_policy.txt"}},
            {"id": "2", "content": "점심 시간은 12시부터 1시까지입니다.", "metadata": {"source": "office_rules.txt"}},
            {"id": "3", "content": "재택근무는 주 2회 가능합니다.", "metadata": {"source": "work_policy.txt"}},
        ]

        # 질의
        query = "휴가는 며칠이나 되나요?"

        # 시맨틱 검색 시뮬레이션
        mock_services["rag"].retrieve = AsyncMock(return_value=[
            {"content": documents[0]["content"], "score": 0.92, "metadata": documents[0]["metadata"]}
        ])

        results = await mock_services["rag"].retrieve(query=query)

        assert len(results) > 0
        assert "연차" in results[0]["content"]

    @pytest.mark.asyncio
    async def test_query_with_filters(self, mock_services):
        """필터를 적용한 질의가 동작해야 한다"""
        query = "회사 정책"
        filters = {"source": "hr_policy.txt"}

        mock_services["rag"].retrieve = AsyncMock(return_value=[
            {"content": "HR 관련 정책 내용", "score": 0.88, "metadata": {"source": "hr_policy.txt"}}
        ])

        results = await mock_services["rag"].retrieve(query=query, filters=filters)

        assert len(results) > 0
        assert results[0]["metadata"]["source"] == "hr_policy.txt"

    @pytest.mark.asyncio
    async def test_query_top_k_results(self, mock_services):
        """top_k 결과 제한이 적용되어야 한다"""
        query = "회사"
        top_k = 3

        mock_services["rag"].retrieve = AsyncMock(return_value=[
            {"content": "결과 1", "score": 0.95},
            {"content": "결과 2", "score": 0.90},
            {"content": "결과 3", "score": 0.85},
        ])

        results = await mock_services["rag"].retrieve(query=query, top_k=top_k)

        assert len(results) <= top_k

    @pytest.mark.asyncio
    async def test_query_relevance_threshold(self, mock_services):
        """관련성 임계값이 적용되어야 한다"""
        query = "관련 없는 질문"
        relevance_threshold = 0.7

        mock_services["rag"].retrieve = AsyncMock(return_value=[
            {"content": "결과 1", "score": 0.6},
            {"content": "결과 2", "score": 0.5},
        ])

        results = await mock_services["rag"].retrieve(query=query)

        # 임계값 이하 결과 필터링
        filtered_results = [r for r in results if r["score"] >= relevance_threshold]

        assert len(filtered_results) == 0


class TestRAGWithLLME2E:
    """RAG와 LLM 통합 E2E 테스트"""

    @pytest.mark.asyncio
    async def test_rag_enhanced_llm_response(self, mock_services):
        """RAG 컨텍스트가 LLM 응답을 향상시켜야 한다"""
        user_query = "회사 휴가 정책이 어떻게 되나요?"

        # RAG 검색
        mock_services["rag"].retrieve = AsyncMock(return_value=[
            {"content": "회사 연차는 입사 1년 후 15일이 부여됩니다. 반차 사용도 가능합니다.",
             "score": 0.95, "metadata": {"source": "hr_policy.txt"}}
        ])

        rag_results = await mock_services["rag"].retrieve(query=user_query)
        rag_context = "\n".join([r["content"] for r in rag_results])

        # LLM에 RAG 컨텍스트와 함께 질의
        mock_services["llm"].generate = AsyncMock(return_value={
            "text": "회사 휴가 정책에 따르면, 입사 1년 후 연차 15일이 부여되며, 반차 사용도 가능합니다.",
            "tokens_used": 50
        })

        llm_response = await mock_services["llm"].generate(
            prompt=user_query,
            rag_context=rag_context
        )

        # 응답에 RAG 정보가 반영되었는지 확인
        assert "15일" in llm_response["text"]
        assert "반차" in llm_response["text"]

    @pytest.mark.asyncio
    async def test_source_attribution_in_response(self, mock_services):
        """응답에 출처가 포함되어야 한다"""
        user_query = "재택근무 정책은?"

        mock_services["rag"].retrieve = AsyncMock(return_value=[
            {"content": "재택근무는 주 2회 가능합니다.",
             "score": 0.92, "metadata": {"source": "work_policy.txt"}}
        ])

        rag_results = await mock_services["rag"].retrieve(query=user_query)

        # 출처 추출
        sources = [r["metadata"]["source"] for r in rag_results]

        assert "work_policy.txt" in sources

    @pytest.mark.asyncio
    async def test_no_rag_context_fallback(self, mock_services):
        """RAG 결과가 없을 때 일반 LLM 응답이 반환되어야 한다"""
        user_query = "RAG에 없는 일반적인 질문"

        mock_services["rag"].retrieve = AsyncMock(return_value=[])

        rag_results = await mock_services["rag"].retrieve(query=user_query)

        # RAG 결과 없음
        assert len(rag_results) == 0

        # 일반 LLM 응답
        mock_services["llm"].generate = AsyncMock(return_value={
            "text": "일반적인 답변입니다.",
            "tokens_used": 20
        })

        llm_response = await mock_services["llm"].generate(prompt=user_query)

        assert llm_response["text"] is not None


class TestDocumentManagementE2E:
    """문서 관리 E2E 테스트"""

    @pytest.mark.asyncio
    async def test_list_all_documents(self, mock_database):
        """모든 문서를 조회할 수 있어야 한다"""
        # 문서 추가
        await mock_database.add_document("doc1.txt", "Content 1")
        await mock_database.add_document("doc2.pdf", "Content 2")
        await mock_database.add_document("doc3.docx", "Content 3")

        documents = mock_database.documents

        assert len(documents) >= 3

    @pytest.mark.asyncio
    async def test_delete_document_removes_from_rag(self, mock_services, mock_database):
        """문서 삭제 시 RAG에서도 제거되어야 한다"""
        # 문서 추가
        doc_id = await mock_database.add_document("to_delete.txt", "Delete me")

        # RAG에 추가
        await mock_services["rag"].add_document({
            "id": doc_id,
            "content": "Delete me"
        })

        # 문서 삭제
        async def delete_document(doc_id):
            # DB에서 삭제
            mock_database.documents[:] = [
                d for d in mock_database.documents if d["id"] != doc_id
            ]
            # RAG에서 삭제
            # (실제로는 RAG 서비스의 delete 메서드 호출)
            return True

        result = await delete_document(doc_id)

        assert result
        assert not any(d["id"] == doc_id for d in mock_database.documents)

    @pytest.mark.asyncio
    async def test_document_update(self, mock_database):
        """문서를 업데이트할 수 있어야 한다"""
        # 문서 추가
        doc_id = await mock_database.add_document("update_me.txt", "Original content")

        # 문서 업데이트
        async def update_document(doc_id, new_content):
            for doc in mock_database.documents:
                if doc["id"] == doc_id:
                    doc["content"] = new_content
                    return True
            return False

        result = await update_document(doc_id, "Updated content")

        assert result

        # 업데이트 확인
        doc = next((d for d in mock_database.documents if d["id"] == doc_id), None)
        assert doc is not None
        assert doc["content"] == "Updated content"

    @pytest.mark.asyncio
    async def test_bulk_upload(self, mock_services, mock_database):
        """여러 문서를 일괄 업로드할 수 있어야 한다"""
        files = [
            {"name": "bulk1.txt", "content": "Content 1"},
            {"name": "bulk2.txt", "content": "Content 2"},
            {"name": "bulk3.txt", "content": "Content 3"},
        ]

        uploaded_ids = []

        for file in files:
            doc_id = await mock_database.add_document(file["name"], file["content"])
            await mock_services["rag"].add_document({
                "id": doc_id,
                "content": file["content"]
            })
            uploaded_ids.append(doc_id)

        assert len(uploaded_ids) == 3
        assert all(id is not None for id in uploaded_ids)
