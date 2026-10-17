"""데스크톱 MCP 서버: 도구 목록·읽기 전용 표시·저장 폴더.

읽기 전용 표시로 EdgeVoice 가 실행 전 확인 여부를 정한다.
"""

import pytest


@pytest.mark.asyncio
async def test_should_mark_only_listing_and_reading_as_read_only() -> None:
    from services.desktop_mcp import server

    tools = {t.name: t for t in await server.app.list_tools()}

    assert set(tools) == {
        "open_app",
        "write_document",
        "list_test_files",
        "read_test_file",
    }
    assert tools["list_test_files"].annotations.read_only_hint is True
    assert tools["read_test_file"].annotations.read_only_hint is True
    assert not (
        tools["write_document"].annotations
        and tools["write_document"].annotations.read_only_hint
    )
    assert not (
        tools["open_app"].annotations and tools["open_app"].annotations.read_only_hint
    )


@pytest.mark.asyncio
async def test_should_save_into_configured_folder_and_read_back(
    tmp_path, monkeypatch
) -> None:
    from services.desktop_mcp import desktop, server

    monkeypatch.setattr(server, "FOLDER", tmp_path)
    monkeypatch.setattr(desktop, "_launch", lambda path: None)

    saved = server.write_document("메모장", "할일", "청소\n빨래")
    listing = server.list_test_files()
    text = server.read_test_file("할일.txt")

    assert "할일.txt" in saved and str(tmp_path) in saved
    assert "할일.txt" in listing
    assert text == "청소\n빨래"


def test_should_report_unknown_program_without_crashing() -> None:
    from services.desktop_mcp import server

    with pytest.raises(ValueError):
        server.open_app("cmd")
