'use strict';
// v5 프롬프트 — 짧게. 목표 원문 · 범위 · PLAN.md · 자율 정책 3문장 · 검사 · BLOCKED 출구 · git 은 하네스가.
const money = x => '$' + (Number(x) || 0).toFixed(2);

const AUTONOMY = [
  'Reversible actions (reading, editing files in this worktree, running builds and tests, installing dependencies locally) need no permission.',
  'No human is available during this run, so never ask questions or wait for confirmation — decide with your best judgment and proceed; record each decision point in DECISIONS.md (see the working rules).',
  // [2026-10-16 자동 보고 00b4667cbf35] "이번 작업에서 만들지 않은 파일은 지우지 말라" 가 앞 작업 파일의 이름 바꾸기를 막아 어색한 결과를 남겼다.
  //   worktree 안의 삭제 · 이름 바꾸기는 하네스가 턴마다 커밋하므로 되돌릴 수 있다 — 되돌릴 수 없는 것은 worktree 밖(guard 가 막는다).
  // [2026-10-17 자동 보고 caed67b9a2f1] 작업자가 worktree 의 compose 로 사용자의 실행 중 컨테이너를 다시 만들어 서비스가 멈췄다.
  'Do not stop, restart or recreate the running services, containers or processes of the main checkout — they are in use. If you need to run services, start your own (the harness gives this worktree its own COMPOSE_PROJECT_NAME) and stop them when you are done.',
  'Irreversible actions are forbidden: no git push, no merging or resetting branches, and no deleting anything outside this worktree. Deleting or renaming files inside this worktree is fine when the goal needs it (including files earlier tasks created) — the harness commits after every turn, so it can be undone.',
].join(' ');

// 작업 언어(task.language) — 사람이 읽는 것(PLAN.md · BLOCKED.md · 마지막 말)은 그 언어로. [2026-10-08] 지시가 없어 영어로 나왔다.
function languageLine(t) {
  return t && t.language ? `Write everything a person will read — PLAN.md, BLOCKED.md, code comments you add, and your final message — in ${t.language} (keep identifiers, commands, paths and quoted text as they are).` : null;
}
function systemAppend(t) { return [AUTONOMY, languageLine(t)].filter(Boolean).join(' '); }

// 첨부(go --attach) — 목록과 바뀐 모양(장면 이미지 · 전사)을 절대 경로로. 작업자는 worktree 밖이지만 그 폴더를 읽을 수 있다(Claude: --add-dir · Codex: 읽기는 열려 있다).
function attachmentLines(t) {
  const items = t.attachments || [];
  if (!items.length) return [];
  const L = ['# Attachments', `The user attached ${items.length} file(s) to this goal. They are part of the specification: look at every one before you start — open images, PDFs and video frames with your file-reading tool, and read transcripts. They live outside the worktree; do not copy them into it unless the goal asks for that.${t.runtime === 'codex' ? ' The images (and video frames) are also attached to this message.' : ''}`];
  for (const a of items) {
    L.push(`- ${a.name} (${a.kind}${a.duration_s != null ? `, ${a.duration_s} s` : ''}): ${a.file}`);
    if (a.frames && a.frames.length) L.push(`  - ${a.kind === 'video' ? 'frames' : 'converted image'}: ${a.frames.map(f => `${f.file}${f.at != null ? ` (at ${f.at} s)` : ''}`).join(' · ')}`);
    if (a.transcript) L.push(`  - transcript: ${a.transcript}`);
    for (const n of a.notes || []) L.push(`  - note: ${n}`);
  }
  return [...L, ''];
}

function checksLines(checks) {
  if (!checks || checks.source === 'none' || !(checks.commands || []).length) {
    return ['No automated checks were found for this repository. Verify your work yourself by running what is appropriate, and end with a short report of the evidence (commands you ran and their results).'];
  }
  const { display } = require('./checks');
  return ['When you end your turn, the harness runs these checks from the worktree root and decides whether you are done:',
    ...checks.commands.map(a => `- \`${display(a)}\``),
    'You can run them yourself. Make them pass by fixing the implementation; do not weaken, skip, or rewrite existing tests.',
    // [2026-09-30 실측 · Python 서비스 저장소] 원래 빨갛던 테스트(환경 의존) 때문에 모델이 BLOCKED 로 멈췄다 — 기준선을 알려 준다.
    ...(checks.baseline && !checks.baseline.ok && checks.source !== 'user' ? [
      `Before your change these checks already failed (baseline: ${checks.baseline.fail} failing, ${checks.baseline.pass} passing). The harness judges that your change makes them no worse — no new failures and no fewer passing tests. Do not try to fix unrelated pre-existing failures, and do not write BLOCKED.md because of them.`] : [])];
}

