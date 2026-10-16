# DECISIONS

## 1. 인터넷 도구 설정(토글)을 어디에 저장하나
- options: (a) 기존 settings DB + 설정 전파(propagator) 로 각 서비스에 push, (b) Redis 키 `edgevoice:settings:tools` 를 두 서비스가 턴마다 읽음, (c) 환경변수만
- chosen: (b) Redis 키 + 없으면 환경변수(`INTERNET_TOOLS_ENABLED`, 기본 false) 기본값
- why: 음성(오케스트레이터)·채팅(백엔드)이 같은 값을 다음 턴부터 바로 쓰고, 전파 실패·재시작 순서 문제가 없다. Redis 는 appendonly 라 재시작해도 남는다.
- effect: `PUT /api/settings/tools` 와 데스크톱 설정 화면 "도구 (인터넷 검색)" 카드가 이 키를 바꾼다. DB 영속이 필요해지면 `shared/tools.py` 의 `load_tool_settings` 와 settings 라우트만 바꾸면 된다.

## 2. 검색 제공자 기본값과 "제공자 미설정" 판단
- options: (a) SEARXNG_URL 기본값을 `http://searxng:8080` 로 둠, (b) 비워 두고 사용자가 search profile 을 켤 때 설정
- chosen: (b) compose 의 `SEARXNG_URL` 기본값은 빈 값. 제공자(SearXNG/Tavily/Naver)의 주소·키가 없으면 web_search·web_fetch 둘 다 노출하지 않는다.
- why: SearXNG 는 `profiles: [search]` 선택 서비스라 기본으로는 떠 있지 않다. 기본값을 넣으면 토글만 켜도 없는 서버를 부르는 도구가 노출된다. 명세 열린 질문(SearXNG vs Naver 키)은 사용자 확정 전이라 둘 다 지원하고 기본 이름만 searxng.
- effect: 인터넷 검색을 쓰려면 `docker compose --profile search up -d searxng` + `.env` 에 `SEARXNG_URL=http://searxng:8080` (또는 `SEARCH_PROVIDER=naver` + `NAVER_CLIENT_ID/SECRET`, `tavily` + `TAVILY_API_KEY`) 후 설정 토글을 켠다.

## 3. 파서가 없는 모델 판단
- options: (a) 모델 이름 → 파서 표(Qwen2.5/Qwen3/Hermes → hermes), (b) vLLM 에 물어보기(API 없음), (c) 400 을 받으면 끄기
- chosen: (a) + (c) 둘 다. 모르는 모델이면 도구를 아예 보내지 않고, 알려진 모델이어도 vLLM 이 도구 요청을 400 으로 거절하면 도구 없이 다시 요청하고 그 클라이언트에서는 도구를 끈다. `LLM_TOOL_PARSER` 로 덮어쓸 수 있다("none" 이면 끔).
- why: 설정 화면에서 모델을 바꾸면 vLLM 플래그와 어긋날 수 있다 — 어느 쪽이 틀려도 사용자 답에 400 이 보이지 않게.
- effect: compose 의 vLLM 은 `--tool-call-parser hermes` 고정. 다른 계열 모델을 쓰면 `shared/tools.py` 의 `tool_parser_for` 와 compose 플래그를 함께 바꾼다.

## 4. 음성 "실행할까요?" 확인 흐름 (명세 열린 질문)
- options: (a) 같은 턴 안에서 다음 STT 를 기다림, (b) 도구를 실행하지 않고 기억해 둔 뒤 다음 음성 턴의 예/아니오로 결정
- chosen: (b) 확인이 필요한 도구는 실행하지 않고 모델에 "아직 승인 안 됨, 실행할지 물어보라" 결과를 준다 → 모델이 "재시작할까요?" 라고 말함. 다음 턴이 "네/예/응/그래/좋아/실행/해줘" 로 시작하면 실행해 결과로 답하고, "아니/아뇨/취소/하지 마/싫어" 면 "알겠어요, 실행하지 않을게요." 로 끝낸다. 그 밖의 말이면 확인을 버리고 보통 턴으로 처리.
- why: 음성 턴은 웨이크워드→STT 로 끊겨 있어 한 턴 안에서 기다리면 상태 머신이 막힌다.
- effect: 예/아니오 단어는 `services/orchestrator/app/orchestrator.py` 의 `YES_PATTERN`·`NO_PATTERN` 에서 바꾼다. 채팅은 `tool_confirm` SSE 이벤트 → 데스크톱 확인 창 → `POST /api/chat/confirm` (120초 안에 답이 없으면 실행 안 함).

