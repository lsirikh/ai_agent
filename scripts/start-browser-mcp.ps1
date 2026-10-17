# EdgeVoice 브라우저 MCP (Playwright MCP) 를 이 PC 에서 띄운다.
# 컨테이너(backend · orchestrator)가 http://host.docker.internal:8931/mcp 로 붙어
# 이 PC 화면의 크롬을 연다 (config/mcp/servers.json 의 "browser").
#   - 127.0.0.1 에만 열고, 허용 호스트를 정해 둔다(다른 PC 에서 붙지 못한다)
#   - --shared-browser-context: 채팅과 음성이 같은 크롬을 함께 쓴다
#     (없으면 두 번째 연결이 "Browser is already in use" 로 실패했다)
# 로그인할 때 자동으로 띄우려면: .\scripts\start-browser-mcp.ps1 -InstallStartup
#
# -Extension: 따로 띄운 크롬 대신 '내가 쓰던 크롬'(로그인 상태 그대로)을 조작한다.
#   scripts/install-chrome-extension.ps1 로 확장을 준비해 크롬에 넣고, 확장의 토큰을
#   %LOCALAPPDATA%\EdgeVoicerowser-mcp\extension-token.txt 에 저장한 뒤 쓴다
#   (토큰이 있으면 연결을 매번 승인하지 않아도 된다).
# -Restart: 이미 떠 있는 브라우저 MCP 를 끄고 다시 띄운다.
param([switch]$InstallStartup, [switch]$Extension, [switch]$Restart)

$port = 8931
if ($InstallStartup) {
    $startup = [Environment]::GetFolderPath("Startup")
    $mode = if ($Extension) { " -Extension" } else { "" }
    $cmd = "powershell -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$PSCommandPath`"$mode"
    Set-Content -Path (Join-Path $startup "EdgeVoice-browser-mcp.cmd") -Value "@start `"`" $cmd" -Encoding ascii
    Write-Output "로그인할 때 자동 실행: $startup\EdgeVoice-browser-mcp.cmd"
}

$listening = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
if ($listening -and $Restart) {
    $listening | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -Confirm:$false }
    Start-Sleep -Seconds 1
} elseif ($listening) {
    Write-Output "브라우저 MCP 가 이미 떠 있다 (포트 $port) — 다시 띄우려면 -Restart"
    exit 0
}

$work = Join-Path $env:LOCALAPPDATA "EdgeVoice\browser-mcp"
New-Item -ItemType Directory -Force $work | Out-Null
$hosts = "host.docker.internal:$port,host.docker.internal,localhost:$port,127.0.0.1:$port"
$mcpArgs = "-y @playwright/mcp@0.0.83 --port $port --host 127.0.0.1 --allowed-hosts $hosts " +
    "--output-dir `"$work\out`" "
$setToken = ""
if ($Extension) {
    # 내가 쓰던 크롬에 확장으로 붙는다(채팅·음성은 각자 탭 묶음을 쓴다)
    $mcpArgs += "--extension"
    $tokenFile = Join-Path $work "extension-token.txt"
    if (Test-Path $tokenFile) {
        $token = (Get-Content $tokenFile -Raw).Trim()
        $setToken = "set PLAYWRIGHT_MCP_EXTENSION_TOKEN=$token&& "
    } else {
        Write-Output "토큰 파일이 없어 연결할 때마다 크롬에서 승인해야 한다: $tokenFile"
    }
} else {
    $mcpArgs += "--browser chrome --shared-browser-context"
}
Start-Process -WindowStyle Hidden -WorkingDirectory $work -FilePath "cmd.exe" `
    -ArgumentList "/c $setToken npx $mcpArgs > `"$work\server.log`" 2>&1"
Write-Output "브라우저 MCP 시작: http://127.0.0.1:$port/mcp (로그 $work\server.log)"
