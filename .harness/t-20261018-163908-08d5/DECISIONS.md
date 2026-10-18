# 결정 기록

## 1. 다시 시작은 누가 실행하나 (백엔드 vs 데스크톱 앱)
- options: (a) 백엔드 API 만(기존 LLM 재생성처럼, 지금 compose 에서는 늘 503 + 명령 안내) · (b) 데스크톱 앱만 호스트에서 docker compose 실행 · (c) 백엔드 API 를 먼저 부르고, 503 이면 백엔드가 이 PC 의 docker 에서 돌 때 앱이 호스트에서 같은 compose 명령 실행
- chosen: (c)
- why: 사양은 백엔드 API 를 요구하지만, 백엔드 컨테이너에는 docker CLI·프로젝트 폴더가 없고 Windows 경로라 컨테이너 안 compose 로는 바른 마운트를 만들 수 없다. 그대로면 버튼이 늘 실패한다. 앱은 같은 PC 에 있으므로 백엔드 포트를 publish 한 컨테이너의 compose 라벨(project·working_dir·config_files)로 같은 프로젝트를 정확히 다시 만든다. 백엔드 포트를 가진 컨테이너가 없으면(가짜 백엔드·원격) 아무것도 실행하지 않는다.
- effect: `HostCompose.RestartAsync` 를 쓰지 않으려면 SettingsViewModel.HostRestart 를 null 로 두면 된다(그러면 503 안내만 보인다).

## 2. 다시 시작 제안 대상
- options: (a) 서버가 알려 주는 pending_restart(저장값≠실행값) 전부 · (b) 방금 저장한 항목 중 다시 시작이 필요한 것만
- chosen: (b)
- why: 실제 스택은 오래된 저장값(LLM qwen2.5-7b, STT medium)이 실행값과 달라 (a)면 열 때마다 원치 않는 재시작을 권한다. LLM 은 .env 가 단일 출처라 다시 만들어도 바뀌지 않는다. 기존 '다시 시작 후 적용' 배지는 정보로 그대로 둔다.
- effect: SettingsViewModel.Save.cs 의 RestartPrompt 를 저장 결과에서만 채운다. (a)로 바꾸려면 LoadOptions 의 pending_restart 로도 채우면 된다.

## 3. 화면 콤보박스 값(실행값 vs 저장값)
- options: (a) 지금처럼 실행 중인 값 + 다르면 배지 · (b) 저장값
- chosen: (a)
- why: 이전 작업에서 사용자가 정한 동작(테스트 있음)이고, 저장값은 배지('저장 medium · 실행 small')로 보인다. 일반·대화·도구·MCP·스킬은 저장값으로 채운다.
- effect: 바꾸려면 LoadOptions 에서 current 대신 saved 를 쓰면 된다.

## 4. 반영 방식 분류
- options: 항목별 고정 분류 vs 서버 응답 기반
- chosen: 고정 분류 + 일반 설정은 서버의 전파 결과(propagation_results)로 보정
- why: 바로 반영됨 = 호출어·민감도·무음·제한 시간·말하기 속도·언어(서비스에 바로 전파), 다음 질문부터 = 대화·도구·지역·시간·MCP·스킬(턴마다 읽음), 다시 시작해야 반영됨 = LLM 모델(llm)·STT 모델(stt)·TTS 엔진·음성(tts). 전파에 실패한 서비스 항목은 '저장됨 · 서비스가 다시 시작되면 반영' 으로 보인다.
- effect: SettingsViewModel.Save.cs 의 Tracked() 표에서 바꾼다.

## 5. STT 모델이 다시 만들 때 반영되게
- options: (a) compose 를 STT_MODEL_SIZE 를 읽게 바꾸기 · (b) .env 에 compose 가 읽는 STT_MODEL 도 쓰기(apply 때만)
- chosen: (b)
- why: (a)는 compose 설정이 바뀌어 다음 `docker compose up -d` 때 실제 스택의 STT 가 오래된 저장값(medium)으로 바뀐다. (b)는 사용자가 STT 모델을 저장할 때만 쓰인다(시작 때 .env 동기화에서는 LLM 모델처럼 뺀다).
- effect: env_writer.SETTINGS_ENV_MAP["stt"]["model"] 와 get_current_settings_as_dict.

## 6. 앱 재시작
- options: 앱 재시작 흐름 추가 vs 없음
- chosen: 없음
- why: 설정 탭에 앱을 다시 띄워야 하는 설정이 없다(백엔드 주소 등은 설정 탭에 없다).
- effect: 생기면 AppRestart.Restart 를 저장 결과의 '앱 다시 시작' 항목에서 부르면 된다.

## 7. 카드별 버튼 정리
- options: 모두 제거 vs 저장 성격만 제거
- chosen: 저장 버튼(일반·도구·지역·시간·컨텍스트 저장, 모델 적용, 고른 서버/스킬 저장, 호출어 바로 바꾸기, LLM 다시 만들기)은 없애고 저장 막대로. MCP·스킬의 '추가'·'삭제'·'연결 상태 새로고침' 은 목록 편집 동작이라 그대로 둔다. MCP·스킬 체크박스도 바로 저장하지 않고 저장 막대로 모은다.
- why: 사양 1 의 '모든 카드의 바뀐 값을 한 번에 저장'.
- effect: MainWindow.axaml Settings 탭.
