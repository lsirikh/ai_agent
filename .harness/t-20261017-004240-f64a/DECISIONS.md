# DECISIONS

## 1. 활성 세션을 어디에 저장할까
- options: DB `settings` 테이블 키 / `sessions` 에 is_active 컬럼 추가(마이그레이션) / Redis 키
- chosen: DB `settings` 의 `active_session` 키(`{"session_id": ...}`), 읽을 때 `sessions` 와 JOIN 해 지워진 세션이면 새로 만든다
- why: PRD 가 재시작 유지 때문에 DB 를 권장. 기존 테이블이라 스키마 변경 없이 바로 동작
- effect: `SessionRepository.get_active/set_active` 두 곳만 바꾸면 다른 저장 위치로 옮길 수 있다

## 2. 끼어들기로 잘린 음성 답 처리
- options: 저장하지 않음 / `metadata.interrupted=true` 로 저장(messages 에 metadata 컬럼 추가 필요)
- chosen: 인식 문장(user)은 턴 시작 때 저장, 잘린 답(assistant)은 저장하지 않음
- why: PRD 가 둘 다 허용. messages 테이블에 metadata 컬럼이 없어 마이그레이션 없이 가능한 쪽
- effect: 히스토리에 user 가 연속으로 남을 수 있음(모델은 문제없음). 표시가 필요하면 컬럼 추가 후 `_process_llm_stream` 의 CancelledError 경로에서 저장

## 3. 채팅창 SSE 에서 어떤 메시지를 말풍선으로 붙일까
- options: 모든 저장 메시지 / 음성(source='voice')만
- chosen: 초기 `init` 히스토리는 전부, 실시간 `message` 이벤트는 음성만
- why: 텍스트 턴은 보낸 화면이 이미 스트리밍으로 그리고 있어 전부 붙이면 중복된다(채팅 SSE 응답에 메시지 ID 가 없어 중복 제거가 어렵다)
- effect: 다른 창에서 보낸 텍스트는 재연결(또는 앱 재시작) 때 히스토리로 보인다. 바꾸려면 `ChatViewModel.OnStoredMessage`

## 4. 토큰을 어떻게 셀까
- options: 매 턴 vLLM `/tokenize` / HF 토크나이저 의존성 추가 / 보수적 추정 + 필요할 때만 `/tokenize`
- chosen: UTF-8 바이트/3 추정으로 조립하고, 추정치가 입력 예산의 50% 를 넘을 때만 vLLM `/tokenize` 로 실제 수를 확인해 넘치면 줄여 다시 만든다(최대 3회). 서버 `max_model_len` 은 `/v1/models`·`/tokenize` 응답으로 갱신
- why: 짧은 대화에서는 왕복을 아끼고(음성 지연), 긴 대화에서는 실제 토크나이저 기준으로 400 을 막는다. 새 의존성 없음
- effect: `shared/context_builder.py` 의 `VERIFY_RATIO`·`estimate_tokens` 로 조정

## 5. 세션 요약은 어디서 돌릴까
- options: 오케스트레이터와 백엔드 각각 / 백엔드 한 곳
- chosen: 백엔드 한 곳 — 음성·텍스트 assistant 메시지가 저장될 때마다 비동기로 검사(같은 세션 동시 1개)
- why: 모든 메시지가 백엔드를 거쳐 저장되므로 한 곳이면 중복 요약이 없다. 요약 실패 시 ContextBuilder 의 잘라내기가 대체
- effect: 임계 75%·남길 비율 40% 는 `shared/context_builder.py` 상수

## 6. 시스템 메시지가 빈 경우
- options: 항상 시스템 메시지 보냄 / 시스템 프롬프트가 비어 있으면 생략
- chosen: 비어 있으면 생략, 대신 음성(`DEFAULT_VOICE_SYSTEM_PROMPT`)·채팅(고정 프롬프트) 경로는 항상 프롬프트를 준다
- why: 기존 테스트(`test_context_duplication`)가 프롬프트 없는 LLMClient 의 정확한 메시지 목록을 고정하고 있음. 실제 경로에서는 항상 시스템 메시지가 간다
- effect: 필요하면 `build_messages` 에서 빈 프롬프트일 때 기본 문구를 넣으면 된다

## 7. 명세와 어긋나는 기존 테스트 처리
- options: 테스트를 그대로 두고 실패 / 명세대로 바뀐 동작에 맞게 기대값만 수정
- chosen: 기대값만 수정(3곳, 모두 하네스 검사 대상 밖)
  - `services/orchestrator/tests/test_message_sync.py`: PRD 가 고치라고 한 틀린 URL(`/api/messages/pipeline`)을 기대 → 실제 경로로
  - `tests/backend/test_chat_rag.py`: RAG 가 시스템 프롬프트에 있어야 한다고 기대 → PRD R2.1(시스템에 섞지 않음)대로 `reference` 로
  - 데스크톱 `FakeBackend` 의 `/api/history` 응답을 실제 백엔드 형식(`messages`)으로, 헤디드 채팅 테스트는 히스토리가 먼저 채워지므로 "보낸 뒤 2개 늘어남"으로
- why: 명세가 명시적으로 바꾸라는 동작을 예전 값으로 고정한 테스트라 그대로 두면 명세를 지킬 수 없다
- effect: 각 테스트의 의도(경로 호출·RAG 전달·히스토리 표시·응답 스트리밍)는 그대로다

## 8. 백엔드 `app/models` 가 저장소에 없음
- options: gitignore 를 고쳐 models 를 추적 / 그대로 두고 로컬 시험용 스텁만 사용
- chosen: 건드리지 않음. 루트 `.gitignore` 의 `models/` 규칙 때문에 `services/backend/app/models/` 가 추적되지 않아 이 worktree 에는 없다(메인 체크아웃에는 있음). 백엔드 시험은 무시되는 로컬 스텁을 잠깐 만들어 돌렸다
- why: 범위 밖이고, 메인 체크아웃의 실제 파일과 충돌할 수 있다
- effect: 사용자가 `.gitignore` 에 `!services/backend/app/models/` 를 추가하면 정상 추적된다

## 9. 단계 3·4(도구·MCP)
- options: 인터페이스 자리까지 코드로 / 설계만 문서로
- chosen: 코드로 만들지 않고 PLAN.md 에 설계 메모만 — ContextBuilder 는 시스템 다음 고정 위치에 도구 스키마를 넣을 수 있는 순서로 짰다
- why: PRD 가 이번 범위 밖이라고 명시. 쓰지 않는 추상화를 만들지 않는다
- effect: 단계 3 작업 때 `build_messages` 에 정렬된 `tools` 를 추가하면 된다
