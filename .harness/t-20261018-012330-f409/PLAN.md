# PLAN — 설정에 MCP · 스킬 관리 공간

## 목표
설정 화면(.NET Avalonia Settings 탭)에서 MCP 서버와 스킬을 등록·수정·삭제하고 체크박스로 켜고 끈다.
켜고 끄면 백엔드(채팅)·오케스트레이터(음성)가 재시작 없이 MCP 연결을 다시 만든다.

## 설계
- 저장: Redis (기존 도구 설정 `edgevoice:settings:tools` 와 같은 방식, Redis 는 appendonly)
  - MCP: `edgevoice:settings:mcp` = 서버 목록 JSON 배열. 비어 있으면 `MCP_CONFIG_PATH`(servers.json) 를 처음 값으로 쓴다.
  - 스킬: `edgevoice:settings:skills` = `{"disabled_tools": [...], "prompts": [{name, description, instructions, enabled}]}`
- `shared/mcp_client.py`: `MCPServerConfig.enabled`, `load_mcp_servers(redis)`, `MCPManager.apply(configs)`(바뀐 서버만 다시 연결, 꺼진 서버는 닫음, 잠금), `start_mcp_from_env(redis)` 는 항상 매니저를 돌려준다. 재연결(reconnect) 로직은 그대로.
- 두 서비스는 턴마다 `apply(await load_mcp_servers(redis))` 로 맞춘다(바뀐 게 없으면 아무것도 안 함). 백엔드 API 는 저장 직후 바로 apply.
- `shared/skills.py`: 내장 도구 = 스킬 목록, `load_skills`, `with_skills`(켜진 프롬프트 스킬을 시스템 프롬프트에 붙임).
  `load_tool_settings` 가 `disabled_tools` 를 합치고 `build_registry` 가 그 도구를 뺀다.
- 백엔드 라우터 `routes/extensions.py`: `GET/POST /api/settings/mcp`, `PUT/DELETE /api/settings/mcp/{name}`, `GET/PUT /api/settings/skills`.
- .NET: `SettingsViewModel` 을 partial 로, `SettingsViewModel.Extensions.cs` 에 MCP·스킬 목록/체크박스/편집. MainWindow.axaml Settings 탭에 카드 2개.

## 진행
- [x] 조사·설계
- [x] shared: mcp_client (enabled, load_mcp_servers, apply) + 테스트 (tests/shared/test_mcp_client.py::TestSettings)
- [x] shared: skills + build_registry 필터 + 테스트 (tests/shared/test_skills.py)
- [x] backend: extensions 라우터 + chat 연동 + 채팅 시스템 프롬프트 스킬 + 테스트 (tests/backend/test_extension_settings.py — 실제 stdio MCP 시험 서버로 연결)
- [x] orchestrator: 턴마다 MCP 맞추기 + 스킬 프롬프트 + 테스트 (tests/orchestrator/test_voice_extensions.py)
- [x] .NET: VM(SettingsViewModel.Extensions.cs) + XAML 카드 2개 + 헤드리스 테스트 (ExtensionSettingsScenarioTests, 6개)
- [x] ruff (바꾼 파일 오류 수 늘지 않음, 새 파일 0), 관련 테스트
- [x] 최신 master(1a3649c) 반영: master 에서만 바뀐 파일은 master 내용 그대로, 둘 다 바뀐 4개(shared/mcp_client.py · shared/tools.py · services/orchestrator/app/orchestrator.py · tests/shared/test_mcp_client.py)는 `git merge-file` 로 3-way 병합. 충돌 2곳(상수 블록, 테스트 클래스 뒤)은 양쪽 모두 살림.
  - master 동작(retry_after·_retry_connect·reconnect, parse_json_arguments, play_youtube, draw_picture 규칙 등)은 서버별로 tools()/call() 안에서 돌아서 apply 로 다시 만든 서버에도 그대로 걸린다 → 테스트 `test_server_turned_back_on_still_reconnects_when_listing`.
  - 새 데스크톱 도구가 설정 목록에 보이는지: `test_project_config_offers_new_desktop_tools`, `test_settings_list_shows_new_desktop_tools_from_project_config`.
  - .NET FakeBackend 에 /api/settings/mcp·skills 기본 응답 추가 (없으면 404 가 상태줄을 덮어 PageConsistency 테스트가 때때로 실패).

## 남은 일
- 없음. (선택) 연결 실패한 서버를 '연결 상태 새로고침' 때 다시 연결 시도 — 지금은 끄고 켜거나 도구 호출 때 다시 연결된다.
- 전체 pytest 의 기존 실패 4개는 이 작업과 무관: test_chat_router_exists(FastAPI 0.137 `_IncludedRouter`), test_chat_context(`reference` 인자), test_postgres_container_exists(pgvector 이미지), test_end_pause_default(tests/orchestrator 와 한 번에 돌리면 `from app import main` 이 오케스트레이터 app 을 잡아 실패 — master 에서도 같음, tests/shared 만 돌리면 통과).

## 발견
- servers.json 은 컨테이너에 `:ro` 로 마운트된다 → 파일 갱신 대신 Redis 저장.
- 기존 .NET 이 `PUT /api/settings/tools` 에 ToolSettings 전체를 보내므로 disabled_tools 를 같은 키에 넣으면 지워진다 → 별도 키.
