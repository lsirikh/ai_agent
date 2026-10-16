# PLAN — Office 디자인 + 차트 대시보드 + 라이트/다크 + 헤디드/헤드리스 시나리오 테스트

## 목표
1. 웹 디자인 스킬·MCP 조사 후 유망한 것 선정
2. 시나리오 테스트를 부문별로 헤디드/헤드리스로 나눠 수행 (이전 작업에선 Core 단위 테스트 8개뿐이었음 — 안 했던 것이 맞음)
3. 차트/그래프 대시보드, 모던 디자인, 다크/라이트 테마 전환, Microsoft Office 디자인 답습

## 진행
- [x] 현 구조 확인: Avalonia 네이티브 MVVM(Prism.Core+Autofac). WebView2 래퍼가 아님
- [x] 디자인 스킬/MCP 조사 (아래 "조사")
- [x] `App.axaml`: Fluent 팔레트(Office 파랑) + `Office*Brush` Light/Dark 테마 리소스
- [x] `MainWindow.axaml`: Office 앱 바 + 왼쪽 탐색 + 카드 레이아웃, 6개 페이지 모두 재배치
- [x] `MainViewModel`: `IsDarkTheme` / `ToggleThemeCommand` / `ThemeLabel`
- [x] `DashboardViewModel`: LiveCharts2 4개 차트(GPU 추이, 서비스 도넛, 로그 레벨 막대, 서비스별 로그 가로막대)
- [x] `App.BuildContainer` 분리(테스트가 같은 DI 구성 사용)
- [x] 헤드리스 테스트 프로젝트 31개 시나리오 (테마 6, 대시보드 7, 페이지 7, 트레이 11 — Theory 포함)
- [x] 헤디드 테스트 프로젝트 4개 시나리오 (실제 창 + 실제 docker 백엔드 + 실제 LLM), 13장 스크린샷 확인
- [x] `dotnet build` / `dotnet test` 통과

## 조사 (2026-10 기준)
- 디자인 MCP 1위: Figma Context MCP(GLips, ~15k★) — Figma 원본이 있을 때만 의미. 이 프로젝트엔 Figma 원본 없음
- 프론트엔드 테스트/검사: Playwright MCP, Chrome DevTools MCP (이미 `.mcp.json` 에 있음) — 웹(HTML) 대상이라 Avalonia 네이티브 창은 직접 못 봄
- Avalonia 전용: Avalonia DevTools MCP(2026-01, Accelerate 상용 라이선스), Avalonia Build MCP(문서), XamlMcp(오픈소스, 실행 중 앱 트리/스크린샷)
- 스킬: `frontend-design`(미적 방향), `dataviz`(차트 팔레트/형식) — 이번 디자인 원칙에 반영 (중간 명도 팔레트, 라벨/격자 중립색)
- 선정: 구현은 Avalonia 네이티브 + Fluent 2(Office) 토큰 + LiveCharts2, 검증은 Avalonia.Headless(헤드리스) + 실제 창 RenderTargetBitmap(헤디드). 상용 DevTools MCP 와 Figma 는 도입 안 함

## 발견
- `python` 이 허용 목록 밖이라 desktop-automation 스킬(desk.py)로 실제 창 조작 불가 → 헤디드는 xUnit 에서 실제 플랫폼으로 창을 띄우는 방식으로 대체
- 실제 백엔드에서 설정 페이지 `LLM Model` 콤보가 비어 보임(현재 모델 id 가 목록 id 와 불일치하는 기존 동작) — 이번 범위 밖
- LiveCharts 애니메이션 때문에 캡처 전 ~1.5초 대기 필요

## 남은 일
- 없음 (선택: 테마 선택값 저장, 트레이 오버레이 색을 Office 팔레트로 통일)
