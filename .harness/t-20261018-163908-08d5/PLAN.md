# 설정 탭 '저장 막대' + 저장 결과 안내 + 다시 시작 흐름

## 목표
설정 탭의 흩어진 저장 버튼을 화면 아래 늘 보이는 저장 막대 하나로 모은다.
- 바뀐 항목 수 표시 + [저장] [되돌리기], 모든 카드의 바뀐 값을 한 번에 저장
- 저장 직후 항목별 '바로 반영됨 / 다음 질문부터 / 다시 시작해야 반영됨' 안내
- 다시 시작이 필요한 항목은 '○○을(를) 다시 시작합니다(약 N초)' + [다시 시작] → 끝나면 '반영됨'
- 앱을 열 때 저장된 값으로 채우고, 불러오기만으로는 '바뀐 항목' 이 생기지 않는다

## 설계
- VM(SettingsViewModel.Save.cs): 추적 항목 표(키·이름·현재값·반영 방식) → 서버에서 마지막으로 받은 값(_saved)과 비교해 바뀐 항목 계산.
  그룹(general·models·context·tools·mcp·skill·mcp-edit·prompt-edit)별로 서버 응답을 받을 때 기준값을 갱신한다.
- 저장: 바뀐 그룹만 해당 API 로 보낸다(general PUT · apply POST(바뀐 종류만) · llm/context PUT · tools PUT · mcp/{name} PUT · skills PUT).
- 다시 시작: 백엔드 `POST /api/services/{llm|stt|tts}/restart`(기존 LLM 재생성 방식 일반화).
  백엔드가 못 하면(503) 백엔드가 이 PC 의 docker 에서 돌고 있을 때 앱이 호스트에서 같은 compose 명령을 실행한다(HostCompose).
  끝나면 /api/settings/options 의 runtime 이 저장값과 같아질 때까지 확인 → '반영됨'.
- 백엔드: options 응답에 runtime 추가, STT 모델을 compose 가 읽는 STT_MODEL 로도 .env 에 쓴다(시작 때 동기화에서는 제외).

## 진행
- [x] 조사 (MainWindow.axaml Settings 탭, SettingsViewModel*, routes/settings.py, compose)
- [x] 백엔드 테스트 → 구현 (restart 일반화 `/api/services/{llm|stt|tts}/restart`, options.runtime, STT_MODEL)
- [x] .NET 시나리오 테스트(SettingsSaveScenarioTests 9개) → 구현 (SettingsViewModel.Save.cs, HostCompose.cs)
- [x] XAML: 저장 막대(SaveBar), 카드별 저장 버튼 제거, 안내 문구
- [x] 기존 테스트 수정(SaveGeneralCommand 등 → SaveCommand, MCP·스킬 체크는 저장 막대로), 헤디드 테스트 빌드 확인
- [x] ruff(바꾼 파일 오류 수 기준치와 같음), pytest, dotnet test, 헤드리스 화면 캡처로 눈 확인

## 발견
- 백엔드 컨테이너에는 docker CLI·COMPOSE_PROJECT_DIR 가 없어 기존 LLM 재생성은 늘 503(명령 안내)이다. Windows 호스트 경로라 컨테이너 안 compose 로는 바른 바인드 마운트를 만들 수 없다.
- compose 의 stt 는 `MODEL_SIZE=${STT_MODEL:-...}` 를 읽는데 env_writer 는 STT_MODEL_SIZE 만 썼다 → 다시 만들어도 STT 모델이 안 바뀌었다.
- 실제 스택: 저장 llm qwen2.5-7b · 실행 qwen3.5-9b, 저장 stt medium · 실행 small (오래된 저장값). 그래서 '다시 시작' 제안은 방금 저장한 항목에만 한다.
- 앱 재시작이 필요한 설정은 설정 탭에 없다(백엔드 주소 등은 설정 탭에 없음).

- TTS 음성은 compose 가 읽지 않고(TTS_VOICE 미전달) 오케스트레이터가 요청마다 보낸다 → '답변 음성' 은 다시 시작해도 바뀌지 않을 수 있다(반영 확인은 tts_engine 으로만 한다).
- 하네스가 `docker compose -p` 를 막아 HostCompose 가 만들 명령을 실제 프로젝트로 `config` 검증하지는 못했다. 라벨 조회(`docker ps --filter publish=11000`)는 ev-backend → aiagent·폴더·compose 파일을 바르게 돌려준다.
- tests/backend 의 기존 실패 3건(test_chat router·postgres 이미지·chat_context)은 이번 변경과 무관.

## 남은 일
- 실제 스택에서 저장 막대로 모델을 바꿔 다시 시작해 보는 확인(메인 체크아웃 컨테이너는 건드리지 않아 하지 않았다).
