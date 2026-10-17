# EdgeVoice 가 '내가 쓰던 크롬'(로그인 상태 그대로)을 조작하게 하는 확장 프로그램을 준비한다.
#
# ChatGPT · Claude 크롬 확장과 같은 구조다: 확장이 chrome.debugger(DevTools 프로토콜)로
# 탭을 읽고 누르며, 이 PC 의 브라우저 MCP(scripts/start-browser-mcp.ps1 -Extension)와 연결된다.
# 확장은 Microsoft 의 공식 'Playwright Extension'(ID mmlmfjhmonkocbjadbfplnigmagldckm)을 쓴다
# — 브라우저 MCP 가 이 ID 로 확장을 찾으므로 manifest 의 key 가 그대로인 공식 패키지를 쓴다.
#
#   .\scripts\install-chrome-extension.ps1          # 내려받아 풀고 확장 페이지를 연다
#   .\scripts\install-chrome-extension.ps1 -NoOpen  # 내려받아 풀기만
#
# 그다음 (사람이 한 번 해야 한다 — 크롬은 프로그램이 확장을 몰래 설치하지 못하게 막는다):
#   1. chrome://extensions 오른쪽 위 '개발자 모드' 켜기
#   2. '압축해제된 확장 프로그램 로드' → 아래에 나오는 폴더 선택
#   3. 확장 아이콘을 눌러 PLAYWRIGHT_MCP_EXTENSION_TOKEN 값을 복사해
#      %LOCALAPPDATA%\EdgeVoice\browser-mcp\extension-token.txt 에 저장
#   4. .\scripts\start-browser-mcp.ps1 -Extension -Restart
param([switch]$NoOpen)

$ErrorActionPreference = "Stop"
$id = "mmlmfjhmonkocbjadbfplnigmagldckm"
$root = Join-Path $env:LOCALAPPDATA "EdgeVoice\chrome-extension"
$target = Join-Path $root "playwright-extension"
$crx = Join-Path $root "playwright-extension.crx"
New-Item -ItemType Directory -Force $root | Out-Null

$url = "https://clients2.google.com/service/update2/crx?response=redirect&prodversion=141.0" +
    "&acceptformat=crx2,crx3&x=id%3D$id%26uc"
Invoke-WebRequest -Uri $url -OutFile $crx -UseBasicParsing

# CRX3: "Cr24" + 버전(4) + 헤더 길이(4) + 헤더 + ZIP
$bytes = [IO.File]::ReadAllBytes($crx)
if ([Text.Encoding]::ASCII.GetString($bytes, 0, 4) -ne "Cr24") { throw "CRX 파일이 아닙니다" }
$headerLength = [BitConverter]::ToUInt32($bytes, 8)
$zipStart = 12 + $headerLength
$zip = Join-Path $root "playwright-extension.zip"
[IO.File]::WriteAllBytes($zip, $bytes[$zipStart..($bytes.Length - 1)])

if (Test-Path $target) { Remove-Item -Recurse -Force $target }
Add-Type -AssemblyName System.IO.Compression.FileSystem
[IO.Compression.ZipFile]::ExtractToDirectory($zip, $target)
# '_' 로 시작하는 폴더가 있으면 크롬이 압축해제된 확장으로 불러오지 않는다
$metadata = Join-Path $target "_metadata"
if (Test-Path $metadata) { Remove-Item -Recurse -Force $metadata }
Remove-Item -Force $zip, $crx

$manifest = Get-Content (Join-Path $target "manifest.json") -Raw | ConvertFrom-Json
Write-Output "준비됨: $($manifest.name) $($manifest.version)"
Write-Output "폴더: $target"
Write-Output "chrome://extensions → 개발자 모드 → '압축해제된 확장 프로그램 로드' → 위 폴더"

if (-not $NoOpen) {
    $chrome = @(
        "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
        "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
        "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
    ) | Where-Object { Test-Path $_ } | Select-Object -First 1
    if ($chrome) { Start-Process $chrome "chrome://extensions" }
    Start-Process explorer.exe $target
}
