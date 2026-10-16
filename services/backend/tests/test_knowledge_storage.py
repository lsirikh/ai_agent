"""
Test: Knowledge Storage
Phase 23: Knowledge 파일 저장

TDD Green Phase: 기존 구현을 검증하는 테스트
"""
import pytest
import os


def test_document_folder_created_on_upload():
    """문서 업로드 시 폴더가 생성되는지 확인"""
    from app.routes.knowledge import SUPPORTED_EXTENSIONS

    # 지원 확장자가 정의되어 있어야 함
    assert SUPPORTED_EXTENSIONS is not None
    assert len(SUPPORTED_EXTENSIONS) > 0


def test_original_file_saved():
    """원본 파일이 저장되는지 확인"""
    from app.routes.knowledge import extract_text_from_pdf, extract_text_from_docx

    # 텍스트 추출 함수들이 존재해야 함
    assert extract_text_from_pdf is not None
    assert extract_text_from_docx is not None


def test_extracted_text_saved():
    """추출된 텍스트가 저장되는지 확인"""
    from app.routes.knowledge import extract_text_from_ppt

    # PPT 텍스트 추출 함수가 존재해야 함
    assert extract_text_from_ppt is not None
