# 데스크톱 페이지별 필요 사항

EdgeVoice Agent 데스크톱(Avalonia, `src/EdgeVoice.Agent.Desktop`)의 6개 페이지가 무엇을 보여 주고 어디서 데이터를 가져오는지 정리한다.
화면 정의는 `MainWindow.axaml`, 동작은 `ViewModels/*ViewModel.cs`.

공통 디자인(Office / Fluent 2, 라이트·다크)
- 토큰: `App.axaml` 의 `Office*Brush` (캔버스·카드·선·보조 글자·강조·오류·경고). 글자 대비 4.5:1 이상(`PageConsistencyScenarioTests.디자인_토큰의_글자_대비가_4_5_대_1_이상이다`).
- 제목 `TextBlock.title`, 카드 `Border.card`(8px 모서리), 카드 제목 `TextBlock.cardTitle`, 도움말 `TextBlock.help`, 빈 상태 `TextBlock.empty`, 상태줄 `TextBlock.status`.
- 버튼: 주 버튼 `Classes="accent"`(파랑), 보조 버튼은 기본(회색). 표 머리글은 `DataGridColumnHeader` 공통 스타일(SemiBold·보조 글자색).
- 오류는 화면 아래 상태줄에 `오류: <HTTP 코드> <메시지>` 로 보인다(`PageViewModel.RunAsync`).

## Dashboard
- 목적: 서비스 상태와 시스템 자원을 한눈에.
- 표시: Orchestrator 상태·GPU·활성 세션·문서 수 KPI, GPU 사용률 추이, 서비스 상태 파이, 로그 레벨·서비스별 건수, 서비스 표.
- 출처: `GET /api/dashboard/init`, `GET /api/status/stream`(SSE), `GET /api/logs/stats`.
- 조작: 새로고침.
- 빈 상태: 서비스 표가 비면 "서비스 상태가 아직 없습니다. 백엔드에 연결되면 자동으로 채워집니다."
- 오류 상태: 상태줄에 오류, 앱 바에 "Some Services Offline".

## Chat
- 목적: 텍스트·음성(Hey Jarvis) 대화를 한 세션으로.
- 표시: 역할·말풍선, 음성 턴 표시(🎙 음성), RAG 출처(Sources).
- 출처: `POST /api/chat/message`(SSE: token·rag_context·complete·error), 활성 세션 히스토리.
- 조작: 입력+Enter/전송, RAG 사용 체크, 상시 마이크 음소거 토글, 새 대화.
- 빈 상태: "Hey Jarvis 라고 부르거나 메시지를 입력하세요"
- 오류 상태: 응답 말풍선에 `Error: <내용>`.

## Knowledge
- 목적: RAG 문서 관리.
- 표시: 파일명, 조각 수 | 업로드 시각, 지원 형식(.txt .md .pdf .docx .ppt .pptx).
- 출처: `GET /api/knowledge/documents`(`doc_id`·`chunk_count`·`uploaded_at`), `POST /api/knowledge/upload`(`chunk_count`), `DELETE /api/knowledge/documents/{doc_id}`.
- 조작: 문서 업로드(여러 개), 새로고침, 삭제(확인 대화상자).
- 빈 상태: "등록된 문서가 없습니다. '문서 업로드...' 로 추가하면 채팅의 RAG 답변에 쓰입니다."
- 오류 상태: 업로드마다 진행(`업로드 중 (1/2)`)과 결과(`성공(N개 조각)` / `실패: 사유`)를 상태줄에.

## Settings
- 목적: 실행 중인 구성을 보고 바꾼다. 콤보박스 선택값 = 실행 중인 서비스 값.
- 표시(2단 카드): 음성 인식(STT 모델·호출어·민감도·무음·제한 시간) · 답변 음성(엔진·엔진별 음성·속도) · 언어 모델(받아 둔 LLM 만) · 대화(컨텍스트) · 일반(언어: 한국어/English/日本語).
- 출처: `GET /api/settings/options` — `current`=실행 값(vLLM `/v1/models`, stt·tts·wake-word `/info`), `saved`=저장값, `runtime`=응답한 서비스의 실행 값, `pending_restart`, `tts_voices`(엔진별). `GET/PUT /api/settings/general`, `GET/PUT /api/settings/llm/context`, `GET/PUT /api/settings/tools`, `PUT /api/settings/mcp/{name}`, `PUT /api/settings/skills`, `POST /api/settings/apply`(바꾼 종류만), `POST /api/services/{llm|stt|tts}/restart`.
- 조작: 화면 아래 저장 막대 하나 — '저장하지 않은 변경 n개' + [저장] [되돌리기]. 저장하면 항목마다 '바로 반영됨 / 다음 질문부터 / 다시 시작해야 반영됨' 을 보이고, 모델을 바꿨으면 '○○을(를) 다시 시작합니다(약 N초)' + [다시 시작] [나중에]. 다시 시작은 백엔드가 못 하면(503) 이 PC 의 docker 로 같은 compose 프로젝트를 다시 만들고, 실행 값이 저장값과 같아지면 '반영됨'. MCP·스킬의 '추가'·'삭제' 는 바로 저장.
- 빈 상태: 없음(실행 값이 목록에 없으면 "(실행 중)" 항목을 붙여 콤보박스가 비지 않게 함).
- 오류 상태: 저장값≠실행값이면 "다시 시작 후 적용: 항목(저장 X · 실행 Y)" 배지, 실패는 상태줄.

## History
- 목적: 모든 세션의 질문·응답 기록.
- 표시: 시간·질문(음성이면 🎙)·응답.
- 출처: `GET /api/history?limit=500` (`messages`).
- 조작: 새로고침.
- 빈 상태: "아직 대화 기록이 없습니다. 채팅이나 음성(Hey Jarvis)으로 나눈 대화가 여기에 쌓입니다."
- 오류 상태: 상태줄.

## Logs
- 목적: 파이프라인 로그 조회·실시간 보기.
- 표시: Time(HH:mm:ss.fff)·Level(색 구분: ERROR 빨강, WARNING 주황, DEBUG 흐림)·Service·Stage·Message·Duration, 통계.
- 출처: `GET /api/logs?limit=100&min_level=INFO|level=..&service=..`, `GET /api/logs/stream`(SSE, 같은 필터), `GET /api/logs/stats`.
- 조작: 서비스(기본 "전체 서비스")·레벨(기본 "INFO 이상", "전체(DEBUG 포함)" 로 고빈도 DEBUG 보기) 필터, 조회, Live 토글, 지우기, 통계 새로고침.
- 빈 상태: "표시할 로그가 없습니다. 필터를 '전체' 로 바꾸거나 Live 를 켜 두세요."
- 오류 상태: "로그 스트림 오류(5초 후 재연결)".

## 시나리오 테스트
- 헤드리스(가짜 백엔드): `tests/EdgeVoice.Agent.Desktop.Tests/PageConsistencyScenarioTests.cs`, `PageScenarioTests.cs` — 라이트·다크 페이지 스크린샷은 `bin/.../screenshots/page-*.png`.
- 헤디드(실제 창·실제 백엔드, `EDGEVOICE_HEADED=1`): `tests/EdgeVoice.Agent.Desktop.HeadedTests/PageConsistencyHeadedTests.cs`.
- 실제 스택 API 점검(스택 없으면 skip): `tests/scenarios/test_pages_live.py` (저장소 루트에서 `python -m pytest tests/scenarios -v`).
