# PLAN — 통합 대화 세션·컨텍스트 관리 (PRD 단계 1·2)

명세: `C:\workspace_python\AI agent\docs\prds\2026-10-17-통합-대화-세션-컨텍스트-관리-도구-mcp.md`
범위: 단계 1(통합 대화·활성 세션)·단계 2(컨텍스트 관리). 단계 3·4(도구·MCP)는 구현하지 않고 설계만 아래에 남긴다.
분기점은 `DECISIONS.md`.

## 원인 진단(사용자 증상)
- "LLM 은 타는데 TTS 가 안 나온다": 음성 경로가 `max_tokens 2048` + vLLM `--max-model-len 4096`(실행 중 스택에서 확인) 이라
  메모리 컨텍스트가 쌓이면 프롬프트+출력이 4096 을 넘어 vLLM 이 400 → `llm_processing_error` → TTS 요청이 하나도 안 나감.
  → ContextBuilder 토큰 예산 + 음성 출력 512 + vLLM 16384 로 해결.
- "채팅과 음성이 연결 안 됨": 음성 턴이 DB 에 저장되지 않고 채팅 SSE 도 비어 있었음 → 활성 세션 + 저장 + Redis 발행 + SSE.

## 진행
- [x] 코드 조사(오케스트레이터·백엔드·데스크톱·compose)
- [x] `shared/context_builder.py` — 고정 순서 조립, 토큰 예산, `/tokenize` 확인, 요약 분할 (+ `tests/shared/test_context_builder.py`)
- [x] 오케스트레이터: `LLMClient` 예산·요약·RAG 를 사용자 메시지로, `BackendClient` URL·source 수정 + 활성 세션·컨텍스트,
      턴마다 활성 세션 히스토리로 답하고 user·assistant 를 `source='voice'` 로 저장 (+ `tests/orchestrator/test_unified_session.py`)
- [x] 백엔드: `services/conversation.py`(활성 세션·저장·발행·컨텍스트·롤링 요약), `/api/sessions/active`·`POST /api/sessions`·
      `/{id}/messages`·`/{id}/context`(Postgres), pipeline 메시지 저장, `/api/chat/stream` Redis 구독, `/api/history/*` Postgres,
      `SimpleLLMClient` HTTP 오류 → `LLMError`(빈 답 저장 안 함), `persistent_history` 비 UUID 고정 매핑,
      저장소 JSONB 문자열 파싱 버그 수정 (+ `tests/backend/test_unified_conversation.py`)
- [x] DB: `init.sql` 에 `session_summaries`, 시작 시 `ensure_schema()`
- [x] compose: vLLM `--max-model-len ${LLM_MAX_MODEL_LEN:-16384}`, 서비스에 `LLM_MAX_MODEL_LEN`, backend 에 `./shared` 마운트(dev·jetson)
- [x] 데스크톱: 활성 세션 히스토리 로드·`/api/chat/stream` 상시 구독·음성 표시 말풍선·"새 대화"·음소거 토글(트레이와 같은 `AlwaysOnMicrophone`)·
      History 가 `messages` 를 읽음 (+ `ChatSessionScenarioTests`, 헤디드 `UnifiedConversationHeadedTests`)
- [x] live 시험(`tests/integration/test_unified_conversation_live.py`, `EDGEVOICE_LIVE=1`)
- [x] 실제 Postgres 에서 새 SQL 검증(트랜잭션 롤백), 실제 vLLM `/tokenize` 형식·추정치 확인(추정 149 ≥ 실제 128)
- [ ] 하네스 검사 전체 + ruff (마지막 턴에 실행)

## 남은 일 / 사용자 몫
- 스택 재배포 필요: `docker compose -f docker-compose.dev.yml up -d --build backend orchestrator` + `llm` 재시작(16384 반영).
- 헤디드·live 시험은 재배포 뒤 `EDGEVOICE_HEADED=1` / `EDGEVOICE_LIVE=1` 로 실행.
- `services/backend/tests` 를 `services/backend` 에서 돌릴 때는 `PYTHONPATH=<repo root>` 가 필요(shared 모듈).

## 단계 3·4 설계 메모(이번엔 구현 안 함)
- 도구: vLLM `--enable-auto-tool-choice --tool-call-parser hermes --exclude-tools-when-tool-choice-none`.
  `ToolRegistry`(get_time 기본, web_search·web_fetch 토글) → ContextBuilder 의 시스템 다음 고정 위치(이름순 정렬)로 `tools` 전달.
  스트리밍 `delta.tool_calls` 조립, 왕복 최대 2~3회, 음성 경로는 `<tool_call>` 텍스트가 TTS 로 가지 않게.
- 검색: SearXNG(compose profile, 내부망) 기본, Tavily/Naver 선택. `web_fetch` 는 사설·루프백·메타데이터 차단, 2MB·10초.
- MCP: `mcp` SDK 클라이언트(stdio·streamable HTTP), 이름 `서버__도구`, 허용 목록·실행 전 확인, 결과는 구분자로 감싼 비신뢰 데이터.
- DB: `messages.role` 에 `tool` 추가 마이그레이션.
