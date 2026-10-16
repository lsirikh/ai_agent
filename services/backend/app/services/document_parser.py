"""
Document Parser Service
Phase 18.7: Knowledge PPT 지원

PPT/PPTX 파일에서 텍스트를 추출하는 파서
"""
from pathlib import Path
from typing import List, Optional


class PPTParser:
    """PPT/PPTX 문서 파서

    PowerPoint 파일에서 텍스트를 추출합니다.
    python-pptx 라이브러리를 사용합니다.
    """

    # 지원하는 파일 확장자
    SUPPORTED_EXTENSIONS = {".ppt", ".pptx"}

    def __init__(self):
        """PPTParser 초기화"""
        self._pptx_available = False
        try:
            from pptx import Presentation
            self._pptx_available = True
        except ImportError:
            pass

    def supports_extension(self, extension: str) -> bool:
        """파일 확장자 지원 여부 확인

        Args:
            extension: 파일 확장자 (예: ".pptx")

        Returns:
            True: 지원됨, False: 지원 안됨
        """
        return extension.lower() in self.SUPPORTED_EXTENSIONS

    def extract_text(self, file_path: str) -> Optional[str]:
        """PPT/PPTX 파일에서 텍스트 추출

        Args:
            file_path: PPT 파일 경로

        Returns:
            추출된 텍스트 또는 None (실패 시)
        """
        if not self._pptx_available:
            return None

        path = Path(file_path)
        if not path.exists():
            return None

        if not self.supports_extension(path.suffix):
            return None

        try:
            from pptx import Presentation

            prs = Presentation(file_path)
            text_parts: List[str] = []

            for slide_num, slide in enumerate(prs.slides, start=1):
                slide_texts: List[str] = []

                for shape in slide.shapes:
                    if hasattr(shape, "text") and shape.text:
                        slide_texts.append(shape.text)

                if slide_texts:
                    text_parts.append(f"[슬라이드 {slide_num}]")
                    text_parts.extend(slide_texts)
                    text_parts.append("")  # 슬라이드 간 빈 줄

            return "\n".join(text_parts).strip()

        except Exception:
            return None

    def extract_text_by_slides(self, file_path: str) -> List[dict]:
        """슬라이드별로 텍스트 추출

        Args:
            file_path: PPT 파일 경로

        Returns:
            슬라이드별 텍스트 리스트 [{"slide": 1, "text": "..."}, ...]
        """
        if not self._pptx_available:
            return []

        path = Path(file_path)
        if not path.exists() or not self.supports_extension(path.suffix):
            return []

        try:
            from pptx import Presentation

            prs = Presentation(file_path)
            slides_data: List[dict] = []

            for slide_num, slide in enumerate(prs.slides, start=1):
                slide_texts: List[str] = []

                for shape in slide.shapes:
                    if hasattr(shape, "text") and shape.text:
                        slide_texts.append(shape.text)

                slides_data.append({
                    "slide": slide_num,
                    "text": "\n".join(slide_texts)
                })

            return slides_data

        except Exception:
            return []
