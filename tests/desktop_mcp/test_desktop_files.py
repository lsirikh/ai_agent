"""
데스크톱 MCP: 로컬 LLM(EdgeVoice)이 메모장·워드·엑셀·파워포인트를 실행하고
Downloads/Tests 에 저장한다 (사용자 요청 2026-10-17).

- 정해진 프로그램만 (한국어 이름도 받는다)
- 파일은 Downloads/Tests 안에만, 같은 이름이 있으면 덮어쓰지 않는다
- 저장한 파일을 다시 읽어 확인할 수 있다
"""

import pytest

from services.desktop_mcp import desktop


@pytest.mark.parametrize(
    "name, expected",
    [
        ("메모장", "notepad"),
        ("워드", "word"),
        ("Excel", "excel"),
        ("엑셀", "excel"),
        ("피피티", "powerpoint"),
        ("파워포인트", "powerpoint"),
        ("계산기", "calculator"),
    ],
)
def test_should_accept_korean_and_english_app_names(name, expected) -> None:
    assert desktop.normalize_app(name) == expected


def test_should_reject_programs_outside_the_list() -> None:
    with pytest.raises(ValueError):
        desktop.normalize_app("cmd")


def test_should_keep_files_inside_tests_folder(tmp_path) -> None:
    path = desktop.target_path(tmp_path, r"..\..\Windows\evil", "word")

    assert path.parent == tmp_path
    assert path.suffix == ".docx"
    assert ".." not in path.name and "\\" not in path.name


def test_should_not_overwrite_existing_file(tmp_path) -> None:
    (tmp_path / "메모.txt").write_text("old", encoding="utf-8")

    path = desktop.target_path(tmp_path, "메모", "notepad")

    assert path.name == "메모 (2).txt"


def test_should_split_spreadsheet_rows(tmp_path) -> None:
    rows = desktop.table_rows("품목, 수량\n사과, 3\n배\t5")

    assert rows == [["품목", "수량"], ["사과", 3], ["배", 5]]


def test_notepad_document_is_saved_and_read_back(tmp_path) -> None:
    opened = []
    saved = desktop.write_document(
        "메모장", "장보기", "우유\n계란", folder=tmp_path, launch=opened.append
    )

    assert saved.name == "장보기.txt"
    assert desktop.read_document(saved) == "우유\n계란"
    assert opened == [saved]


def test_should_list_saved_files(tmp_path) -> None:
    (tmp_path / "a.txt").write_text("x", encoding="utf-8")

    listing = desktop.list_files(tmp_path)

    assert "a.txt" in listing


SLIDES = "소개\n로컬 음성 비서\n\n기능\n프로그램 실행"


@pytest.mark.parametrize(
    "app, content, expected",
    [
        ("워드", "회의록\n안건: 데스크톱 시험", "회의록\n안건: 데스크톱 시험"),
        ("엑셀", "항목,금액\n식비,30000", "항목, 금액\n식비, 30000"),
        ("파워포인트", SLIDES, SLIDES),
    ],
)
def test_office_documents_are_saved_without_office_and_opened(
    tmp_path, app, content, expected
) -> None:
    # 실측: 이 PC 의 Office 는 '인증 마법사' 창이 떠 COM 자동화가 막혔다
    # (엑셀 저장 안 됨 · 파워포인트 멈춤).
    # 파일은 라이브러리로 만들고 프로그램으로 연다.
    opened = []

    saved = desktop.write_document(
        app, "시험", content, folder=tmp_path, launch=opened.append
    )

    assert desktop.read_document(saved) == expected
    assert opened == [saved]


def test_numbered_headings_become_separate_slides() -> None:
    # 실측: '2장 만들어 줘' 에 로컬 LLM 은 빈 줄 대신 '1. … 2. …' 로 나눠 보내
    # 슬라이드가 1장이 됐다
    content = (
        "1. EdgeVoice 소개\n   - 한국어 AI 어시스턴트\n"
        "2. 주요 기능\n   - 웹 검색\n   - 파일 저장"
    )

    assert desktop.slide_blocks(content) == [
        ["EdgeVoice 소개", "- 한국어 AI 어시스턴트"],
        ["주요 기능", "- 웹 검색", "- 파일 저장"],
    ]


def test_blank_lines_still_split_slides() -> None:
    assert desktop.slide_blocks("제목\n본문\n\n둘째\n내용") == [
        ["제목", "본문"],
        ["둘째", "내용"],
    ]
