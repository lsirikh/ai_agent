"""
EdgeVoice 데스크톱 MCP 서버
(이 PC 에서 실행 — 컨테이너가 host.docker.internal 로 붙는다)

    python services/desktop_mcp/server.py            # 127.0.0.1:8932/mcp
    scripts/start-desktop-mcp.ps1 [-InstallStartup]  # 숨겨 띄우기·로그인 시 자동

도구: open_app · write_document (실행 전 확인)
      list_test_files · read_test_file (읽기 전용)
      draw_picture · mouse_click · mouse_drag · type_text · press_keys (컴퓨터 조작)
"""

import os
import sys
from pathlib import Path

if __package__ in (None, ""):  # 스크립트로 실행할 때도 services.desktop_mcp 를 찾게
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from mcp.server.mcpserver import MCPServer  # noqa: E402
from mcp.server.transport_security import TransportSecuritySettings  # noqa: E402
from mcp.types import ToolAnnotations  # noqa: E402

from services.desktop_mcp import computer, desktop  # noqa: E402

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


@app.tool()
def draw_picture(shapes: list[dict]) -> str:
    """그림판을 열어(없으면 실행) 흰 캔버스에 모양들을 마우스로 그린다.
    좌표는 캔버스를 가로·세로 0~1000 으로 본 값(왼쪽 위가 0,0).
    shapes 의 각 항목(type 별 키):
      circle {x,y,r} · ellipse {x,y,rx,ry}
      arc {x,y,r,start,end} (각도: 0=오른쪽, 90=아래)
      line {x1,y1,x2,y2} · rect {x,y,w,h} · polyline {points:[[x,y],...]}
    예) 웃는 얼굴: [{"type":"circle","x":500,"y":500,"r":300},
      {"type":"circle","x":400,"y":420,"r":30},{"type":"circle","x":600,"y":420,"r":30},
      {"type":"arc","x":500,"y":520,"r":150,"start":20,"end":160}]
    강아지처럼 복잡한 것은 머리·귀·눈·코·입·몸·다리·꼬리를 각각 모양으로 나눠
    12개 이상으로 그리고, 캔버스(0~1000)를 넓게 쓴다. 부분끼리 서로 닿게 놓는다
    (예: 몸통 타원 위에 머리 원, 머리 위 양옆에 귀 타원, 몸통 아래에 다리 선 4개)."""
    try:
        return computer.draw_picture(shapes, screen=computer.WindowsScreen())
    except (ValueError, RuntimeError) as e:
        return f"그리지 못했습니다: {e}"


@app.tool()
def mouse_click(x: int, y: int, button: str = "left", double: bool = False) -> str:
    """화면의 (x, y) 픽셀을 마우스로 누른다.
    button: left · right, double: 두 번 누르기."""
    computer.WindowsScreen().click(x, y, button=button, double=double)
    return f"({x}, {y}) 를 눌렀습니다."


@app.tool()
def mouse_drag(points: list[list[int]]) -> str:
    """왼쪽 버튼을 누른 채 화면 픽셀 점들 [[x,y],...] 을 따라 끈다."""
    pairs = [(int(p[0]), int(p[1])) for p in points if len(p) >= 2]
    if len(pairs) < 2:
        return "점이 두 개 이상 필요합니다."
    computer.WindowsScreen().drag(pairs)
    return f"점 {len(pairs)}개를 따라 끌었습니다."


@app.tool()
def type_text(text: str) -> str:
    """지금 앞에 있는 창에 글자를 입력한다(한글 포함)."""
    computer.WindowsScreen().type_text(text)
    return f"{len(text)}자를 입력했습니다."


@app.tool()
def press_keys(keys: str) -> str:
    """키를 누른다. 예: 'enter' · 'ctrl+s' · 'alt+F4' · 'ctrl+shift+n'."""
    try:
        codes = computer.parse_keys(keys)
    except ValueError as e:
        return f"누르지 못했습니다: {e}"
    computer.WindowsScreen().press(codes)
    return f"{keys} 를 눌렀습니다."


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