// go --doc 로 연결한 문서 — 메인 체크아웃의 절대 경로를 준다(docs 는 git 이 무시할 수 있어 worktree 에 없을 수 있다).
function docsLines(t, root) {
  const docs = t.docs || [];
  if (!docs.length) return [];
  const path = require('node:path');
  const abs = rel => (root ? path.join(root, ...rel.split('/')) : rel);
  return ['# Specification documents',
    'The user linked these documents as the specification and context for this goal. Read all of them before you start:',
    ...docs.map(d => `- ${abs(d)}`),
    'They live in the main checkout, not in this worktree (they may be untracked by git): read them at these absolute paths. Do not copy them into the worktree, and do not edit them unless the goal says so.', ''];
}

// [2026-10-01 · Python 서비스 저장소] 무인 실행에서 허용 목록 밖 명령(docker build · cp -r)은 물을 사람이 없어 자동 거부된다.
//   작업자가 그것을 알고, 사용자가 미리 허용한 규칙(go --allow · worker_allow)을 알고, 막히면 필요한 명령을 정확히 적게 한다.
function permissionLines(t) {
  const rel = `.harness/${t.id}`;
  const allow = t.allow || [];
  const out = [];
  // open(기본): 막지 않는다 — 하네스가 막는 것은 git 쓰기 · push · worktree 밖 삭제뿐이다. [2026-10-16 사용자 지시]
  if ((t.worker_permissions || 'open') === 'open' && t.runtime !== 'codex') {
    return [`- You may run any command you need — builds, tests, scripts, package installs inside this worktree, pipes and loops. The harness blocks only git writes and pushes (it commits your work after each turn) and deleting files outside this worktree. Do not work around a block; if the goal truly needs one of those, write \`${rel}/BLOCKED.md\` with the exact command and why, then stop.`];
  }
  if (allow.length) {
    out.push(`- The user pre-approved these commands for this task (in addition to the defaults)${t.runtime === 'codex' ? ' — the sandbox still applies' : ''}:`, ...allow.map(r => `  - \`${r}\``));
  }
  out.push(`- Commands outside the allow list are refused automatically, because nobody is available to approve them. Do not work around a refusal (no other shells, wrappers, or copies of the command). If the goal itself needs such a command (for example, it must build or deploy something with it), write \`${rel}/BLOCKED.md\` listing the exact commands needed (one per line) and why, then stop — the user can resume the task with them allowed.`);
  // [평가 2026-10-02] 위 문장 때문에 테스트 실행이 거부되자 다 만든 작업을 BLOCKED 로 멈췄다(3/3) — 검증은 하네스가 한다.
  out.push(`- If a refused command was only to verify your work (running tests, linters or the program), do not write BLOCKED.md for it: finish the implementation and end your turn — the harness runs the checks itself after your turn and sends any failures back to you. With no checks, say in your final message what you could not run.`);
  // [2026-10-15 현장 감사 · 10-16 실측] 작업자 셸 거부의 65% 가 출력을 거르는 파이프였다. PowerShell 도구의 파이프는 허용 규칙으로 통과시킬 수 없고
  //   (전부 허용 PowerShell(*) 만 통과), Bash 도구의 파이프는 grep · head · tail 등으로 통과한다.
  if (t.runtime !== 'codex') out.push('- To filter long output (`… 2>&1 | tail -40`, `| grep error`, `| head`), use the Bash tool: pipes into grep · head · tail · wc · sort · uniq · cut are allowed there. In the PowerShell tool any pipe (`| Select-String`, `| Select-Object`) is refused — run the command without the pipe, or use the Bash tool.');
  if (t.runtime === 'codex') out.push('- Your sandbox may refuse to start processes (for example `spawn EPERM` from `node --test` or a build tool). That is not a reason to stop either: the harness runs the checks outside the sandbox after your turn.');
  return out;
}

// 린트(lint_command) — 테스트 다음에 하네스가 돌린다. 실패하면 돌려보낸다.
function lintLines(checks) {
  const lt = checks && checks.lint;
  if (!lt) return [];
  return [`After the checks pass, the harness also runs the project's lint command${lt.files ? ' on the files you changed' : ''}: \`${lt.command}\`. A lint failure is sent back to you like a failing test — fix the code; do not disable rules or add ignore comments to make it pass.`,
    ...(!lt.files && lt.baseline_ok === false ? ['The whole-repository lint already failed before your change, so it is reported but does not block you; do not fix unrelated lint findings.'] : [])];
}
function lintFailMessage(t, r, excerpt, deadlineMs) {
  return ['The tests pass, but the project lint fails, so the task is not done.',
    `\`${r.command}\` — exit ${r.exit_code == null ? 'none' : r.exit_code}${r.timed_out ? ' (timed out)' : ''}`, '```\n' + String(excerpt || '').trim() + '\n```',
    remainingLine(t, deadlineMs),
    `Fix the code so the lint passes (do not disable rules or add ignore comments), keep .harness/${t.id}/PLAN.md current, and end your turn. If it cannot be done, write .harness/${t.id}/BLOCKED.md with the reason.`].join('\n\n');
}

