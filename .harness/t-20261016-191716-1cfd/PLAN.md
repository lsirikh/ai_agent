# PLAN — EdgeVoice .NET 에이전트를 Avalonia 네이티브로 전환

## 목표
- 이전 작업(t-20261016-175305-f749)에서 WPF 로 만든 Desktop 앱을 사용자가 원래 요청한 **Avalonia** 로 전환
- 사용자 선택: "Avalonia 네이티브" — 웹뷰 없이 기존 웹 6개 페이지를 Avalonia MVVM 화면으로 (Prism.Core + Autofac)
- 트레이 아이콘/오버레이에서 듣기(파란 좁쌀)·말하기(초록 물결) 구분 파형 유지
- Core 는 그대로 분리(추후 Dotnet.Ironwall.Monitoring 에 Autofac 모듈로 붙이기)

## 진행
- [x] Desktop csproj: WPF/WinForms → Avalonia 11.3.0 (Desktop, Fluent, DataGrid), net8.0 (Windows 전용 TFM 제거)
- [x] `Program.cs` 추가, `App.xaml(.cs)` Avalonia 수명주기(OnExplicitShutdown)로 변경
- [x] `MainWindow.xaml` 6개 탭 Avalonia XAML 로 재작성 (닫기 = 숨기기)
- [x] 트레이: Avalonia `TrayIcon` + `NativeMenu`, 아이콘은 `RenderTargetBitmap` 으로 매 프레임 그림
- [x] 오버레이: `VoiceOrbWindow` + `RippleView` 컨트롤(직접 Render), 클릭=말하기 토글, 드래그=이동, 오른쪽 클릭=메인 창
- [x] `Dialogs.cs`: MessageBox/OpenFileDialog 대체(확인 창, StorageProvider 파일 선택)
- [x] ViewModel 의 WPF Dispatcher → `Avalonia.Threading.Dispatcher.UIThread`
- [x] `tests/EdgeVoice.Agent.Core.Tests`(xunit) 추가, sln 등록
- [x] `dotnet build` 경고 0/오류 0, `dotnet test` 8개 통과, `dotnet run` 으로 실행 시 예외 없이 상주 확인

## 발견 사항
- 설치된 SDK 는 10.0.401 뿐, 런타임 8.0.22 있음 → net8.0 유지로 빌드/실행 가능
- `dotnet new xunit -f net8.0` 은 SDK 10 템플릿에서 거부됨 → csproj 직접 작성
- 이전 작업의 `.xaml` 파일은 이번 작업에서 지우거나 이름을 바꿀 수 없어 `.xaml` 이름 그대로 Avalonia XAML 로 컴파일(`<AvaloniaXaml Include="**\*.xaml" />`)
- Avalonia 트레이에는 풍선 알림이 없음 → 마이크 연결 실패는 오버레이 라벨/툴팁에 3초 표시
- `MicrophoneStreamer` 는 NAudio.WinMM(Windows 전용) → Linux/Jetson 에서는 말하기 불가(화면은 동작)

## 남은 작업
- 실제 백엔드 연결 상태에서 화면별 수동 확인
- Linux 마이크 지원이 필요하면 MicrophoneStreamer 를 크로스플랫폼 오디오 라이브러리로 교체
