## 1. Prism 통합 방식 (Avalonia 에서)
- options: Prism.Avalonia(DryIoc/Unity 컨테이너, Autofac 미지원) / Prism.Core 8.1.97 + Autofac 직접 구성
- chosen: Prism.Core 8.1.97(BindableBase, DelegateCommand) + Autofac
- why: 사용자가 Prism + Autofac 을 지정했고 Prism.Avalonia 는 Autofac 을 지원하지 않음. 기존 ViewModel 을 그대로 재사용 가능
- effect: Region 탐색 없이 TabControl + DataContext 바인딩. Region 이 필요하면 Prism.Avalonia + DryIoc 로 교체

## 2. 기존 `.xaml` 파일 이름 유지
- options: `.axaml` 로 새로 만들고 기존 파일 삭제 / 기존 `.xaml` 파일 내용을 Avalonia XAML 로 교체
- chosen: 기존 `.xaml` 파일 내용 교체 + csproj 에 `<AvaloniaXaml Include="**\*.xaml" />`
- why: 이번 작업 규칙상 이전에 만든 파일을 삭제/이름변경할 수 없음
- effect: 동작 차이 없음. 나중에 `git mv *.xaml *.axaml` 후 csproj 의 해당 줄을 지우면 Avalonia 관례대로 됨

## 3. 대상 프레임워크
- options: net8.0 / net10.0
- chosen: net8.0 (Core 와 동일)
- why: 기존 Core 가 net8.0 이고 런타임 8.0 이 설치되어 있으며 Jetson(ARM64 Linux)에서도 LTS 로 무난
- effect: csproj 의 TargetFramework 만 바꾸면 됨

## 4. 마이크 입력 연결 실패 알림
- options: 별도 알림 창 / 오버레이 라벨·트레이 툴팁에 잠시 표시
- chosen: 오버레이 라벨·툴팁에 3초 표시
- why: Avalonia TrayIcon 은 풍선 알림을 제공하지 않고, 추가 창은 방해가 됨
- effect: `TrayController.ToggleTalk` 의 catch 블록에서 변경

## 5. Linux/Jetson 마이크 지원
- options: 이번에 크로스플랫폼 오디오 라이브러리로 교체 / NAudio(Windows 전용) 유지
- chosen: NAudio 유지 (UI 는 크로스플랫폼)
- why: 요청 범위는 Avalonia 화면 전환이고 Core 의 오디오 캡처 교체는 범위 밖. Linux 에서는 연결 실패로 표시만 됨
- effect: 필요 시 `MicrophoneStreamer` 의 `WaveInEvent` 부분만 교체하면 됨

## 6. 테스트 프로젝트 추가
- options: 테스트 없음(`dotnet test` 가 아무것도 실행하지 않음) / Core 단위 테스트 추가
- chosen: `tests/EdgeVoice.Agent.Core.Tests`(xunit) — Orchestrator 상태 → 파형 상태 매핑 테스트
- why: 검사 명령 `dotnet test` 가 실제로 무언가를 검증하도록
- effect: 테스트 추가는 이 프로젝트에 파일만 더하면 됨
