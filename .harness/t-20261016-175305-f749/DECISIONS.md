## 1. WebView2 로 기존 웹을 감쌀지, 네이티브 WPF MVVM 으로 다시 만들지
- options: WebView2 로 기존 index.html 호스팅 / WPF MVVM(Prism + Autofac) 네이티브 화면
- chosen: WPF MVVM 네이티브 화면
- why: 사용자가 "MVVM ViewModel + Autofac/Prism" 쪽을 마지막에 명시했고, 나중에 Ironwall.Monitoring(.NET)에 에이전트로 붙이려면 화면/로직이 .NET 코드여야 재사용이 쉽다
- effect: 6개 탭이 `MainWindow.xaml` + `ViewModels/*` 로 구현됨. WebView2 로 바꾸려면 MainWindow 내용을 WebView2 하나로 교체하면 됨(트레이/Core 는 그대로)

## 2. Prism 컨테이너 통합 방식
- options: Prism.Wpf 9(상용 라이선스, Autofac 미지원) / Prism.Autofac 7.x(구버전) / Prism.Core 8.1.97(MIT) + Autofac 직접 사용
- chosen: Prism.Core 8.1.97(BindableBase, DelegateCommand) + Autofac 컨테이너 직접 구성
- why: 최신 Prism 은 Autofac 통합을 제공하지 않고 Prism 9 는 라이선스가 바뀜. MVVM 기본 요소만 Prism 에서 쓰고 DI 는 Autofac 으로 하는 것이 가장 단순
- effect: Region/Module 탐색은 없음(TabControl + DataContext 바인딩). 필요 시 Prism.Wpf + DryIoc 등으로 교체 가능

## 3. 트레이 음성 상태 소스
- options: `/api/dashboard/stream`(5초 주기) / `/api/status/stream`(1초 주기) / REST 폴링
- chosen: `/api/status/stream`, 그리고 로컬 마이크 스트리밍 중이면 '듣는 중'으로 표시
- why: 말하기/듣기 전환을 빨리 반영해야 하고, 백엔드 수정 없이 쓸 수 있는 가장 빠른 스트림
- effect: `VoiceStateMonitor` 의 경로만 바꾸면 소스 교체 가능. 더 빠른 반응이 필요하면 백엔드에 상태 변경 즉시 푸시 이벤트 추가 필요

## 4. 듣기/말하기 파형 표현
- options: 둘 다 같은 원형 물결에 색만 다르게 / 듣기=좁쌀 점, 말하기=물결 원
- chosen: 듣기=파란 좁쌀 점이 퍼짐(마이크 레벨 반영), 말하기=초록 물결 원이 퍼짐, 생각 중=보라 점 회전
- why: 사용자가 "좁쌀 혹은 물결"을 언급했고, 모양까지 다르면 작은 트레이 아이콘에서도 구분이 쉬움
- effect: `Tray/RippleRenderer.cs` 한 곳에서 그림/색 변경 가능. 트레이 아이콘(32px)과 오버레이(120px)가 같은 렌더러 사용

## 5. 트레이 외 화면 오버레이 추가 여부
- options: 트레이 아이콘만 / 트레이 + 작은 항상 위 오버레이
- chosen: 트레이 + 오버레이(기본 표시, 트레이 메뉴에서 숨김 가능)
- why: 트레이 아이콘은 16~32px 라 파형이 작고 숨겨진 아이콘 영역에 들어가면 보이지 않음. "웹을 보지 않고도" 상태를 보려면 눈에 띄는 표시가 필요
- effect: `TrayController` 생성자에서 `_orb.Show()` 를 빼거나 `_orbItem.Checked` 기본값을 false 로 바꾸면 기본 숨김

## 6. 솔루션 위치와 설정 방식
- options: 저장소 루트 / `clients/dotnet` 하위, 설정은 Microsoft.Extensions.Configuration / 단순 JSON
- chosen: `clients/dotnet` 하위, `appsettings.json` 을 System.Text.Json 으로 직접 읽음
- why: 기존 Python 서비스 구조(services/, tests/)와 분리하고, 추가 패키지 의존을 줄임
- effect: 기본 주소는 dev compose 호스트 포트(11000/11008). 파일만 고치면 됨
