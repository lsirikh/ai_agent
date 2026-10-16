# DECISIONS

## 1. WebView2 로 갈아탈지, 지금의 Avalonia 네이티브 MVVM 을 유지할지
- options: WebView2 로 기존 웹(index.html) 감싸기 / Avalonia 네이티브 MVVM 유지
- chosen: Avalonia 네이티브 유지 (현재 코드는 WebView2 래퍼가 아님)
- why: 사용자가 이전 요청에서 둘 다 허용했고, 이미 Prism+Autofac 네이티브로 6개 페이지가 구현돼 있음. Ironwall.Monitoring 호스트에 붙일 때도 네이티브가 유리
- effect: 웹 전용 디자인 도구(Figma/shadcn MCP)는 직접 쓰지 않고 Office(Fluent 2) 토큰을 XAML 리소스로 옮김. 바꾸려면 MainWindow 를 WebView 컨트롤로 교체

## 2. 차트 라이브러리
- options: LiveCharts2 (LiveChartsCore.SkiaSharpView.Avalonia 2.0.5) / ScottPlot.Avalonia / Avalonia Shape 로 직접 그리기
- chosen: LiveCharts2 2.0.5 (정식)
- why: Avalonia 용 MVVM 바인딩·애니메이션·범례·도넛/막대/선 모두 지원, 가장 널리 쓰임
- effect: Desktop csproj 에 패키지 1개 추가. 교체 시 DashboardViewModel 의 `*Series`/`*Axes` 와 MainWindow 의 `lvc:` 컨트롤만 바꾸면 됨

## 3. 차트 색을 테마별로 바꿀지
- options: 테마 변경 시 VM 이 차트 페인트를 다시 만듦 / 라이트·다크 모두에서 읽히는 중간 명도 Office 팔레트 고정
- chosen: 고정 팔레트(#2886DE, #13A10E, #D13438, #8764B8, 축·격자 #8A8886)
- why: VM 이 테마를 몰라도 되고 코드가 가장 적음. 스크린샷으로 양쪽 테마 가독성 확인
- effect: 테마별 색이 필요하면 DashboardViewModel 상수를 테마 리소스로 옮기면 됨

## 4. 테마 기본값과 저장
- options: OS 테마 따르기 + 저장 안 함 / 선택값을 appsettings 등에 저장
- chosen: 시작은 OS 테마, 전환값은 저장하지 않음
- why: 요청 범위가 "전환 구현"이라 최소 구현. 저장은 나중에 쉽게 추가 가능
- effect: 재시작하면 OS 테마로 돌아감. 저장하려면 MainViewModel.IsDarkTheme setter 에서 옵션 파일에 기록

## 5. 헤디드 테스트 방식
- options: desktop-automation 스킬(desk.py)로 실제 앱 조작 / xUnit 에서 실제 플랫폼으로 창을 띄움
- chosen: 별도 xUnit 프로젝트(EdgeVoice.Agent.Desktop.HeadedTests), `EDGEVOICE_HEADED=1` 일 때만 실행, 실제 docker 백엔드 사용
- why: `python` 명령이 허용 목록 밖이라 desk.py 실행 불가. 디스플레이·백엔드가 없는 환경(하네스/CI)에서 실패하지 않도록 기본 건너뜀
- effect: CI 에서는 4개가 "건너뜀"으로 표시. 로컬에서 `dotnet test tests/EdgeVoice.Agent.Desktop.HeadedTests -e EDGEVOICE_HEADED=1`
