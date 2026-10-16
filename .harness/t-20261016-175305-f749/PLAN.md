# PLAN — EdgeVoice .NET 트레이 에이전트

## 목표
- 트레이 아이콘에서 음성 "듣는 중"과 "말하는 중"이 구분되는 퍼지는 파형(좁쌀/물결) UI → 웹 없이 음성 사용
- 기존 웹 대시보드의 모든 페이지/기능을 .NET(WPF, MVVM, Prism + Autofac)으로 이식
- 추후 Dotnet.Ironwall.Monitoring 에 에이전트로 붙일 수 있도록 Core 를 분리한 단독 Agent

## 진행
- [x] 기존 웹(index.html)·백엔드 API 조사 (탭 6개: Dashboard, Chat, Knowledge, Settings, History, Logs)
- [x] `clients/dotnet/src/EdgeVoice.Agent.Core`: API/SSE 클라이언트, VoiceStateMonitor(`/api/status/stream`), MicrophoneStreamer(NAudio → `/ws/audio`), EdgeVoiceCoreModule(Autofac)
- [x] `clients/dotnet/src/EdgeVoice.Agent.Desktop`: TrayController(애니메이션 아이콘), VoiceOrbWindow(오버레이), RippleRenderer, MainWindow + 6개 ViewModel
- [x] README, sln
- [ ] `dotnet build` 검증 — 이 세션에서 `dotnet` 명령이 허용되지 않아 미실행

## 발견 사항
- 웹 UI 는 audio-gateway 를 `:8008` 로 하드코딩하지만 호스트 포트는 11008 → appsettings.json 으로 설정 가능하게 함
- `/api/dashboard/stream` 은 orchestrator 상태를 5초마다만 보냄 → 트레이 상태는 1초 주기 `/api/status/stream` 사용
- 오디오 WS 는 TTS 오디오를 돌려주지 않음(재생은 서버측) → "말하는 중"은 orchestrator `tts_processing` 상태로 판단
- 루트 pytest 베이스라인 실패(`tests/test_project_structure.py` 등)는 이번 작업과 무관

## 남은 작업
- 실제 빌드/실행 확인 (`cd clients/dotnet && dotnet build`), 컴파일 오류 시 수정