function taskPrompt(t, o) {
  const rel = `.harness/${t.id}`;
  const docs = docsLines(t, o && o.root);
  return ['# Goal', t.goal, '', ...docs, ...attachmentLines(t),
    `${docs.length ? 'The goal and these documents are' : 'This is'} the complete specification. Do not expand scope beyond it.`, '',
    '# Working rules',
    `- Keep a living plan at \`${rel}/PLAN.md\`: goal, progress (checked items), decisions, discoveries, remaining work. A fresh session must be able to continue from that file and the git log alone.`,
    `- ${AUTONOMY}`,
    // [2026-10-16 사용자 지시] 시작 때 묻지 않고 지시를 바탕으로 끝까지 스스로 판단한다 — 결과를 바꾼 갈림길만 완성 뒤 보고에 정리한다(하네스가 DECISIONS.md 를 읽는다).
    `- Decision points: when you reach a fork that the goal and the repository do not settle — two or more reasonable options that change the result (behaviour, data or API shape, scope, dependencies, what the user sees) — never ask and never stop; pick the option that best fits the user's instructions and is easiest to change later, and keep going. Record each fork in \`${rel}/DECISIONS.md\` as a section: \`## <n>. <the fork in one line>\` followed by the lines \`- options: …\`, \`- chosen: …\`, \`- why: …\`, \`- effect: … (and how to change it later)\`. Only real forks — not routine implementation details. The harness shows them to the user when the work is done.`,
    ...(languageLine(t) ? [`- ${languageLine(t)}`] : []),
    `- If the task is impossible or the specification contradicts itself, write \`${rel}/BLOCKED.md\` explaining why and stop.`,
    '- Do not run git commands that write (commit, checkout, reset, merge, stash, branch). The harness commits after every turn.',
    // [2026-10-13 영상 "쓰레기 코드 없애는 법"] AI 는 더하기 기계다 — 덜 쓰게 한다(효과는 평가로 잰다: 숨은 검사 통과율 · 추가 줄 수).
    '- Write the least code that meets the goal: no features, options or abstractions the goal did not ask for; prefer the standard library and the project\'s existing helpers to hand-written ones; change only the lines the goal needs (match the existing style, do not reformat or refactor unrelated code); remove only what your own change made unused.',
    '- End with a short report: the result first, then the commands you ran to verify it and their results.',
    ...permissionLines(t), '',
    '# Checks', ...checksLines(t.checks), ...lintLines(t.checks)].join('\n');
}

function remainingLine(t, deadlineMs) {
  const c = t.caps, s = t.spent;
  const parts = [`budget ${money(Math.max(0, c.budget_usd - s.cost_usd))}`];
  if (c.token_budget) parts.push(`tokens ${Math.max(0, c.token_budget - s.tokens)}`);
  parts.push(`continuations ${Math.max(0, c.max_continuations - s.continuations - 1)} after this one`);
  if (deadlineMs) parts.push(`wall clock ${Math.max(0, Math.round((deadlineMs - Date.now()) / 60000))} min`);
  return `Remaining (enforced by the harness): ${parts.join(' · ')}.`;
}

function failMessage(t, judged, excerpt, deadlineMs) {
  return ['The harness ran the checks after your turn. They fail, so the task is not done.',
    `Failing: ${judged.fail} (passing: ${judged.pass}).`, excerpt,
    remainingLine(t, deadlineMs),
    `Fix the implementation (not the checks), keep .harness/${t.id}/PLAN.md current, and end your turn when the checks pass. If it cannot be done, write .harness/${t.id}/BLOCKED.md with the reason.`].filter(Boolean).join('\n\n');
}

// 중복 코드(dup.js) — 테스트 · 린트는 통과했지만 새로 쓴 코드가 있는 코드를 블록째 베꼈다. 한 번만 돌려보낸다.
function dupMessage(t, blocks, deadlineMs) {
  return ['The checks pass, but your change duplicates code that already exists (blocks of identical lines, whitespace ignored):',
    ...blocks.map(b => `- ${b.file}:${b.start}-${b.end} (${b.lines} lines) duplicates ${b.other}`),
    `Reuse the existing code instead — call it, or move it into one shared function both places use — and delete the copy. If the duplication is truly intended, keep it and say why in .harness/${t.id}/DECISIONS.md. Then end your turn.`,
    remainingLine(t, deadlineMs)].join('\n');
}
// 사용자가 작업 도중 더한 지시(note) — 다음 턴 메시지 머리에 붙는다. [2026-10-15 자동 이슈 #9]
function notesBlock(notes) {
  return ['# Additional instructions from the user (added while this task was running)', ...notes.map(n => `- ${String(n.text).replace(/\r?\n/g, '\n  ')}`),
    'They are part of the specification from now on and take precedence over earlier instructions where they conflict. Do not ask about them — apply them, and record any fork they create in DECISIONS.md.'].join('\n');
}
// 끝나려던 참에(또는 BLOCKED 뒤에) 추가 지시가 와서 한 턴 더 도는 메시지 — 지시 자체는 notesBlock 이 앞에 붙는다.
function notesTurnMessage(t, deadlineMs) {
  return [`Apply the additional instructions above to the work in this worktree, keep .harness/${t.id}/PLAN.md and DECISIONS.md current, and end your turn when they are done. The harness runs the checks again after your turn.`,
    remainingLine(t, deadlineMs)].join('\n\n');
}