## 5. 도구 결과 메시지의 저장·표시
- options: (a) role='tool' 행을 채팅 말풍선으로 띄움, (b) 행은 저장하되 말풍선은 띄우지 않고 답 말풍선에 "🔎 검색함 · 출처" 를 붙임
- chosen: (b). 도구 행은 `messages.role='tool'`(마이그레이션), `rag_sources=[{"tool","is_error"}, {"title","url"}...]` 로 저장한다. 프롬프트 컨텍스트·요약에서는 tool 행을 뺀다(답만 이어짐).
- why: 기존 헤디드 시험이 "텍스트 턴 = 말풍선 2개" 를 전제한다. 도구 결과 원문은 길고 신뢰하지 않는 데이터라 다음 턴 프롬프트에 다시 넣지 않는 편이 안전하고 예산도 아낀다.
- effect: 도구 원문 보기가 필요하면 `ChatViewModel.IsBubble` 만 바꾸면 된다.

## 6. 범위: 지식베이스 가상 데이터 시험
- options: (a) 이 작업 범위(단계 3·4) 밖이라 건너뜀, (b) 목표 문장에 있으므로 live 시나리오로 수행
- chosen: (b) `tests/integration/test_knowledge_live.py` — 가상 연예인 위키·가상 도시 위키 문서를 올려 검색·RAG 답을 확인하고, 끝나면(실패해도) 문서를 지운 뒤 지워졌는지 확인한다.
- why: 사용자가 직접 요청했고, 실제 스택에 흔적을 남기지 않는다.
- effect: `EDGEVOICE_LIVE=1` 일 때만 돈다.

## 7. live 검증을 위해 실행 중인 ev-llm 컨테이너를 새 플래그로 재생성
- options: (a) compose 만 고치고 재기동은 사용자에게 맡김, (b) 검증을 위해 재기동
- chosen: (b) `docker compose -p aiagent --project-directory "C:\workspace_python\AI agent" -f <worktree>/docker-compose.dev.yml up -d --no-deps llm` 로 ev-llm 만 재생성(`--enable-auto-tool-choice --tool-call-parser hermes --exclude-tools-when-tool-choice-none`).
- why: 완료 기준 (j) 가 실제 vLLM 왕복이다. 되돌릴 수 있고(같은 명령을 원래 compose 로), 도구 플래그는 도구를 보내지 않는 기존 요청에 영향이 없다(기존 live 시험 통과 확인).
- effect: 백엔드·오케스트레이터 컨테이너는 아직 옛 이미지라 도구를 쓰지 않는다. 병합 후 `docker compose -f docker-compose.dev.yml build backend orchestrator && up -d` 로 새 의존성(mcp·trafilatura)과 코드를 반영해야 한다.

## 8. 사용자 추가 지시 반영: 실제 스택을 다시 만들지 않음 · vLLM GPU 비율 유지
- options: (a) compose 의 vLLM 명령을 master 기준(`${LLM_GPU_UTIL:-0.6}`)으로 다시 써 넣음, (b) 이 브랜치는 `--port 11003` 뒤에 도구 플래그 3줄만 추가하고 `--gpu-memory-utilization` 줄은 건드리지 않음
- chosen: (b). 이 브랜치의 diff 는 플래그 3줄 추가뿐이라 master 와 병합하면 master 의 `${LLM_GPU_UTIL:-0.6}` 가 그대로 남는다(0.7 로 되돌리지 않음).
- why: 사용자 지시 — GPU 비율을 되돌리지 말 것. 다른 줄을 고치지 않아야 병합 충돌도 없다.
- effect: DECISIONS 7 의 ev-llm 재생성은 사용자 음성 대화를 1분 넘게 멈추게 했다(잘못된 판단). 이후로는 실제 스택(ev-*)을 재생성·재시작하지 않고, live 검증은 이미 떠 있는 vLLM(도구 플래그 켜짐)에 요청만 보낸다.

