"""
EdgeVoice 데스크톱 MCP 서버
(이 PC 에서 실행 — 컨테이너가 host.docker.internal 로 붙는다)

    python services/desktop_mcp/server.py            # 127.0.0.1:8932/mcp
    scripts/start-desktop-mcp.ps1 [-InstallStartup]  # 숨겨 띄우기·로그인 시 자동

도구: open_app · write_document (실행 전 확인)
      list_test_files · read_test_file (읽기 전용)
"""

import os
import sys
from pathlib import Path

if __package__ in (None, ""):  # 스크립트로 실행할 때도 services.desktop_mcp 를 찾게
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from mcp.server.mcpserver import MCPServer  # noqa: E402
from mcp.server.transport_security import TransportSecuritySettings  # noqa: E402
from mcp.types import ToolAnnotations  # noqa: E402

from services.desktop_mcp import desktop  # noqa: E402

PORT = int(os.getenv("DESKTOP_MCP_PORT", "8932"))
FOLDER = Path(os.getenv("DESKTOP_MCP_FOLDER", str(desktop.DEFAULT_FOLDER)))
APP_HELP = "notepad(메모장) · word(워드) · excel(엑셀) · powerpoint(파워포인트)"

app = MCPServer("edgevoice-desktop")


@app.tool()
def open_app(app_name: str) -> str:
    """이 PC 에서 프로그램을 실행한다.
    app_name: notepad(메모장) · word(워드) · excel(엑셀) · powerpoint(파워포인트) ·
    calculator(계산기) · paint(그림판)"""
    name = desktop.open_app(app_name, launch=desktop._launch)
    return f"{desktop.KOREAN_NAMES[name]}을(를) 실행했습니다."


@app.tool()
def write_document(app_name: str, filename: str, content: str) -> str:
    """프로그램을 화면에 띄워 내용을 쓰고 Downloads/Tests 폴더에 저장한다.
    app_name: notepad(메모장) · word(워드) · excel(엑셀) · powerpoint(파워포인트).
    filename: 확장자 없는 파일 이름. content: 쓸 내용 —
    엑셀은 줄=행, 쉼표=칸 / 파워포인트는 빈 줄로 슬라이드를 나누고 첫 줄이 제목."""
    path = desktop.write_document(
        app_name, filename, content, folder=FOLDER, launch=desktop._launch
    )
    return f"저장했습니다: {path}"


@app.tool(annotations=ToolAnnotations(readOnlyHint=True))
def list_test_files() -> str:
    """Downloads/Tests 폴더에 저장된 파일 목록(최근 것부터)."""
    return desktop.list_files(FOLDER)


@app.tool(annotations=ToolAnnotations(readOnlyHint=True))
def read_test_file(filename: str) -> str:
    """Downloads/Tests 폴더의 파일 내용을 읽어 저장이 잘 됐는지 확인한다.
    filename: 확장자를 포함한 이름."""
    path = desktop.find_file(FOLDER, filename)
    if path is None:
        return f"{filename} 파일이 없습니다. 목록: {desktop.list_files(FOLDER)}"
    return desktop.read_document(path)


if __name__ == "__main__":
    import asyncio

    hosts = [f"{h}:{PORT}" for h in ("127.0.0.1", "localhost", "host.docker.internal")]
    asyncio.run(
        app.run_streamable_http_async(
            host="127.0.0.1",
            port=PORT,
            transport_security=TransportSecuritySettings(allowed_hosts=hosts),
        )
    )
