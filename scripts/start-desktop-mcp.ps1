# EdgeVoice 데스크톱 MCP 를 이 PC 에서 띄운다 (services/desktop_mcp/server.py).
# 로컬 LLM 이 메모장·워드·엑셀·파워포인트를 실행하고 Downloads\Tests 에 저장한다.
# 컨테이너는 http://host.docker.internal:8932/mcp 로 붙는다 (config/mcp/servers.json 의 "desktop").
#   - 127.0.0.1 에만 열고 허용 호스트를 정해 둔다
#   - 프로그램 창이 사용자 화면에 떠야 하므로 로그인한 사용자 세션에서 실행한다
# 로그인할 때 자동으로 띄우려면: .\scripts\start-desktop-mcp.ps1 -InstallStartup
param([switch]$InstallStartup)

$port = 8932
if ($InstallStartup) {
    $startup = [Environment]::GetFolderPath("Startup")
    $cmd = "powershell -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$PSCommandPath`""
    Set-Content -Path (Join-Path $startup "EdgeVoice-desktop-mcp.cmd") -Value "@start `"`" $cmd" -Encoding ascii
    Write-Output "로그인할 때 자동 실행: $startup\EdgeVoice-desktop-mcp.cmd"
}

if (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) {
    Write-Output "데스크톱 MCP 가 이미 떠 있다 (포트 $port)"
    exit 0
}

$root = Split-Path -Parent $PSScriptRoot
$log = Join-Path $env:LOCALAPPDATA "EdgeVoice\desktop-mcp.log"
New-Item -ItemType Directory -Force (Split-Path $log) | Out-Null
$server = Join-Path $root "services\desktop_mcp\server.py"
Start-Process -WindowStyle Hidden -WorkingDirectory $root -FilePath "cmd.exe" `
    -ArgumentList "/c python `"$server`" > `"$log`" 2>&1"
Write-Output "데스크톱 MCP 시작: http://127.0.0.1:$port/mcp (로그 $log)"
