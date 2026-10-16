"""
Test: PPT Parser
Phase 18.7: Knowledge PPT 지원

TDD Red Phase: 이 테스트는 처음에 실패해야 합니다.
"""
import pytest


def test_ppt_parser_class_exists():
    """PPTParser 클래스가 존재하는지 확인"""
    from app.services.document_parser import PPTParser
    assert PPTParser is not None


def test_ppt_parser_extracts_text():
    """PPT 파서가 텍스트를 추출하는지 확인"""
    from app.services.document_parser import PPTParser

    # PPTParser에 extract_text 메서드가 있는지 확인
    parser = PPTParser()
    assert hasattr(parser, "extract_text"), "PPTParser에 extract_text 메서드가 없습니다"


def test_ppt_parser_handles_pptx():
    """PPT 파서가 .pptx 파일을 처리하는지 확인"""
    from app.services.document_parser import PPTParser

    parser = PPTParser()

    # 지원 확장자 확인
    assert parser.supports_extension(".pptx") is True
    assert parser.supports_extension(".ppt") is True
    assert parser.supports_extension(".pdf") is False
    assert parser.supports_extension(".docx") is False