## 9. 백엔드 채팅 시스템 프롬프트 중복
- options: (a) ChatService 의 한국어 프롬프트 사본 유지, (b) `llm_client.LANGUAGE_PROMPTS["ko"]` 재사용
- chosen: (b) — 두 문자열이 글자 단위로 같아 사본을 지우고 상수를 쓴다(동작 동일).
- why: 하네스가 중복으로 지적. 한 곳만 고치면 두 경로가 같이 바뀐다.
- effect: 채팅 시스템 프롬프트를 바꾸려면 `services/backend/app/services/llm_client.py` 의 `LANGUAGE_PROMPTS["ko"]` 를 고친다.

## 10. 줄바꿈 복원 (사용자 추가 지시)
- options: (a) 바뀐 파일을 7c542df 의 줄바꿈으로 되돌림, (b) 그대로 둠
- chosen: (a). 7c542df 에서 바뀐 파일은 원래 모두 LF 였다 → 전부 LF 로 바꿨고(내용 그대로), 새 파일도 LF. 원인은 Windows 에서 Python 텍스트 모드 `open(..., "w")` 로 쓴 스크립트 편집(CRLF 로 저장됨).
- 함께 고친 것: 앞선 `ruff check --fix shared/` 가 이 작업과 관계없는 `shared/__init__.py`·`shared/pipeline_logger/*`·`tests/shared/test_pipeline_logger.py` 를 고쳤었다 → 7c542df 내용으로 되돌렸다.
- effect: 공백을 빼지 않은 diff 와 뺀 diff 가 거의 같아졌다(+3554/-106 vs +3545/-97, master 들여온 내용 포함). master 가 추가한 `.gitattributes`(소스 eol=lf)와도 맞는다.

## 11. master 들여오기 방법 — git 병합 대신 파일 내용으로
- options: (a) `git merge master` (하네스가 git 쓰기를 막음), (b) master 변경을 파일 내용으로 반영: master 만 바꾼 파일은 master 내용 그대로(LF), 양쪽이 바꾼 4개는 3-way 병합 결과, (c) 들여오지 않고 충돌 여부만 보고
- chosen: (b). `docker-compose.dev.yml`·`routes/settings.py`·`orchestrator/main.py` 는 충돌 없이 합쳐졌다. compose 는 master 의 `--gpu-memory-utilization ${LLM_GPU_UTIL:-0.6}` 와 STT GPU 설정을 그대로 두고 도구 플래그는 한 벌만 남는다.
- 실제 충돌 1곳: `services/orchestrator/app/orchestrator.py` 의 `_process_llm_stream` — master 의 음성 RAG(`knowledge = await self._relevant_knowledge(text)`, `rag_context=knowledge or None`)와 이 브랜치의 도구 인자(`tools=`, `confirm=`, 확인된 도구 결과)가 같은 `generate_stream(...)` 호출 줄을 고쳤다. 해결: 확인된 도구 결과가 없을 때만 도구 레지스트리를 만들고 지식 베이스 근거를 `rag_context` 로 붙인다(둘 다 유지).
- effect: 병합 기준점이 여전히 7c542df 라서 실제 `git merge master` 를 하면 이 한 곳은 다시 충돌로 표시된다. 그때는 이 브랜치 쪽(ours)을 고르면 된다 — master 의 음성 RAG 가 이미 들어 있다. 나머지 파일은 master 와 내용이 같거나 깔끔하게 합쳐진다. master 쪽 일부 blob(compose·settings.py·orchestrator 의 main.py/orchestrator.py 등)이 CRLF 로 커밋돼 있어, `.gitattributes` 재정규화 전이라면 `git merge -X ignore-space-at-eol` 이 필요할 수 있다.

## 12. 중복 지식 베이스 시험 제거
- options: (a) 이 브랜치의 `tests/integration/test_knowledge_live.py` 유지, (b) 삭제
- chosen: (b). master 의 `tests/scenarios/test_knowledge_live.py` 가 같은 시나리오(가상 위키 업로드 → 검색 → 채팅 답 → 삭제 → 삭제 후 미검색)를 더 넓게(가수·도시·드라마) 다룬다.
- effect: 지식 베이스 live 시험은 master 의 시나리오 하나만 남는다(이 브랜치에 들여옴).
