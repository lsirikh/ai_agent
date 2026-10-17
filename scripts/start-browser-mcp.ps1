# EdgeVoice 브라우저 MCP (Playwright MCP) 를 이 PC 에서 띄운다.
# 컨테이너(backend · orchestrator)가 http://host.docker.internal:8931/mcp 로 붙어
# 이 PC 화면의 크롬을 연다 (config/mcp/servers.json 의 "browser").
#   - 127.0.0.1 에만 열고, 허용 호스트를 정해 둔다(다른 PC 에서 붙지 못한다)
#   - --shared-browser-context: 채팅과 음성이 같은 크롬을 함께 쓴다
#     (없으면 두 번째 연결이 "Browser is already in use" 로 실패했다)
# 로그인할 때 자동으로 띄우려면: .\scripts\start-browser-mcp.ps1 -InstallStartup
param([switch]$InstallStartup)

$port = 8931
if ($InstallStartup) {
    $startup = [Environment]::GetFolderPath("Startup")
    $cmd = "powershell -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$PSCommandPath`""
    Set-Content -Path (Join-Path $startup "EdgeVoice-browser-mcp.cmd") -Value "@start `"`" $cmd" -Encoding ascii
    Write-Output "로그인할 때 자동 실행: $startup\EdgeVoice-browser-mcp.cmd"
}

if (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) {
    Write-Output "브라우저 MCP 가 이미 떠 있다 (포트 $port)"
    exit 0
}

$work = Join-Path $env:LOCALAPPDATA "EdgeVoice\browser-mcp"
New-Item -ItemType Directory -Force $work | Out-Null
$hosts = "host.docker.internal:$port,host.docker.internal,localhost:$port,127.0.0.1:$port"
$mcpArgs = "-y @playwright/mcp@0.0.83 --port $port --host 127.0.0.1 --allowed-hosts $hosts " +
    "--browser chrome --shared-browser-context --output-dir `"$work\out`""
Start-Process -WindowStyle Hidden -WorkingDirectory $work -FilePath "cmd.exe" `
    -ArgumentList "/c npx $mcpArgs > `"$work\server.log`" 2>&1"
Write-Output "브라우저 MCP 시작: http://127.0.0.1:$port/mcp (로그 $work\server.log)"
