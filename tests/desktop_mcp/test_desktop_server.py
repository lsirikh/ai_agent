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
        # 컴퓨터 조작 (2026-10-18: 그림판에 그리기를 못 했다)
        "draw_picture",
        "mouse_click",
        "mouse_drag",
        "type_text",
        "press_keys",
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


def test_draw_picture_tool_draws_on_paint(monkeypatch) -> None:
    from services.desktop_mcp import computer, server

    drags = []

    class Screen:
        def paint_canvas(self):
            return (0, 0, 1000, 1000)

        def drag(self, points):
            drags.append(points)

    monkeypatch.setattr(computer, "WindowsScreen", Screen)

    message = server.draw_picture(
        [{"type": "circle", "x": 500, "y": 400, "r": 200}, {"type": "line",
          "x1": 400, "y1": 700, "x2": 600, "y2": 700}]
    )

    assert len(drags) == 2 and "2" in message


def test_keyboard_tools_report_bad_keys_without_crashing() -> None:
    from services.desktop_mcp import server

    assert "모르는 키" in server.press_keys("ctrl+없는키")
