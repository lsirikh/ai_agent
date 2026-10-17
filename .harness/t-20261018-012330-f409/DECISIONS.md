# DECISIONS

## 1. MCP 서버 설정을 어디에 영구 저장할까
- options: servers.json 파일을 고쳐 쓴다 / Redis 에 저장한다(기존 도구 설정과 같은 방식) / Postgres settings 테이블
- chosen: Redis `edgevoice:settings:mcp` 에 서버 목록 전체를 저장. 한 번도 저장하지 않았으면 servers.json(MCP_CONFIG_PATH)을 처음 값으로 쓴다.
- why: servers.json 은 두 컨테이너에 `:ro` 로 마운트돼 있고 git 에 들어 있으며 다른 세션이 값을 바꾼다. 도구 설정이 이미 Redis(appendonly)로 두 서비스에 공유된다.
- effect: 설정 화면에서 한 번 저장하면 그 뒤로는 Redis 값이 이긴다(servers.json 을 고쳐도 반영 안 됨). 파일로 되돌리려면 Redis 키 `edgevoice:settings:mcp` 를 지우면 된다. 저장처를 바꾸려면 `load_mcp_servers`·`save` 한 곳만 고치면 된다.

## 2. 오케스트레이터(음성)는 MCP 설정 변경을 언제 반영할까
- options: Redis pub/sub 으로 즉시 알림 / 턴마다 저장된 설정과 비교해 바뀐 서버만 다시 연결
- chosen: 턴마다 비교(`MCPManager.apply`). 백엔드는 API 로 저장하자마자 바로 apply 해서 연결 상태를 돌려준다.
- why: 구독 루프 없이 두 서비스가 같은 코드로 맞춰진다. 바뀌지 않았으면 비교만 하고 끝난다.
- effect: 음성은 변경 뒤 첫 턴에 연결한다(그 턴이 연결 시간만큼 늦을 수 있음). 즉시가 필요하면 pub/sub 구독을 더하면 된다.

## 3. 서버 하나를 바꾸면 전체를 다시 연결할까
- options: 매니저 전체 재생성 / 바뀐 서버만 다시 연결
- chosen: 바뀐(추가·수정·켜짐) 서버만 연결하고 꺼지거나 지워진 서버만 닫는다.
- why: 데스크톱 서버를 끄는데 브라우저 MCP 세션(열린 페이지)이 끊기면 안 된다.
- effect: 같은 이름·같은 설정이면 기존 연결을 그대로 쓴다.

## 4. 스킬 API 모양
- options: 스킬마다 CRUD 엔드포인트 / `GET·PUT /api/settings/skills` 로 전체를 주고받기
- chosen: 전체 주고받기 `{"disabled_tools": [...], "prompts": [...]}`. MCP 는 요청에 적힌 대로 목록·추가·수정·삭제 엔드포인트.
- why: 스킬은 연결이 없는 순수 설정이라 전체 저장이 가장 단순하다.
- effect: 동시에 두 화면에서 고치면 나중 저장이 이긴다. 항목별 API 가 필요하면 같은 Redis 키 위에 더하면 된다.

## 5. 내장 스킬(도구) 끄기를 어디에 저장할까
- options: 기존 도구 설정 키에 `disabled_tools` 추가 / 스킬 키에 저장하고 `load_tool_settings` 가 합친다
- chosen: 스킬 키에 저장, `load_tool_settings` 가 합치고 `build_registry` 가 뺀다.
- why: 데스크톱 앱이 `PUT /api/settings/tools` 에 도구 설정 전체를 보내므로 같은 키에 두면 저장할 때마다 지워진다.
- effect: `/api/settings/tools` 의 `tools` 목록에도 꺼진 스킬은 빠진다.

## 6. 체크박스를 누르면 바로 저장할까
- options: 바로 저장 / '저장' 버튼
- chosen: 체크박스는 바로 저장(MCP 는 바로 다시 연결). 추가·수정은 편집 칸 + 버튼.
- why: "체크박스로 켜고 끄게" 요청 — 켠 즉시 반영되는 쪽이 기대에 맞다.
- effect: 바꾸려면 항목의 `Changed` 콜백 대신 저장 버튼을 두면 된다.

## 7. '사용하지 않음'으로 표시된 extensions.py 함수들을 지울까
- options: 지운다 / 그대로 둔다
- chosen: 그대로 둔다 — `get_mcp_servers`·`add_mcp_server`·`update_mcp_server`·`delete_mcp_server`·`get_skills`·`update_skills`, 그리고 `_needs_target`·`_unique_names`.
- why: 앞의 6개는 `@router.get/post/put/delete` 로 등록된 FastAPI 엔드포인트라서, 코드에서 이름으로 부르지 않고 HTTP 요청이 오면 FastAPI 가 부른다. 데스크톱 앱(`SettingsViewModel.Extensions.cs`)이 이 엔드포인트를 쓴다. 뒤의 2개는 `@model_validator`·`@field_validator` 로 등록된 pydantic 검증기로, 요청 본문을 검사할 때 pydantic 이 부른다. 정적 검사기는 데코레이터로 등록된 함수를 호출되지 않는 것으로 본다. 실제로 쓰인다는 것은 tests/backend/test_extension_settings.py 가 확인한다(엔드포인트 호출, 422 응답).
- effect: 지우면 설정 화면의 MCP·스킬 API 와 입력 검증이 사라진다.

## 8. 최신 master 를 어떻게 반영할까 (git merge 는 하네스가 막는다)
- options: BLOCKED 로 멈춘다 / 작업 트리에 master 내용을 옮기고 겹친 파일은 `git merge-file` 로 3-way 병합해 하네스가 일반 커밋으로 남기게 한다
- chosen: 뒤쪽. 기준점 6dca181, 대상 master 1a3649c.
- why: git 쓰기(merge·checkout) 없이 결과 내용을 master 위에 올린 것과 같게 만들 수 있다. 겹친 hunk 는 양쪽 모두 덧붙이는 변경이라 둘 다 살렸다.
- effect: 이 브랜치 이력에는 병합 커밋이 없고 master 내용이 일반 커밋으로 들어간다. accept 때 같은 줄 변경은 양쪽이 같아 깨끗이 합쳐질 것으로 보지만, 충돌이 나면 master 쪽 줄과 이 브랜치 줄이 같은지만 확인하면 된다.
