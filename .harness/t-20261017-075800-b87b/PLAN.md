# PLAN — 단계 3(도구 호출·인터넷 검색)·단계 4(MCP 클라이언트)

명세: `C:\workspace_python\AI agent\docs\prds\2026-10-17-통합-대화-세션-컨텍스트-관리-도구-mcp.md` (단계 3·4, 완료 기준 (a)~(j))
+ 목표 문장: 지식베이스에 가상 위키 데이터를 넣어 시험하고 삭제.

## 설계 (구현됨)
- `shared/tools.py` — Tool/ToolRegistry(이름순 스키마, 실패는 오류 결과로), get_time(기본),
  web_search·web_fetch(설정 토글 + 제공자 있을 때만), 제공자 SearXNG/Tavily/Naver,
  web_fetch SSRF 방어(http(s)만, DNS 해석 후 비공인 주소·점 없는 호스트·localhost 거부, 리다이렉트마다 재검사,
  text/html·text/plain, 2MB, 10초, trafilatura 추출, 토큰 예산으로 자름), 도구 설정(Redis `edgevoice:settings:tools`),
  `tool_parser_for(model)`.
- `shared/tool_calling.py` — 스트리밍 tool_calls 조립기, `<tool_call>` 텍스트 가드, 도구 왕복 루프
  (`stream_with_tools`: 최대 3회 후 도구 없이 최종 답, 예산 부족 시 도구 끔, 결과를 신뢰하지 않는 데이터 구분자로 감쌈,
  확인 필요 도구는 confirm 콜백이 True 일 때만 실행). 답 텍스트(str)와 도구 이벤트(dict)를 섞어 내보냄.
- `shared/mcp_client.py` — MCP SDK 2.3 `Client`(stdio·streamable HTTP), 설정 파일(`MCP_CONFIG_PATH`),
  서버별 전용 태스크로 연결 유지, 페이지네이션, list_changed → 재조회, `서버__도구` 이름 정리·역매핑,
  허용 목록, 확인 정책(신뢰 서버의 read-only 만 바로 실행, destructive·always_confirm 은 항상 확인), 시간 제한, 감사 로그.
- 오케스트레이터: `LLMClient.generate_stream(tools=, confirm=)`, 400 이면 도구 없이 재요청.
  음성 턴에서 도구 안내 음성("검색해 볼게요."), 결과는 TTS 로 보내지 않고 role='tool' 로 저장, 출처는 답에.
  확인 필요 도구는 다음 턴 예/아니오. MCP 는 main.py lifespan 에서 연결.
- 백엔드: `SimpleLLMClient` 같은 구조, `ChatService(tool_provider=)` → SSE `tool_call`/`tool_confirm`/`tool_result`,
  `POST /api/chat/confirm`, `GET/PUT /api/settings/tools`, 파이프라인 메시지 role='tool'+metadata.sources,
  DB `messages.role` 에 `tool`(init.sql + 시작 시 마이그레이션), 컨텍스트·요약에서 tool 행 제외.
- compose: vLLM `--enable-auto-tool-choice --tool-call-parser hermes --exclude-tools-when-tool-choice-none`,
  SearXNG `profiles: [search]`(포트 미공개, json·ko·naver: `config/searxng/settings.yml`), 도구 env, `config/mcp` 마운트.
- 데스크톱: 채팅 답에 "🔎 검색함 · 출처" 링크, tool 행은 말풍선 아님, tool_confirm → 확인 창 → confirm API,
  설정 화면 "도구 (인터넷 검색)" 토글.

## 진행
- [x] shared 모듈 3개 + 시험용 MCP 서버(`tests/shared/mcp_test_server.py`)
- [x] 오케스트레이터 연결 + `tests/orchestrator/test_voice_tools.py` ((a)(b)(c)(g)(h)(i), 음성 확인)
- [x] 백엔드 연결 + `tests/backend/test_chat_tools.py` (채팅 왕복·저장·확인·400·설정 API)
- [x] `tests/shared/test_tools.py` (d)(g)(b), `test_tool_calling.py` (c)(a), `test_mcp_client.py` (e)(f)
- [x] DB 마이그레이션, compose, 요구사항(mcp·trafilatura)
- [x] 데스크톱 채팅·설정 + 시나리오 테스트 2개
- [x] live: ev-llm 재생성 후 `tests/integration/test_tools_live.py` 3개 통과 (j), 기존 live 통합 대화 2개 통과
- [x] live: 가상 위키 지식 베이스 시험 통과 → 이후 master 의 `tests/scenarios/test_knowledge_live.py` 와 중복이라 삭제(DECISIONS 12)
- [x] 줄바꿈을 7c542df(LF)에 맞춤, ruff 가 건드린 관계없는 파일 복원(DECISIONS 10)
- [x] master(9bd0e8d) 변경을 파일 내용으로 들여옴, 오케스트레이터 충돌 1곳 해결(음성 RAG + 도구)(DECISIONS 11)
- [x] 실제 스택은 다시 만들지 않음 — live 는 떠 있는 vLLM 에 요청만(DECISIONS 8)
- [x] SearXNG 설정을 임시 컨테이너로 확인(naver 결과 JSON), 실제 검색·web_fetch 왕복 확인 후 컨테이너 정리

## 발견
- Wikimedia 는 httpx 요청을 UA 와 무관하게 403(봇 정책) — web_fetch 는 오류 결과로 돌려주고 답은 계속된다.
- 로컬 호스트의 Redis 는 26379(ev-redis). live 시험은 `EDGEVOICE_REDIS_PORT=26379` 필요.
- tests/backend 의 `test_chat_router_exists`(FastAPI `_IncludedRouter`)·`test_postgres_container_exists` 는 이 변경 전부터 실패.

## 남은 일 (사용자)
- 병합 후 backend·orchestrator 이미지 재빌드(새 의존성·코드 반영).
- 인터넷 검색을 쓰려면 SearXNG profile 기동 + `SEARXNG_URL` 설정(또는 Naver/Tavily 키) 후 설정 토글.
- Ironwall.Monitoring MCP 서버가 생기면 `MCP_CONFIG_PATH` 로 서버 목록 지정(`config/mcp/servers.example.json`).
