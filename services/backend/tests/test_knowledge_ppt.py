"""
Test: Knowledge PPT Upload
Phase 18.7.2: Upload 확장

TDD Red Phase: 이 테스트는 처음에 실패해야 합니다.
"""
import pytest


def test_upload_accepts_ppt():
    """Knowledge 업로드가 PPT 파일을 허용하는지 확인"""
    from app.routes.knowledge import SUPPORTED_EXTENSIONS

    # PPT 확장자가 지원 목록에 있어야 함
    assert ".pptx" in SUPPORTED_EXTENSIONS, "SUPPORTED_EXTENSIONS에 .pptx가 없습니다"
    assert ".ppt" in SUPPORTED_EXTENSIONS, "SUPPORTED_EXTENSIONS에 .ppt가 없습니다"
