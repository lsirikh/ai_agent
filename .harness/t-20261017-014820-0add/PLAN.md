# PLAN — 페이지별 점검 결과와 설정 콤보박스 정합성

명세: `C:\workspace_python\AI agent\docs\prds\2026-10-17-페이지별-점검-결과와-설정-콤보박스-정합성.md`

## 목표
- 설정 콤보박스 선택값 = 실제 실행 값(R1·R2), 정직한 UI(재시작 불가 시 실패 반환)
- Knowledge 조각 수·업로드 시각(R3), Logs 기본 "전체"/"INFO 이상"·열 폭(R4)
- 전 페이지 Office 디자인·빈 상태 문구(R5), 페이지별 필요 사항 문서(R6)
- 실제 스택 점검 스크립트 `tests/scenarios/test_pages_live.py`(스택 없으면 skip)

## 진행
- [x] 백엔드 settings: `read_runtime_settings`, options.current = 실행 값 + saved·pending_restart·tts_voices, 받아 둔 LLM 만, apply 검증(LLM·엔진별 음성·stt model 일치), restart 503, 시작 시 .env 에 llm.model 덮어쓰기 중단
- [x] 백엔드 knowledge: chunk_count·uploaded_at(rag 목록에 uploaded_at 추가), 업로드 실패 사유 전달
- [x] 백엔드 logs: min_level 필터(목록·스트림)
- [x] compose: 백엔드에 models/llm/hub 읽기 전용 마운트 + LLM_MODELS_HUB_DIR
- [x] 데스크톱 Settings: 2단 카드(음성 인식·답변 음성·언어 모델·대화·일반), 표시 이름, 배지, 엔진별 음성, "(실행 중)" 항목
- [x] 데스크톱 Knowledge/Logs/Chat/History/Dashboard: 빈 상태, 열 폭, 기본 필터, 레벨 색, 업로드 진행·결과, doc_id
- [x] 토큰: 오류·경고 색 추가, 다크 강조 글자 #73B4F7(선택 항목 위 대비 4.5:1)
- [x] 테스트: `tests/backend/test_settings_runtime.py`, `PageConsistencyScenarioTests.cs`(헤드리스), `PageConsistencyHeadedTests.cs`(헤디드)
- [x] 라이브 시나리오 14건 통과(워크트리 백엔드를 로컬 :11100 으로 띄워 실제 서비스에 연결)
- [x] `clients/dotnet/PAGES.md` (docs/ 는 gitignore — DECISIONS 8)
- [x] 검사 명령 전부 실행

## 발견
- 실행 중 스택: backend :11000, stt :11001, tts :11002, llm :11003, wake-word :11005, rag :11006, postgres :25432, redis :26379
- 실행 중 컨테이너는 메인 체크아웃 코드 → 라이브 점검은 워크트리 백엔드를 로컬 uvicorn(:11100)으로 띄워 실행. 기존 컨테이너(:11000)에 돌리면 7건 실패(수정 전 결함 재현)
- 로컬 백엔드도 로그 구독자를 띄워 실행하는 동안 pipeline_logs 에 로그가 두 번 들어간다(몇 분치) — 다음엔 짧게 띄울 것
- Windows 에서 HF 캐시 snapshot 파일은 접근 불가 심볼릭 링크 → `os.path.lexists` 로 확인
- `tests/backend` 의 기존 실패 3건(`test_chat_router_exists`, `test_postgres_container_exists`, `test_no_import_references_to_settings_broadcaster`)은 이번 변경과 무관(FastAPI 버전·grep 부재·docker 이름)

## 남은 일
- 실제 컨테이너 반영은 사용자 몫: `docker compose -f docker-compose.dev.yml up -d --build backend rag`
