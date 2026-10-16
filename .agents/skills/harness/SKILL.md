---
name: harness
description: 무언가를 만들거나 고쳐 달라는 요청을 하네스 CLI(`node harness/cli.js go`)로 보내 자기 worktree 에서 끝까지 실행하고 보고를 전한다. 작업 결과 받아들이기(accept) · 취소(cancel) · 되살리기(restore) · 현황(status) 요청에도 쓴다.
---

# harness — 요청을 하네스로 보내는 길잡이

## 만들거나 고쳐 달라는 요청
1. 사용자 요청 **원문 그대로**를 임시 파일에 쓴다 — 셸 명령줄에 넣지 않는다(따옴표·`$(…)`·백틱이 셸에서 바뀌거나 실행된다).
   Claude Code 는 Write 도구로(예: 스크래치패드의 `harness-goal.txt`), Codex 는 파일 쓰기로. 고치거나 요약하지 않는다.
2. `node harness/cli.js go --detach --goal-file "<그 파일 경로>"` 를 실행한다 — 작업을 셸과 분리된 프로세스로 띄우고 id 를 바로 돌려준다(몇 초). `--detach` 를 빼지 않는다: 에이전트 셸에는 시간 상한(Claude Code 백그라운드 30분)이 있어 셸 안에서 돌린 작업은 함께 죽는다.
   사용자가 검사 명령을 줬으면 `--check "<명령>"` 으로 넘긴다. (파일을 쓸 수 없으면 `go -` 로 원문을 stdin 에 넘긴다.)
   사용자가 **이미지 · 영상 · 음성 · 문서**를 함께 줬으면 파일마다 `--attach "<경로>"` 를 붙인다. 대화창에 붙여 넣은 이미지는 메시지에 `[Image: source: <경로>]` 로 보이니 그 경로를 쓴다. 경로가 없는 이미지는 사용자에게 파일로 저장해 경로를 달라고 한 번 묻는다.
3. `node harness/cli.js wait <id>` 를 **백그라운드로** 실행하고(Claude Code: Bash `run_in_background: true`) 끝났다는 알림을 기다린다. 몇 분~몇십 분 걸린다. `wait` 가 셸 상한으로 끝나도 작업은 계속 돈다 — 그때는 `wait <id>` 를 다시 띄운다(종료 코드 3 = 아직 실행 중). 도는 동안 묻지 않는다.
4. 보고를 사용자의 언어로 전하고 멈춘다 — 맨 위의 `요약:` · `첨부:` · `다음:` · `주의:` 줄과 `결정 분기점:`(작업자가 묻지 않고 고른 갈림길 — 분기점 · 고른 것 · 이유 · 결과)은 그대로, 그 아래의 영어 세부 줄은 빠짐없이 사용자의 언어로 옮긴다(명령 · 경로 · 숫자 · 브랜치 이름은 원문 그대로). 줄이거나 판단을 덧붙이지 않는다.

## 받아들이기 · 취소 · 되살리기
- 사용자가 결과를 받아들인다고 **명시적으로** 말했을 때만: `node harness/cli.js accept <id>`
- 사용자가 취소를 원하면: `node harness/cli.js cancel <id>` · 취소한 병합을 되살리려면: `node harness/cli.js restore <id>`
- 실행 중인 작업을 멈추려면: `node harness/cli.js stop <id>`(go 를 띄운 셸을 죽이지 않는다).
- 사용자가 push 를 **명시적으로** 요청하면: `node harness/cli.js push [<remote>] [<branch>]` — 빨리감기만, 강제 없음, 결과 브랜치는 먼저 accept.
- 중단된 작업 이어 가기: `node harness/cli.js resume <id> --detach` 뒤 `wait <id>`(위와 같이) — 상한을 늘릴 때는 **새 총액**을 준다(`--budget-usd 40` = 작업 전체 $40, 추가분 아님).
- BLOCKED 로 끝났고 보고에 `denied commands` 가 있으면 사용자에게 보여 주고, 사용자가 허용하면 보고의 `resume <id> --allow "Bash(…:*)"` 줄을 그대로 실행한다(허용은 사용자가 정한다 — 스스로 넓히지 않는다).

## 현황
- `node harness/cli.js status` — 작업 목록 · 겹침 · 주인 없는 미커밋 변경.
- 끝난 작업의 worktree 정리: `node harness/cli.js gc`.
- 이전 하네스 버전의 잔여물(옛 worktree · 브랜치 · `.git/harness-v14`): `node harness/cli.js cleanup-legacy` 로 계획을 보여 주고, 사용자가 정리하라고 **말한 뒤에만** `--apply`. 내용이 현재 브랜치에 다 있고 깨끗한 것만 지우며, 지운 브랜치는 기록에서 되살릴 수 있다. 미커밋 작업이나 반영 안 된 커밋이 있어 남은 것은 `--salvage` 로 태그(`harness/salvage/…`)에 옮겨 놓고 지운다. `git branch -D` 나 `.git` 아래 직접 삭제는 하지 않는다(훅이 막는다).

## 문서 (사용자가 요청할 때만)
- 문서를 만들어 달라고 할 때만: `node harness/cli.js doc new <prd|coordination|design> "<제목>"` — 분석·요구사항은 prd, 다른 프로젝트와의 통신은 coordination(`--with <프로젝트>`), 디자인·와이어프레임·스토리보드는 design. 요청 없이 만들거나 고치지 않는다.
- 상태가 바뀌면 `doc status <경로> <active|done|superseded>`(대체는 `--by <새 문서>`) · 목록 `doc list` · 점검 `doc check` · 이전 판 `doc history <경로>` / `doc restore <경로> <판>`.
- 문서를 명세로 작업을 보낼 때: `node harness/cli.js go --goal-file "<파일>" --doc <문서 경로>` (여러 개면 `--doc` 반복).

## 하네스 보고 (자동)
- 하네스가 오류로 멈추거나 의도와 다르게 행동하거나 더 나은 방향이 보이면 묻지 말고 `node harness/cli.js report --kind <bug|intent|improve> --title "…" --body "…"` — 하네스 동작만 쓰고 프로젝트 코드 · 이름 · 경로는 쓰지 않는다. 사용자가 하네스에 대한 건의를 말하면 그것도 이렇게 올린다(`--kind improve`).
- 보고서 끝에 "하네스 결함으로 보입니다" 가 있으면 하네스가 이미 기록했다 — 따로 할 일은 없다(로그인이 없으면 `report` 가 링크를 보여 준다).

## 하네스로 보내지 않는 것
- 한두 줄 수정 · 질문 · 조사는 그 자리에서 하고, 고친 파일만 경로를 지정해 커밋한다(`git commit -m "…" -- <파일>`).