function nudgeMessage(t) {
  return `No human is available to answer. Use your best judgment, record the decision point in .harness/${t.id}/DECISIONS.md, and continue until the goal is complete. If it truly cannot be done, write .harness/${t.id}/BLOCKED.md with the reason.`;
}

// 러너 오류(crash · model)로 끝난 턴 — 판정하지 않고 같은 세션을 1회 이어 간다(H1).
function errorMessage(t, kind, why, deadlineMs) {
  return [`Your previous turn ended with an error (${kind}${why ? `: ${String(why).replace(/\s+/g, ' ').slice(0, 300)}` : ''}), so the harness did not judge it.`,
    `Check the state of the worktree, read .harness/${t.id}/PLAN.md, and continue until the goal is complete.`,
    remainingLine(t, deadlineMs)].join('\n\n');
}

// 변경이 하나도 없는 턴(H2) — 검사가 초록이어도 아무것도 안 했으면 끝이 아니다.
function noChangeMessage(t) {
  return [`The harness sees no changes to the repository outside .harness/ — nothing has been done yet. No human is available to answer questions.`,
    `Do the work the goal asks for now, record decision points in .harness/${t.id}/DECISIONS.md, and end your turn when it is complete. If it truly cannot be done, write .harness/${t.id}/BLOCKED.md with the reason.`].join('\n\n');
}

// added: 이번 resume 에서 사용자가 새로 허용한 규칙.
function resumeMessage(t, deadlineMs, added) {
  return [`The run was interrupted (${t.reason || t.status}). Continue the same task from where you stopped: read .harness/${t.id}/PLAN.md and \`git log\` in this worktree, then keep going until the goal is complete.`,
    ...((added || []).length ? [`The user also pre-approved these commands: ${added.join(', ')}.`] : []),
    remainingLine(t, deadlineMs)].join('\n\n');
}

// blocked 에서 resume — 사용자가 BLOCKED.md 를 읽고 규칙을 허용했거나(added) 그냥 계속하라고 했다. 옛 BLOCKED.md 는 movedTo 로 옮겨 두었다.
function unblockMessage(t, added, movedTo, deadlineMs) {
  const what = (added || []).length ? `allowed: ${added.join(', ')}` : 'asked you to continue';
  return [`The user reviewed your BLOCKED.md and ${what}. Continue the task; the harness judges completion with the same checks.`,
    `${movedTo ? `Your previous BLOCKED.md was moved to ${movedTo}. ` : ''}Read .harness/${t.id}/PLAN.md, do the remaining work, and end your turn when it is complete. If you are blocked again, write a new .harness/${t.id}/BLOCKED.md with the exact commands you need.`,
    remainingLine(t, deadlineMs)].join('\n\n');
}

function conflictMessage(t, target, files) {
  return [`The harness is integrating your branch with \`${target}\`, which moved ahead. The merge stopped with conflicts in:`,
    ...files.map(f => `- ${f}`),
    'Resolve every conflict: edit these files so they keep both intents, and remove all conflict markers (<<<<<<<, =======, >>>>>>>). Do not run git commands; the harness completes the merge and re-runs the checks when you end your turn.'].join('\n');
}

// 마지막 말이 질문·허락 요청인가.
function isQuestion(text) {
  const s = String(text || '').trim();
  if (!s) return false;
  if (/[?？]\s*[)\]"'`*_]*\s*$/.test(s)) return true;
  return /할까요|하시겠|원하시면|괜찮을까요|진행할까|\bshould I\b|\bwould you like\b|\bshall I\b|\bdo you want\b|\blet me know if\b/i.test(s.slice(-400));
}

module.exports = { dupMessage, notesBlock, notesTurnMessage, lintLines, lintFailMessage, AUTONOMY, systemAppend, languageLine, attachmentLines, taskPrompt, failMessage, nudgeMessage, noChangeMessage, errorMessage, resumeMessage, unblockMessage, conflictMessage, isQuestion, remainingLine, money };
