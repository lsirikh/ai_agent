"""
Backend API Knowledge Base Router

Phase 5.3: Knowledge Base (RAG) 관리 API
Phase 27.1: 모듈 임포트 에러 수정 - HTTP API 호출 방식으로 변경
"""
import io
import uuid
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from ..services.rag_client import get_rag_client, RAGServiceClient

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


# ===== Pydantic Models =====

class DocumentInfo(BaseModel):
    """문서 정보"""
    doc_id: str
    filename: str
    chunk_count: int = 0
    uploaded_at: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class DocumentListResponse(BaseModel):
    """문서 목록 응답"""
    documents: List[DocumentInfo]
    total: int = 0


class UploadResponse(BaseModel):
    """업로드 응답"""
    doc_id: str
    filename: str
    chunk_count: int = 0
    message: str = "Document uploaded successfully"


class DeleteResponse(BaseModel):
    """삭제 응답"""
    doc_id: str
    deleted: bool


class SearchRequest(BaseModel):
    """검색 요청"""
    query: str
    top_k: int = Field(default=3, ge=1, le=10)
    filter: Optional[Dict[str, Any]] = None
    format_context: bool = False


class SearchResult(BaseModel):
    """검색 결과 항목"""
    content: str
    score: float
    doc_id: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SearchResponse(BaseModel):
    """검색 응답"""
    results: List[SearchResult]
    formatted_context: Optional[str] = None


# ===== Document Extraction =====

SUPPORTED_EXTENSIONS = {".txt", ".pdf", ".docx", ".md", ".ppt", ".pptx"}


def extract_text_from_pdf(content: bytes) -> str:
    """PDF에서 텍스트 추출"""
    try:
        import PyPDF2
        reader = PyPDF2.PdfReader(io.BytesIO(content))
        text = ""
        for page in reader.pages:
            text += page.extract_text() + "\n"
        return text.strip()
    except Exception:
        # PyPDF2가 없거나 파싱 실패 시
        return "PDF 내용을 추출할 수 없습니다."


def extract_text_from_docx(content: bytes) -> str:
    """DOCX에서 텍스트 추출"""
    try:
        import docx
        doc = docx.Document(io.BytesIO(content))
        text = "\n".join([para.text for para in doc.paragraphs])
        return text.strip()
    except Exception:
        # python-docx가 없거나 파싱 실패 시
        return "DOCX 내용을 추출할 수 없습니다."


def extract_text_from_ppt(content: bytes) -> str:
    """PPT/PPTX에서 텍스트 추출"""
    try:
        from pptx import Presentation
        prs = Presentation(io.BytesIO(content))
        text_parts = []
        for slide_num, slide in enumerate(prs.slides, start=1):
            slide_texts = []
            for shape in slide.shapes:
                if hasattr(shape, "text") and shape.text:
                    slide_texts.append(shape.text)
            if slide_texts:
                text_parts.append(f"[슬라이드 {slide_num}]")
                text_parts.extend(slide_texts)
                text_parts.append("")
        return "\n".join(text_parts).strip()
    except Exception:
        # python-pptx가 없거나 파싱 실패 시
        return "PPT 내용을 추출할 수 없습니다."


def get_file_extension(filename: str) -> str:
    """파일 확장자 추출"""
    import os
    return os.path.splitext(filename)[1].lower()


# ===== API Endpoints =====

@router.post("/upload", response_model=UploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    category: Optional[str] = Form(None)
):
    """
    문서 업로드

    Args:
        file: 업로드할 파일 (txt, pdf, docx 지원)
        title: 문서 제목 (선택)
        category: 문서 카테고리 (선택)

    Returns:
        업로드 결과
    """
    extension = get_file_extension(file.filename)

    if extension not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"지원하지 않는 파일 형식입니다. 지원 형식: {', '.join(SUPPORTED_EXTENSIONS)}"
        )

    content = await file.read()

    # 파일 형식에 따라 텍스트 추출
    if extension == ".txt" or extension == ".md":
        text = content.decode("utf-8")
    elif extension == ".pdf":
        text = extract_text_from_pdf(content)
    elif extension == ".docx":
        text = extract_text_from_docx(content)
    elif extension in (".ppt", ".pptx"):
        text = extract_text_from_ppt(content)
    else:
        text = content.decode("utf-8", errors="ignore")

    # 메타데이터 구성
    metadata = {
        "filename": file.filename,
        "extension": extension
    }
    if title:
        metadata["title"] = title
    if category:
        metadata["category"] = category

    # RAG 서비스에 문서 추가 (HTTP API 호출)
    rag_client = get_rag_client()
    try:
        result = await rag_client.add_document(content=text, metadata=metadata)
    except httpx.HTTPStatusError as e:
        # RAG 의 실패 사유(빈 문서·임베딩 오류 등)를 그대로 화면에 전한다
        try:
            detail = e.response.json().get("detail", e.response.text)
        except ValueError:
            detail = e.response.text
        raise HTTPException(status_code=e.response.status_code, detail=detail)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=503, detail=f"RAG 서비스 연결 실패: {e}")
    doc_id = result.get("doc_id", str(uuid.uuid4()))

    return UploadResponse(
        doc_id=doc_id,
        filename=file.filename,
        chunk_count=result.get("chunk_count", 0)
    )


@router.get("/documents", response_model=DocumentListResponse)
async def list_documents(
    limit: int = 100,
    offset: int = 0
):
    """
    문서 목록 조회

    Args:
        limit: 최대 반환 수
        offset: 시작 위치

    Returns:
        문서 목록
    """
    rag_client = get_rag_client()
    all_docs = await rag_client.list_documents()

    # 페이지네이션 적용
    paginated = all_docs[offset:offset + limit]

    documents = [
        DocumentInfo(
            doc_id=doc.get("doc_id", ""),
            filename=doc.get("metadata", {}).get("filename", "unknown"),
            chunk_count=doc.get("chunk_count") or 0,
            uploaded_at=doc.get("uploaded_at"),
            metadata=doc.get("metadata", {})
        )
        for doc in paginated
    ]

    return DocumentListResponse(
        documents=documents,
        total=len(all_docs)
    )


@router.delete("/documents/{doc_id}", response_model=DeleteResponse)
async def delete_document(doc_id: str):
    """
    문서 삭제

    Args:
        doc_id: 삭제할 문서 ID

    Returns:
        삭제 결과
    """
    rag_client = get_rag_client()

    try:
        await rag_client.delete_document(doc_id)
        return DeleteResponse(doc_id=doc_id, deleted=True)
    except Exception:
        raise HTTPException(status_code=404, detail=f"문서를 찾을 수 없습니다: {doc_id}")


@router.post("/search", response_model=SearchResponse)
async def search_knowledge(request: SearchRequest):
    """
    지식 베이스 검색

    Args:
        request: 검색 요청

    Returns:
        검색 결과
    """
    if not request.query or not request.query.strip():
        raise HTTPException(status_code=400, detail="검색어를 입력해주세요")

    rag_client = get_rag_client()

    # RAG 검색 수행 (HTTP API 호출)
    results = await rag_client.search(
        query=request.query,
        top_k=request.top_k,
        filter_metadata=request.filter
    )

    search_results = [
        SearchResult(
            content=r.get("content", ""),
            score=r.get("score", 0.0),
            doc_id=r.get("doc_id", ""),
            metadata=r.get("metadata", {})
        )
        for r in results
    ]

    response = SearchResponse(results=search_results)

    # 포맷된 컨텍스트 요청 시
    if request.format_context and results:
        response.formatted_context = await rag_client.format_context(results)

    return response
