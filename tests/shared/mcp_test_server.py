"""
시험용 MCP 서버 (stdio): status(읽기 전용) · restart(파괴적) · hidden(허용 목록 밖)

    python tests/shared/mcp_test_server.py
"""

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

app = MCPServer("edgevoice-test")


@app.tool(annotations=ToolAnnotations(readOnlyHint=True))
def status() -> str:
    """서비스 상태를 알려 준다."""
    return "모든 서비스 정상"


@app.tool(annotations=ToolAnnotations(destructiveHint=True))
def restart(service: str) -> str:
    """서비스를 재시작한다."""
    if service == "unknown":
        raise ValueError(f"없는 서비스: {service}")
    return f"{service} 재시작 완료"


@app.tool()
def hidden() -> str:
    """허용 목록에 없는 도구."""
    return "보이면 안 됨"


if __name__ == "__main__":
    app.run()
