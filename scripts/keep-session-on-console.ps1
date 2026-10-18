# 원격 데스크톱이 끊겨도 이 PC 화면(세션)이 잠기지 않게 한다 — 끊기는 순간 세션을 이 PC 의
# 실제 화면(콘솔)으로 넘긴다(tscon <세션> /dest:console). 화면 캡처·마우스·키보드가 계속
# 동작해 EdgeVoice 의 그림판·컴퓨터 조작과 시나리오 시험이 원격이 끊긴 동안에도 돈다.
#
#   (관리자 PowerShell 에서 한 번)
#   .\scripts\keep-session-on-console.ps1 -Install     # 작업 스케줄러에 등록
#   .\scripts\keep-session-on-console.ps1 -Status      # 등록 여부
#   .\scripts\keep-session-on-console.ps1 -Uninstall   # 해제
#
# 주의: 끊긴 동안 이 PC 의 모니터에는 잠기지 않은 바탕화면이 보인다(누군가 이 PC 앞에 있으면
# 볼 수 있다). 다시 원격으로 붙으면 평소처럼 원격 화면으로 돌아온다.
param([switch]$Install, [switch]$Uninstall, [switch]$Status)

$name = "EdgeVoice-KeepSessionOnConsole"

if ($Status -or -not ($Install -or $Uninstall)) {
    $task = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
    if ($task) { Write-Output "등록됨: $name ($($task.State))" } else { Write-Output "등록 안 됨: $name" }
    exit 0
}

$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin) {
    Write-Output "관리자 PowerShell 에서 실행해야 한다 (시작 → PowerShell 오른쪽 클릭 → 관리자 권한으로 실행)."
    exit 1
}

if ($Uninstall) {
    Unregister-ScheduledTask -TaskName $name -Confirm:$false -ErrorAction SilentlyContinue
    Write-Output "해제했다: $name"
    exit 0
}

# 이벤트 24 = 원격 데스크톱 세션 연결 끊김. 끊긴 세션 번호(SessionID)를 tscon 에 넘긴다
$xml = @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Description>EdgeVoice: 원격 데스크톱이 끊기면 세션을 콘솔로 넘겨 화면이 잠기지 않게 한다</Description></RegistrationInfo>
  <Triggers>
    <EventTrigger>
      <Enabled>true</Enabled>
      <Subscription>&lt;QueryList&gt;&lt;Query Id="0" Path="Microsoft-Windows-TerminalServices-LocalSessionManager/Operational"&gt;&lt;Select Path="Microsoft-Windows-TerminalServices-LocalSessionManager/Operational"&gt;*[System[(EventID=24)]]&lt;/Select&gt;&lt;/Query&gt;&lt;/QueryList&gt;</Subscription>
      <ValueQueries><Value name="SessionId">Event/UserData/EventXML/SessionID</Value></ValueQueries>
    </EventTrigger>
  </Triggers>
  <Principals><Principal id="Author"><UserId>S-1-5-18</UserId><RunLevel>HighestAvailable</RunLevel></Principal></Principals>
  <Settings>
    <MultipleInstancesPolicy>Parallel</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <ExecutionTimeLimit>PT1M</ExecutionTimeLimit>
    <Enabled>true</Enabled>
  </Settings>
  <Actions Context="Author">
    <Exec><Command>$env:SystemRoot\System32\tscon.exe</Command><Arguments>`$(SessionId) /dest:console</Arguments></Exec>
  </Actions>
</Task>
"@
Register-ScheduledTask -TaskName $name -Xml $xml -Force | Out-Null
Write-Output "등록했다: $name — 원격이 끊기면 세션을 이 PC 화면으로 넘긴다. 해제: -Uninstall"
