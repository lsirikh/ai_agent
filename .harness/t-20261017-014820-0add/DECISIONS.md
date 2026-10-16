# DECISIONS

## 1. 실행 값을 새 엔드포인트로 줄지, 기존 options 에 넣을지
- options: `GET /api/settings/runtime` 신설 / `GET /api/settings/options` 의 `current` 를 실행 값으로 채우기
- chosen: `options` 확장 — `current`=실행 값(서비스 무응답 항목은 저장값), `saved`=저장값, `pending_restart`, `tts_voices` 추가
- why: 데스크톱·웹 UI 가 이미 `options.current` 를 콤보 선택값으로 쓰므로 한 곳만 고치면 모든 화면이 맞는다
- effect: `current` 의 뜻이 "저장값"→"실행 값" 으로 바뀜. 저장값이 필요하면 `saved` 를 쓴다. 별도 엔드포인트가 필요하면 `read_runtime_settings()` 를 그대로 노출하면 된다

## 2. 엔진에 없는 TTS 음성(예: melo + ko-KR-SunHiNeural)을 무엇으로 보일지
- options: 서비스 `/info` 의 음성 문자열 그대로 / 엔진이 실제로 쓰는 음성(엔진 기본 음성)
- chosen: 엔진 기본 음성(`TTS_VOICES[engine][0]`, melo → KR)
- why: melo 는 음성 인자를 무시하고 KR 로만 말한다. 정직한 UI·"melo 면 목록 = [KR]" 기준과 맞는다
- effect: 저장할 때도 엔진에 없는 음성은 엔진 기본 음성으로 바뀐다(`apply`). 엔진별 음성 목록은 `settings.py` 의 `TTS_VOICES` (TTS 엔진 코드와 수동 동기화)

## 3. LLM 모델 설정의 단일 출처
- options: DB(기존, 시작 때 .env 덮어씀) / `.env` 의 `LLM_MODEL`(vLLM 이 실제로 읽는 값)
- chosen: `.env` 가 vLLM 의 출처, 화면 표시는 vLLM `/v1/models`. 시작 때 DB→.env 동기화에서 `llm.model` 을 뺐고, apply 는 받아 둔 모델만 저장(.env·DB)한다
- why: DB 에 남은 잘못된 모델이 백엔드 재시작마다 .env 를 덮어써 vLLM 이 기동하지 못하던 문제(S2b)
- effect: .env 를 손으로 고치면 그대로 유지된다. 예전처럼 DB 값으로 덮어쓰려면 `get_current_settings_as_dict()` 의 `exclude={"model"}` 를 지우면 된다

## 4. 받아 둔 LLM 판단과 폴더를 볼 수 없을 때
- options: hub 폴더 이름만 / `models--org--name/snapshots/*/config.json` 존재 / 볼 수 없으면 목록 비우기 vs 카탈로그 전체
- chosen: snapshot 의 `config.json` 링크 존재(심볼릭 링크는 따라가지 않음). 폴더를 볼 수 없으면 카탈로그 전체(확인 불가)
- why: 폴더만 남은 미완료 다운로드를 거른다. 단위 테스트·폴더 미마운트 환경에서 화면이 비지 않게 한다
- effect: compose 백엔드에 `models/llm/hub` 를 읽기 전용으로 마운트하고 `LLM_MODELS_HUB_DIR` 를 넣었다 (반영하려면 `docker compose up -d backend`)

## 5. "LLM 재시작" 을 어떻게 정직하게 만들지
- options: docker CLI 가 있으면 현재 폴더에서 실행 / `COMPOSE_PROJECT_DIR` 를 준 환경에서만 `docker compose up -d llm` 실행, 아니면 503
- chosen: 후자. 실패(설정 없음·docker 없음·시간 초과·비정상 종료)는 503 + `status=failed` + 직접 실행할 명령
- why: 컨테이너에는 docker 가 없고, 호스트에서 테스트할 때 엉뚱한 폴더로 새 compose 프로젝트(두 번째 vLLM)를 만들 위험이 있다. restart 는 .env 를 다시 읽지 않아 `up -d` 가 맞다
- effect: 실제 재생성을 원하면 백엔드 환경에 `COMPOSE_PROJECT_DIR`(compose 파일 폴더)와 docker CLI 를 넣는다

## 6. 웨이크워드 임계값의 단일 출처
- options: 저장값 표시 / 서비스 실제값 표시 + 저장 시 서비스 반영
- chosen: 명세의 "열린 질문" 대로 서비스 실제값(`/info settings.threshold`)을 표시, "일반 설정 저장" 은 기존대로 서비스에 전파
- why: 사용자 확인 전까지 실제 동작하는 값을 보여 주는 쪽이 정직하다
- effect: 저장값과 다르면 배지에 "호출어 민감도(저장 X · 실행 Y)". 기준값(0.3/0.5)은 사용자가 정하면 compose `WAKE_WORD_THRESHOLD` 와 DB 를 같이 맞추면 된다

## 7. Logs 기본 "INFO 이상" 구현
- options: 클라이언트에서 DEBUG 거르기 / 백엔드 `min_level` 쿼리
- chosen: 백엔드 `GET /api/logs?min_level=INFO` (스트림도 같은 파라미터)
- why: 클라이언트에서 거르면 100건 중 64건이 DEBUG 라 보이는 로그가 크게 줄어든다
- effect: 레벨 콤보 "전체(DEBUG 포함)" 이 고빈도 DEBUG 보기 토글 역할

## 8. 페이지별 필요 사항 문서 위치
- options: `docs/` (명세 제안) / 추적되는 다른 위치
- chosen: `clients/dotnet/PAGES.md`
- why: 저장소 `.gitignore` 가 모든 `docs/` 를 무시해 `docs/` 아래에 두면 커밋되지 않는다
- effect: `docs/` 로 옮기려면 `.gitignore` 의 `docs/` 예외를 추가하거나 사용자 docs 폴더에 복사

## 9. Knowledge "조각 수" 표기
- options: "N개 조각" 으로 바꾸기 / 기존 "N chunks | 시각" 유지
- chosen: 기존 형식 유지, 열 머리글만 "조각 수 | 업로드 시각"
- why: 기존 시나리오 테스트가 "12 chunks" 형식을 검사한다(기존 테스트를 고치지 않는다)
- effect: 표기를 바꾸려면 `KnowledgeViewModel.Refresh` 와 `PageScenarioTests` 를 함께 바꾼다
