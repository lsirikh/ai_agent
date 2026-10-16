'use strict';
// v5 루프 — go / resume. 모델이 일하고, 하네스는 턴마다 커밋하고 신뢰할 수 있는 검사로만 판정한다.
//   턴 끝: 체크포인트 커밋(비밀 경로 제외 · 못 넣는 경로 제외 · 실패해도 기록하고 계속) → (BLOCKED.md → blocked)
//          · 러너 오류(crash · model)로 끝난 턴은 판정하지 않는다 → CLI 예산 소진이면 capped, 아니면 1회 다시 · 연속 2회 → error
//          → 검사 → 실패 → 같은 세션 이어 가기(실패 발췌) · 같은 실패 서명 2회 연속 → stalled
//          → 통과/나빠지지 않음/검사 없음 → 기준 대비 .harness/ 밖 변경이 0 이거나 마지막 말이 질문이면 1회 넛지
//            (넛지 뒤에도 변경 0 → failed) · 아니면 done(나빠지지 않음이면 이유에 "baseline was red")
//   상한(비용·토큰·벽시계·이어 가기)은 매 호출 전에 강제 → capped. 사용량 한도 → interrupted(재개 가능). 상한은 작업 전체의 총액이다.
//   끝: 최종 커밋(항상 시도) → 보고 → 커밋이 됐고 무시된 파일 변경도 없을 때만 worktree 제거(아니면 남기고 이유를 보고).
const fs = require('node:fs'), path = require('node:path'), crypto = require('node:crypto');
const S = require('./state'), G = require('./git'), K = require('./checks'), Pr = require('./prompts'), D = require('./docs'), Po = require('./policy'), M = require('./media');

const DEFAULTS = { runtime: 'claude', model: 'opus', effort: null, budgetUsd: 20, tokenBudget: null, wallMin: 120, maxContinuations: 8 };
// blocked 도 재개한다 — 사용자가 BLOCKED.md 를 읽고 필요한 명령을 허용(resume --allow)하거나 계속하라고 할 수 있다.
const RESUMABLE = new Set(['interrupted', 'capped', 'stalled', 'failed', 'error', 'running', 'blocked']);
const MAX_DENIED = 20;
const RUNNER_GRACE_MS = 30000;
const TEST_FILE_RE = /(^|\/)(tests?|__tests__|specs?)\/|(^|\/)test_[^/]+\.py$|[._-](test|spec)s?\.[A-Za-z0-9]+$|(^|\/)[^/]*Tests?\.(cs|fs|vb|java|kt)$/i;

function getRun(o) {
  if (o && typeof o.run === 'function') return o.run;
  if (process.env.HARNESS_RUNNER_MODULE) return require(path.resolve(process.env.HARNESS_RUNNER_MODULE)).run;
  try { return require('./runner').run; }
  catch (e) {
    if (e.code === 'MODULE_NOT_FOUND' && /[\\/]runner(\.js)?'/.test(e.message)) throw Object.assign(new Error('harness/lib/runner.js is missing — the runner is not installed'), { code: 'NO_RUNNER' });
    throw e;
  }
}
const logger = o => (o && o.log) || (m => process.stderr.write(m + '\n'));
const numOr = (v, d) => (v == null || v === '' || Number.isNaN(Number(v))) ? d : Number(v);

function capsFrom(o, base) {
  const b = base || { budget_usd: DEFAULTS.budgetUsd, token_budget: DEFAULTS.tokenBudget, wall_min: DEFAULTS.wallMin, max_continuations: DEFAULTS.maxContinuations };
  return { budget_usd: numOr(o.budgetUsd, b.budget_usd), token_budget: o.tokenBudget == null ? b.token_budget : Number(o.tokenBudget),
    wall_min: numOr(o.wallMin, b.wall_min), max_continuations: o.maxContinuations == null ? b.max_continuations : Math.floor(Number(o.maxContinuations)) };
}

// ── go ─────────────────────────────────────────────────────────────────
async function go(o) {
  const t0 = Date.now(), log = logger(o);
  const goal = String(o.goal || '').trim();
  if (!goal) throw Object.assign(new Error('go needs a goal'), { code: 'USAGE' });
  const runtime = o.runtime || DEFAULTS.runtime;
  if (!['claude', 'codex'].includes(runtime)) throw Object.assign(new Error(`unknown runtime: ${runtime}`), { code: 'USAGE' });
  if (o.id != null && !S.validId(o.id)) throw Object.assign(new Error(`invalid task id: ${JSON.stringify(String(o.id)).slice(0, 80)} (expected t-yyyymmdd-HHMMss-xxxx)`), { code: 'USAGE' });
  // --allow: 작업 단위 추가 허용. git 쓰기 · 셸 · 통째 허용은 작업을 만들기 전에 USAGE 로 거부한다.
  const cliAllow = Po.checkAllowRules(o.allow, '--allow');
  const run = getRun(o);
  // 기준은 부른 체크아웃의 HEAD, 경로는 주 worktree 에 묶는다. 없는 경로·저장소 아닌 폴더에 저장소를 만드는 것은 --init 일 때만(L7).
  const start = path.resolve(o.root || process.cwd());
  if (!o.init && !G.isRepo(start)) throw Object.assign(new Error(`not a git repository: ${start} — pass --init to create one there`), { code: 'USAGE' });
  const here = G.ensureRepo(start);
  const root = S.mainRoot(here);
  const baseCommit = G.headSha(here, o.base || 'HEAD');
  if (!baseCommit) throw Object.assign(new Error(`unknown base: ${o.base}`), { code: 'USAGE' });
  // 프로젝트 기본 허용(worker_allow) — 부른 체크아웃, 없으면 주 체크아웃의 AGENTS.md · CLAUDE.md(gitignore 된 CLAUDE.md 도 읽게).
  //   작업을 만들 때 한 번만 읽어 task.allow 에 기록한다 — resume 은 그것을 쓰고, worktree 에서 작업자가 고친 AGENTS.md 는 읽지 않는다.
  const projAllow = Po.checkAllowRules(K.yamlList(here, 'worker_allow') || (G.samePath(here, root) ? null : K.yamlList(root, 'worker_allow')), 'worker_allow in the project block (AGENTS.md / CLAUDE.md)');
  const allow = [...new Set([...projAllow, ...cliAllow])];
  // --doc: 명세 문서(메인 체크아웃 기준 상대 경로로 기록). 없는 파일이면 작업을 만들기 전에 거부.
  const docs = D.resolveDocs(root, o.docs);
  // --attach: 함께 준 파일(이미지 · 영상 · 음성 · 문서). 없거나 너무 크면 작업을 만들기 전에 거부.
  const attach = (o.attach || []).map(f => path.resolve(f));
  for (const f of attach) { const why = M.checkFile(f); if (why) throw Object.assign(new Error(why), { code: 'USAGE' }); }
  // 작업 언어 — 작업자가 PLAN.md · BLOCKED.md · 마지막 말을 쓰는 언어. 프로젝트 블록 reply_language > 목표에 한글이 있으면 Korean > 지정 없음.
  //   [2026-10-08] 언어 지시가 어디에도 없어 작업자의 기록 · 보고가 영어로 나왔다.
  const yamlLang = K.yamlString(here, 'reply_language') || K.yamlString(root, 'reply_language');
  const language = yamlLang || (/[가-힣]/.test(goal) ? 'Korean' : null);
  const id = o.id || S.newId(), P = S.taskPaths(root, id);
  const lock = S.acquire(root, `task-${id}`);
  const task = S.newTask({ id, goal, runtime, model: o.model || (runtime === 'claude' ? DEFAULTS.model : null), effort: o.effort || null,
    base_branch: o.base ? o.base.replace(/^refs\/heads\//, '') : G.currentBranch(here), base_commit: baseCommit, branch: P.branch, worktree: P.wt,
    owner: S.ownerRecord(), caps: capsFrom(o), docs, allow, language });
  S.writeTask(root, task);
  S.log(root, id, { event: 'created', goal, base_branch: task.base_branch, base_commit: baseCommit, docs, allow });
  if (allow.length && runtime === 'codex') log(`[harness] ${id} — note: allow rules (${allow.join(', ')}) have no effect on the Codex runtime; its sandbox governs what runs`);
  const c = { root, P, task, run, lock, log, t0, spentBefore: 0, o };
  try {
    G.addWorktree(root, P.wt, { branch: P.branch, base: baseCommit });
    task.worktree_include = G.copyWorktreeInclude(root, P.wt);
    if (attach.length) {
      const prep = M.prepare(attach, path.join(P.dir, 'attachments'), { transcribe: K.yamlString(here, 'transcribe_command') || K.yamlString(root, 'transcribe_command') });
      task.attachments = prep.items;
      S.log(root, id, { event: 'attachments', items: prep.items.map(x => ({ name: x.name, kind: x.kind, frames: x.frames.length, transcript: !!x.transcript, notes: x.notes })), tools: prep.tools });
      S.writeTask(root, task);
    }
    const found = K.discover(P.wt, o.checks, here);
    // defs: 검사 명령이 읽는 정의의 기준 값(M6) — 모델이 scripts.test 를 바꿔도 판정은 이것으로.
    // [2026-09-30 실측 · Python 서비스 저장소] 전체 회귀가 20분을 넘는 저장소 — 검사 상한(기본 15분)에 매번 걸리면 끝낼 수 없다.
    //   --check-timeout-min 이 없으면 프로젝트 블록의 check_timeout_min 을 쓴다. resume 도 같은 값을 쓰도록 기록한다.
    if (o.checkTimeoutMs == null) { const m = K.yamlNumber(here, 'check_timeout_min') || K.yamlNumber(P.wt, 'check_timeout_min'); if (m) o.checkTimeoutMs = m * 60000; }
    task.checks = { source: found.source, from: found.from || null, commands: found.commands, defs: K.definitions(P.wt), baseline: null, last: null, timeout_ms: o.checkTimeoutMs || K.CHECK_TIMEOUT_MS };
    // 린트(프로젝트 블록 lint_command) — 테스트 다음의 두 번째 결정적 검사. {files} 가 있으면 작업이 바꾼 파일만.
    const lintCmd = K.yamlString(here, 'lint_command') || K.yamlString(P.wt, 'lint_command');
    if (/^(off|false|no)$/i.test(K.yamlString(here, 'rerun_failed') || K.yamlString(P.wt, 'rerun_failed') || '')) task.checks.rerun = false;
    if (/^(on|true|yes)$/i.test(K.yamlString(here, 'serial_checks') || K.yamlString(P.wt, 'serial_checks') || '')) task.checks.serial = true;
    // 작업자 권한 — 기본 open(명령을 막지 않고 git 쓰기 · worktree 밖 삭제만 막는다). worker_permissions: strict 면 예전 허용 목록. [2026-10-16 사용자 지시]
    // 중복 코드 검사 — 기본 켬 · dup_check: off 로 끈다 · dup_min_lines 로 블록 크기(기본 8).
    task.checks.dup = { on: !/^(off|false|no)$/i.test(K.yamlString(here, 'dup_check') || K.yamlString(P.wt, 'dup_check') || ''), min_lines: K.yamlNumber(here, 'dup_min_lines') || K.yamlNumber(P.wt, 'dup_min_lines') || 8 };
    task.worker_permissions = /^strict$/i.test(K.yamlString(here, 'worker_permissions') || K.yamlString(P.wt, 'worker_permissions') || '') ? 'strict' : 'open';
    if (lintCmd) task.checks.lint = { command: lintCmd, files: /{files}/.test(lintCmd), baseline_ok: null, last: null };
    S.writeTask(root, task);
    log(`[harness] ${id} — worktree ${P.wt} · checks: ${found.source}${found.commands.length ? ' — ' + found.commands.map(K.display).join(' ; ') : ''}`);
    if (found.commands.length) {
      // 기준선 캐시: 같은 기준 커밋 · 같은 검사 · 같은 .worktreeinclude 내용이면 앞선 작업의 기준선을 다시 쓴다(느린 저장소에서 작업마다 수십 분).
      const cacheKey = crypto.createHash('sha1').update(JSON.stringify([baseCommit, found.commands, (task.worktree_include || []).map(x => `${x.path}:${x.sha1}`)])).digest('hex');
      const cacheFile = path.join(S.paths(root).harnessDir, 'baseline-cache', `${cacheKey}.json`);
      let b = null;
      if (!o.freshBaseline) { try { b = JSON.parse(fs.readFileSync(cacheFile, 'utf8')); } catch { b = null; } }
      if (b) { log(`[harness] ${id} — baseline reused from an earlier task on the same base commit (--fresh-baseline to rerun)`); task.checks.baseline_cached = true; }
      else {
        b = (await K.runJudged(P.wt, found.commands, { timeoutMs: o.checkTimeoutMs, rerun: task.checks.rerun, serialRoot: task.checks.serial ? root : null })).judged;
        const slim = { ...b, results: (b.results || []).map(r => ({ ...r, output: undefined })) };
        try { fs.mkdirSync(path.dirname(cacheFile), { recursive: true }); fs.writeFileSync(cacheFile, JSON.stringify(slim)); } catch { /* 캐시 실패는 작업을 멈추지 않는다 */ }
      }
      // [2026-10-16 자동 이슈 #13] 저장소에서 찾은 검사가 새 worktree 에서 작업 전부터 시간 초과 — 작업과 무관하게 정체됐다.
      //   자동으로 찾은 검사(사용자가 준 것이 아닌)는 기준선에서 시간 초과면 판정에서 빼고 알린다(남은 검사가 없으면 모델의 보고로 끝난다).
      if (found.source !== 'user' && b.results.some(x => x.timed_out)) {
        const keep = b.results.map(x => !x.timed_out);
        task.checks.dropped = found.commands.filter((_, i) => !keep[i]).map(cmd => ({ command: K.display(cmd), why: 'timed out before the task (baseline)' }));
        task.checks.commands = found.commands.filter((_, i) => keep[i]);
        b = K.summarize(b.results.filter((_, i) => keep[i]));
        log(`[harness] ${id} — dropped auto-detected checks that timed out before the task: ${task.checks.dropped.map(d => d.command).join(' ; ')}`);
      }
      task.checks.baseline = K.brief(b);
      // 요약 없이 종료 코드만 빨간 기준선(M7) — 새 worktree 에 의존성(node_modules 등 무시된 파일)이 없어서일 수 있다.
      const blind = b.results.filter(x => !x.ok && !x.found);
      if (blind.length) {
        task.checks.baseline_warning = `the checks failed before the task without a readable test summary (${blind.map(x => `${x.command}: ${x.timed_out ? 'timed out' : `exit ${x.exit_code}`}`).join('; ')}) — this may be an environment problem in the new worktree (e.g. dependencies are not installed there; list them in .worktreeinclude), and such checks cannot show "not worse"`;
        log(`[harness] ${id} — warning: ${task.checks.baseline_warning}`);
      }
      S.log(root, id, { event: 'baseline', ok: b.ok, pass: b.pass, fail: b.fail, warning: task.checks.baseline_warning || null });
      S.writeTask(root, task);
    }
    // 저장소 전체 린트는 작업 전 상태를 재 둔다 — 원래 빨갛다면 막지 않고 보고만 한다(바꾼 파일만 보는 {files} 가 낫다).
    if (task.checks.lint && !task.checks.lint.files) {
      const lb = await K.runCheck(P.wt, K.lintArgv(lintCmd, []), { timeoutMs: o.checkTimeoutMs });
      task.checks.lint.baseline_ok = lb.ok;
      S.log(root, id, { event: 'lint_baseline', ok: lb.ok, exit_code: lb.exit_code });
      S.writeTask(root, task);
    }
    return await loop(c, 'initial');
  } catch (e) {
    // 작업 중 예기치 못한 예외 — 하네스 결함일 수 있다(가려서 기록 · 보고에 안내).
    const bug = require('./bugreport').record(root, 'task', e);
    const res = finish(c, 'error', `${e.code ? e.code + ': ' : ''}${e.message}`);
    if (bug && res.report) res.report += `
하네스 결함으로 보입니다(서명 ${bug.sig}) — 내용을 확인하고 보고하려면: node harness/cli.js report-bug`;
    return res;
  }
}

// ── resume ─────────────────────────────────────────────────────────────
async function resume(o) {
  const t0 = Date.now(), log = logger(o);
  if (!S.validId(o.id)) throw Object.assign(new Error(`invalid task id: ${JSON.stringify(String(o.id)).slice(0, 80)} (expected t-yyyymmdd-HHMMss-xxxx)`), { code: 'USAGE' });
  const root = S.mainRoot(o.root || process.cwd());
  const task = S.readTask(root, o.id);
  if (!task) throw Object.assign(new Error(`unknown task: ${o.id}`), { code: 'UNKNOWN_TASK' });
  const added = Po.checkAllowRules(o.allow, '--allow').filter(r => !(task.allow || []).includes(r));
  const refuse = reason => ({ ...result(task), refused: true, reason, report: `harness ${task.id} — not resumed: ${reason}` });
  // done 이라도 전달하지 않은 추가 지시(note)가 있으면 이어 간다 — 그 지시를 반영하는 턴(자동 이슈 #9).
  const wasDoneWithNotes = task.status === 'done' && pendingNotes(root, task.id).length > 0;
  if (!RESUMABLE.has(task.status) && !wasDoneWithNotes) return refuse(`status is ${task.status}; only ${[...RESUMABLE].join('/')} tasks can be resumed`);
  if (task.status === 'running' && task.owner && !S.isSelf(task.owner) && S.ownerAlive(task.owner)) return refuse(`task is being run by pid ${task.owner.pid}@${task.owner.host}`);
  let lock;
  try { lock = S.acquire(root, `task-${task.id}`); }
  catch (e) { if (e.code === 'LOCK_HELD') return refuse(`task is owned by a live process (pid ${e.owner && e.owner.pid})`); throw e; }
  const run = getRun(o), P = S.taskPathsFor(root, task);
  task.caps = capsFrom(o, task.caps);
  if (o.model) task.model = o.model;
  if (o.effort) task.effort = o.effort;
  const wasBlocked = task.status === 'blocked';
  task.allow = [...(task.allow || []), ...added];
  task.status = 'running'; task.reason = ''; task.owner = S.ownerRecord(); task.last_signature = null;
  delete task.worktree_kept; delete task.commit_error;
  S.writeTask(root, task);
  S.log(root, task.id, { event: 'resume', caps: task.caps, from: wasBlocked ? 'blocked' : undefined, allow_added: added.length ? added : undefined });
  if (added.length && task.runtime === 'codex') log(`[harness] ${task.id} — note: allow rules have no effect on the Codex runtime; its sandbox governs what runs`);
  const c = { root, P, task, run, lock, log, t0, spentBefore: task.spent.wall_ms || 0, o, added };
  try {
    if (!fs.existsSync(P.wt) || !G.worktreeRegistered(root, P.wt) || !G.isWorktreeRoot(P.wt, task.branch)) {
      const why = G.clearWorktreeSlot(root, P.wt, task.branch, o.removalWaitMs, G.slotOpts(root, task.id, P.dir, log));
      if (why && !G.useAltWorktree(root, task, P, why, log)) return finish(c, 'interrupted', why);
      G.git(root, ['worktree', 'prune'], { allowFail: true });
      G.addWorktree(root, P.wt, { branch: task.branch, base: task.base_commit });   // 브랜치가 없으면(생성 전 오류) 기록된 기준에서
      task.worktree_include = G.copyWorktreeInclude(root, P.wt);
    }
    // blocked 에서 재개: 옛 BLOCKED.md 를 BLOCKED.<n>.md 로 옮겨(이력은 브랜치에 남는다) 다음 턴 끝에 다시 blocked 로 읽히지 않게 하고,
    //   같은 세션에 "사용자가 BLOCKED.md 를 보고 허용했다/계속하라고 했다" 를 보낸다.
    if (wasBlocked) {
      const movedTo = moveBlocked(P);
      if (movedTo) S.log(root, task.id, { event: 'blocked_moved', to: movedTo });
      if (task.session_id) c.firstMessage = deadline => Pr.unblockMessage(task, added, movedTo, deadline);
    }
    if (wasDoneWithNotes && task.session_id) c.firstMessage = deadline => Pr.notesTurnMessage(task, deadline);
    return await loop(c, task.session_id ? 'resume' : 'initial');
  } catch (e) {
    // 작업 중 예기치 못한 예외 — 하네스 결함일 수 있다(가려서 기록 · 보고에 안내).
    const bug = require('./bugreport').record(root, 'task', e);
    const res = finish(c, 'error', `${e.code ? e.code + ': ' : ''}${e.message}`);
    if (bug && res.report) res.report += `
하네스 결함으로 보입니다(서명 ${bug.sig}) — 내용을 확인하고 보고하려면: node harness/cli.js report-bug`;
    return res;
  }
}

// .harness/<id>/BLOCKED.md → BLOCKED.<n>.md (n = 비어 있는 첫 번호). 옮긴 상대 경로, 없으면 null.
function moveBlocked(P) {
  if (!fs.existsSync(P.blockedFile)) return null;
  const dir = path.dirname(P.blockedFile);
  let n = 1;
  while (fs.existsSync(path.join(dir, `BLOCKED.${n}.md`))) n++;
  fs.renameSync(P.blockedFile, path.join(dir, `BLOCKED.${n}.md`));
  return `${P.relWork}/BLOCKED.${n}.md`;
}

// 러너가 돌려준 권한 거부(permission_denials: [{tool_name, tool_input:{command|file_path|url}}]) → task.denied 에 쌓는다.
//   이번 실행(go 또는 resume 한 번) 동안 중복 없이 최대 MAX_DENIED — 거부된 턴 뒤에 모델이 BLOCKED.md 만 쓰고 끝나는 턴이 와도 잃지 않게.
function recordDenials(task, denials) {
  const cur = task.denied || (task.denied = []);
  for (const d of denials || []) {
    if (!d || typeof d !== 'object') continue;
    const inp = d.tool_input && typeof d.tool_input === 'object' ? d.tool_input : {};
    const tool = String(d.tool_name || 'Bash');
    const raw = inp.command != null ? inp.command : inp.file_path != null ? inp.file_path : inp.url != null ? inp.url : inp.path != null ? inp.path : JSON.stringify(inp);
    const command = String(raw).replace(/\s+/g, ' ').trim().slice(0, 300);
    if (!command || cur.some(x => x.tool === tool && x.command === command)) continue;
    if (cur.length >= MAX_DENIED) break;
    cur.push({ tool, command });
  }
}

// ── 루프 ───────────────────────────────────────────────────────────────
function capHit(task, deadline, continuing) {
  const c = task.caps, s = task.spent;
  if (c.budget_usd != null && s.cost_usd >= c.budget_usd) return `cost $${s.cost_usd.toFixed(2)} reached the budget $${Number(c.budget_usd).toFixed(2)}`;
  if (c.token_budget && s.tokens >= c.token_budget) return `tokens ${s.tokens} reached the token budget ${c.token_budget}`;
  if (Date.now() >= deadline) return `wall clock ${c.wall_min} min reached`;
  if (continuing && s.continuations >= c.max_continuations) return `${s.continuations} continuations used (max ${c.max_continuations})`;
  return null;
}

async function callRunner(c, message, deadline) {
  const { task, P } = c;
  const left = Math.max(1000, deadline - Date.now());
  const ctrl = new AbortController();
  let timer, grace;
  const newSessionId = !task.session_id && task.runtime === 'claude' ? crypto.randomUUID() : undefined;
  const args = { runtime: task.runtime, cwd: P.wt, prompt: message, sessionId: task.session_id || null, newSessionId, model: task.model, effort: task.effort,
    budgetUsd: Math.max(0, task.caps.budget_usd - task.spent.cost_usd), tokenBudget: task.caps.token_budget ? Math.max(0, task.caps.token_budget - task.spent.tokens) : null,
    timeoutMs: left, signal: ctrl.signal, allowCommands: c.allow, allowRules: task.allow || [], workerPermissions: task.worker_permissions || 'open', systemAppend: Pr.systemAppend(task),
    images: !task.session_id ? M.imagesOf(task.attachments) : [],   // Codex -i — 첫 호출에만
    // --doc 명세는 메인 체크아웃에 있다(gitignore 된 docs/ 일 수 있다) — worktree 밖이라 Claude 워커가 못 읽을 수 있어 그 폴더를 열어 준다.
    addDirs: [...new Set([...(task.docs || []).map(d => path.dirname(path.resolve(P.root || c.root, d))), ...((task.attachments || []).length ? [path.join(S.taskPaths(c.root, task.id).dir, 'attachments')] : [])])],
    priorSessionCostUsd: task.session_id ? (task.session_cost_usd || 0) : 0 };   // claude 재개: 세션 누계에서 이번 호출분을 떼어 내게
  const hung = new Promise(res => {
    timer = setTimeout(() => { ctrl.abort(); grace = setTimeout(() => res({ is_error: true, error_kind: 'timeout', error_message: 'runner did not return after the wall-clock abort' }), RUNNER_GRACE_MS); }, left);
  });
  let r;
  try { r = await Promise.race([Promise.resolve().then(() => c.run(args)), hung]); }
  catch (e) { r = { ok: false, is_error: true, error_kind: ctrl.signal.aborted ? 'aborted' : 'crash', error_message: String(e && e.message || e) }; }
  finally { clearTimeout(timer); clearTimeout(grace); }
  r = r || { is_error: true, error_kind: 'crash', error_message: 'runner returned nothing' };
  if (!r.session_id && newSessionId && !r.is_error) r.session_id = newSessionId;
  return { r, newSessionId };
}

function account(task, r, continuing, newSessionId) {
  const cost = Number(r.cost_usd) || 0;
  task.spent.cost_usd = Math.round((task.spent.cost_usd + cost) * 1e6) / 1e6;
  // 비용을 모르는 Claude 호출(시간 초과로 죽음 · 결과 JSON 없음) — 예산에 들어가지 않았으니 보고에 센다(L9). Codex 는 원래 USD 가 없다.
  if (task.runtime === 'claude' && (r.cost_usd == null || Number.isNaN(Number(r.cost_usd)))) task.spent.unknown_cost_calls = (task.spent.unknown_cost_calls || 0) + 1;
  const total = r.tokens && Number(r.tokens.total);
  if (total) {
    // Codex 의 usage 는 누계다 — 직전 누계보다 크면 차이만, 줄었으면(새 계수) 그 값 전체를 더한다.
    if (task.runtime === 'codex') {
      const same = r.session_id && r.session_id === task.session_id, last = same ? (task.tokens_last_total || 0) : 0;
      task.spent.tokens += total >= last ? total - last : total;
      task.tokens_last_total = total;
    } else task.spent.tokens += total;
  }
  if (continuing) task.spent.continuations++;
  // 세션 id 는 확인됐을 때만 저장한다(H1): 성공한 턴 · 러너가 CLI 에서 확인한 id · 우리가 지어내지 않은 id.
  //   결과 없이 죽은 새 세션의 미리 정한 uuid 를 저장하면 --resume 이 영구 실패한다.
  const trusted = !!r.session_id && (!r.is_error || r.session_confirmed === true || r.session_id !== newSessionId);
  if (!trusted) return;
  const sameSession = !!task.session_id && r.session_id === task.session_id;
  if (r.session_cost_usd != null) task.session_cost_usd = Number(r.session_cost_usd) || 0;
  else task.session_cost_usd = (sameSession ? (task.session_cost_usd || 0) : 0) + cost;
  task.session_id = r.session_id;
}

// 턴 끝 커밋. 비밀 경로는 빼고(H5), add 가 못 넣는 경로는 빼고 다시(L1). 그래도 실패하면 기록하고 계속한다 —
//   o.throwOnError(끝의 최종 커밋)면 던져서 호출자가 worktree 를 남기게 한다.
function checkpoint(c, label, o) {
  const { task, P, root } = c;
  const excluded = [], skipped = [];
  let sha = null;
  // 작업 브랜치에서만 커밋한다 — 세션이 worktree 를 다른 브랜치로 옮겼으면(권한 규칙은 경계가 아니다) 그 브랜치에 쌓지 않는다.
  try { sha = G.commitAll(P.wt, `harness(${task.id}): ${label}`, { excluded, skipped, branch: task.branch }); }
  catch (e) {
    task.commit_failures = (task.commit_failures || 0) + 1;
    task.last_commit_error = String(e.message).slice(0, 500);
    S.log(root, task.id, { event: 'commit_error', label, error: task.last_commit_error });
    if (o && o.throwOnError) throw e;
    return null;
  } finally {
    const add = (key, list) => { if (!list.length) return; const cur = new Set(task[key] || []); const fresh = list.filter(x => !cur.has(x)); if (fresh.length) { task[key] = [...cur, ...fresh]; S.log(root, task.id, { event: key, label, paths: fresh }); } };
    add('secrets_excluded', excluded); add('commit_skipped', skipped);
  }
  if (sha) { task.commits.push(sha); S.log(root, task.id, { event: 'commit', sha, label }); }
  return sha;
}
// 기준 대비 결과 브랜치(worktree HEAD)에서 바뀐 파일 — .harness/ 밖만.
function changedOutsideHarness(c) {
  return G.diffNames(c.P.wt, c.task.base_commit, 'HEAD').filter(f => !f.startsWith('.harness/'));
}

// ── 추가 지시(note) ── [2026-10-15 자동 이슈 #9] 진행 중에 요구를 덧붙일 길이 없어 stop → cancel → 다시 go 를 되풀이했다.
//   tasks/<id>/notes.jsonl 에 쌓고, 작업 루프가 다음 턴에 전달한다(task.notes_delivered = 전달한 개수).
function notesFile(root, id) { return path.join(S.taskPaths(root, id).dir, 'notes.jsonl'); }
function allNotes(root, id) {
  let text = ''; try { text = fs.readFileSync(notesFile(root, id), 'utf8'); } catch { return []; }
  return text.split(/\r?\n/).filter(Boolean).map(l => { try { return JSON.parse(l); } catch { return null; } }).filter(n => n && n.text);
}
function addNote(root, id, text) {
  const t = String(text || '').replace(/^﻿/, '').trim();
  if (!t) throw Object.assign(new Error('note needs text'), { code: 'USAGE' });
  if (!S.readTask(root, id)) throw Object.assign(new Error(`unknown task: ${id}`), { code: 'UNKNOWN_TASK' });
  fs.mkdirSync(path.dirname(notesFile(root, id)), { recursive: true });
  fs.appendFileSync(notesFile(root, id), JSON.stringify({ at: S.nowIso(), text: t }) + '\n');
}
function pendingNotes(root, id) { const t = S.readTask(root, id); return allNotes(root, id).slice((t && t.notes_delivered) || 0); }
function takeNotes(c) {
  const all = allNotes(c.root, c.task.id), fresh = all.slice(c.task.notes_delivered || 0);
  if (!fresh.length) return null;
  c.task.notes_delivered = all.length;
  S.writeTask(c.root, c.task);
  S.log(c.root, c.task.id, { event: 'notes_delivered', count: fresh.length });
  c.log(`[harness] ${c.task.id} — 사용자 추가 지시 ${fresh.length}건을 전달한다`);
  return fresh;
}

async function loop(c, kind) {
  const { root, P, task, log } = c;
  const deadline = c.t0 + task.caps.wall_min * 60000 - c.spentBefore;
  const saveWall = () => { task.spent.wall_ms = c.spentBefore + (Date.now() - c.t0); };
  c.allow = K.allowCommands(P.wt, task.checks);
  const hb = S.startHeartbeat(root, task.id, c.lock, c.o.heartbeatMs || 30000, task);
  c.stopHeartbeat = () => hb.stop();
  task.denied = [];   // 이번 실행의 권한 거부만 보고한다(resume --allow 로 풀린 옛 거부를 다시 내밀지 않게)
  let message = c.firstMessage ? c.firstMessage(deadline) : kind === 'resume' ? Pr.resumeMessage(task, deadline, c.added) : Pr.taskPrompt(task, { root });
  for (;;) {
    const continuing = kind === 'continue';
    const cap = capHit(task, deadline, continuing);
    if (cap) return finish(c, 'capped', cap);
    const notes = takeNotes(c);
    if (notes) message = `${Pr.notesBlock(notes)}\n\n${message}`;
    task.turns = (task.turns || 0) + 1;
    log(`[harness] ${task.id} — turn ${task.turns} (${kind})`);
    const { r, newSessionId } = await callRunner(c, message, deadline);
    account(task, r, continuing, newSessionId);
    recordDenials(task, r.permission_denials);
    saveWall();
    S.log(root, task.id, { event: 'turn', n: task.turns, kind, session_id: r.session_id || null, session_confirmed: r.session_confirmed == null ? null : !!r.session_confirmed, cost_usd: r.cost_usd == null ? null : Number(r.cost_usd) || 0, tokens: r.tokens || null,
      is_error: !!r.is_error, error_kind: r.error_kind || null, error_message: r.error_message ? String(r.error_message).slice(0, 500) : null, permission_denials: (r.permission_denials || []).length });
    // [LP-48] 세션이 worktree 의 HEAD 를 작업 브랜치 밖으로 옮겼다 — 판정도 커밋도 하지 않고 멈춘다(worktree 는 finish 가 남긴다).
    if (fs.existsSync(P.wt) && !G.isWorktreeRoot(P.wt, task.branch)) {
      const head = G.git(P.wt, ['rev-parse', '--abbrev-ref', 'HEAD'], { allowFail: true }).out || '?';
      S.writeTask(root, task);
      return finish(c, 'error', `the worktree is no longer on ${task.branch} (the session moved HEAD to ${head}) — nothing was committed or judged; inspect ${P.wt}`);
    }
    checkpoint(c, `checkpoint ${task.turns}`);
    S.writeTask(root, task);

    const ek = r.is_error ? (r.error_kind || 'crash') : null;
    if (ek === 'quota') return finish(c, 'interrupted', `usage limit: ${String(r.error_message || r.final_text || '').slice(0, 300)}`);
    if (ek === 'auth') return finish(c, 'interrupted', `authentication failed: ${String(r.error_message || '').slice(0, 300)}`);
    if (ek === 'sandbox') return finish(c, 'error', String(r.error_message || 'sandbox refused tool execution').slice(0, 500));
    if (ek === 'timeout' || ek === 'aborted') return finish(c, 'capped', `wall clock ${task.caps.wall_min} min reached (the session was stopped)`);
    // 막혔다고 썼지만 그사이 사용자가 지시를 더했다 — 그 지시가 답일 수 있으니 BLOCKED.md 를 옮기고 한 턴 더 준다.
    if (fs.existsSync(P.blockedFile) && pendingNotes(root, task.id).length) {
      moveBlocked(P);
      message = Pr.notesTurnMessage(task, deadline); kind = 'continue';
      continue;
    }
    if (fs.existsSync(P.blockedFile)) {
      let why = ''; try { why = fs.readFileSync(P.blockedFile, 'utf8').trim(); } catch { /* 없음 */ }
      return finish(c, 'blocked', `the model reported the task cannot be done: ${why.replace(/\s+/g, ' ').slice(0, 400)}`);
    }
    // 러너 오류(crash · model · 그 밖)로 끝난 턴은 판정하지 않는다(H1) — 검사가 원래 초록이면 아무것도 안 한 턴이 done 이 된다.
    //   CLI 가 준 예산에서 멈췄으면 capped. 아니면 1회 다시(확인된 세션이면 이어서, 아니면 새 세션으로) · 연속 2회면 error.
    if (ek) {
      const why = String(r.error_message || r.stderr_tail || '').replace(/\s+/g, ' ').slice(0, 300);
      if (r.budget_exhausted) return finish(c, 'capped', `the CLI stopped at the budget it was given (${Pr.money(task.caps.budget_usd)} total, ${Pr.money(task.spent.cost_usd)} spent): ${why}`);
      c.errorStreak = (c.errorStreak || 0) + 1;
      S.log(root, task.id, { event: 'turn_error', kind: ek, streak: c.errorStreak });
      if (c.errorStreak >= 2) {
        return finish(c, 'error', task.session_id ? `the session ended with an error twice in a row (${ek}) — the work was not judged: ${why}`
          : `the session did not start (${ek}) — tried twice: ${why}`);
      }
      log(`[harness] ${task.id} — turn ended with an error (${ek}); not judged — retrying once`);
      if (task.session_id) { message = Pr.errorMessage(task, ek, why, deadline); kind = 'continue'; }
      else { message = Pr.taskPrompt(task, { root }); kind = 'initial'; }
      continue;
    }
    c.errorStreak = 0;

    let verdict = null;
    if (task.checks.commands.length) {
      const rj = await K.runJudged(P.wt, K.commandsForJudge(P.wt, task.checks), { timeoutMs: Math.min(c.o.checkTimeoutMs || task.checks.timeout_ms || K.CHECK_TIMEOUT_MS, Math.max(1000, deadline - Date.now() + 60000)), rerun: task.checks.rerun, serialRoot: task.checks.serial ? root : null });
      const judged = rj.judged;
      if (rj.flaky.length) { task.checks.flaky = [...new Set([...(task.checks.flaky || []), ...rj.flaky])]; S.log(root, task.id, { event: 'flaky', commands: rj.flaky }); log(`[harness] ${task.id} — flaky: ${rj.flaky.join(' ; ')} failed, then passed on rerun`); }
      task.checks.last = K.brief(judged);
      const v = K.judge(judged, task.checks.baseline, { notWorse: task.checks.source !== 'user' });
      task.checks.verdict = v.verdict;
      saveWall();
      S.log(root, task.id, { event: 'checks', verdict: v.verdict, pass: judged.pass, fail: judged.fail, ok: judged.ok });
      log(`[harness] ${task.id} — checks: ${v.verdict} (${judged.pass} pass / ${judged.fail} fail)`);
      if (v.verdict === 'fail') {
        const sig = K.signature(judged);
        if (sig === task.last_signature) return finish(c, 'stalled', `the same check failure twice in a row: ${K.firstAssertion(judged.results.find(x => !x.ok)).slice(0, 200)}`);
        task.last_signature = sig;
        S.writeTask(root, task);
        message = Pr.failMessage(task, judged, K.failureExcerpt(judged), deadline);
        kind = 'continue';
        continue;
      }
      verdict = v;
    }
    // 린트 — 테스트가 통과(또는 나빠지지 않음 · 검사 없음)일 때만. 실패하면 린트 출력을 작업자에게 돌려보낸다.
    //   [2026-10-13 영상 "쓰레기 코드 없애는 법"] 지시문은 무시될 수 있지만 실패하는 린트 명령은 무시할 수 없다.
    if (task.checks.lint) {
      const lt = task.checks.lint;
      const argv = K.lintArgv(lt.command, lt.files ? changedOutsideHarness(c).filter(f => fs.existsSync(path.join(P.wt, f))) : []);
      if (!argv) lt.last = { skipped: true, ok: true };
      else {
        const lr = await K.runCheck(P.wt, argv, { timeoutMs: Math.min(c.o.checkTimeoutMs || task.checks.timeout_ms || K.CHECK_TIMEOUT_MS, Math.max(1000, deadline - Date.now() + 60000)) });
        lt.last = { ok: lr.ok, exit_code: lr.exit_code, timed_out: lr.timed_out };
        saveWall();
        S.log(root, task.id, { event: 'lint', ok: lr.ok, exit_code: lr.exit_code });
        log(`[harness] ${task.id} — lint: ${lr.ok ? 'pass' : 'fail'}`);
        if (!lr.ok && (lt.files || lt.baseline_ok !== false)) {
          const sig = `lint:${K.firstAssertion(lr)}`;
          if (sig === task.last_signature) return finish(c, 'stalled', `the same lint failure twice in a row: ${K.firstAssertion(lr).slice(0, 200)}`);
          task.last_signature = sig;
          S.writeTask(root, task);
          message = Pr.lintFailMessage(task, lr, K.clip(lr.output, 1500, 2500), deadline);
          kind = 'continue';
          continue;
        }
      }
      S.writeTask(root, task);
    }
    // 중복 코드 — 새로 더한 코드가 있는 코드를 블록째 베꼈으면 위치를 알려 한 번 돌려보낸다(그 뒤로는 보고만 — 막지 않는다).
    //   [2026-10-16 사용자 지시 · 영상 「쓰레기 코드 없애는 법」] 명령을 막는 대신 결과의 군더더기를 잡는다. 끄기: dup_check: off.
    if (!task.checks.dup || task.checks.dup.on !== false) {
      let found = [];
      try { found = require('./dup').find(P.wt, task.base_commit, { minLines: task.checks.dup && task.checks.dup.min_lines }); } catch (e) { found = []; }
      task.checks.dup = { ...(task.checks.dup || { on: true }), last: found, sent: !!(task.checks.dup && task.checks.dup.sent) };
      S.log(root, task.id, { event: 'dup', blocks: found.length });
      if (found.length && !task.checks.dup.sent) {
        task.checks.dup.sent = true;
        S.writeTask(root, task);
        log(`[harness] ${task.id} — duplicate code: ${found.length} block(s) — sending back once`);
        message = Pr.dupMessage(task, found, deadline); kind = 'continue';
        continue;
      }
      S.writeTask(root, task);
    }
    // 끝나려던 참에 전달하지 않은 추가 지시가 있으면 그것을 반영하는 턴을 한 번 더(지시는 다음 턴 머리에 붙는다).
    if (pendingNotes(root, task.id).length) { message = Pr.notesTurnMessage(task, deadline); kind = 'continue'; continue; }
    // done 은 무언가를 했을 때만(H2): 기준 대비 .harness/ 밖 변경이 0 이거나 마지막 말이 질문이면 — 검사가 초록이어도 — 1회 넛지.
    const changed = changedOutsideHarness(c);
    const asked = Pr.isQuestion(r.final_text);
    if ((!changed.length || asked) && !task.nudged) {
      task.nudged = true; S.writeTask(root, task);
      S.log(root, task.id, { event: 'nudge', why: !changed.length ? 'no_changes' : 'question' });
      message = !changed.length ? Pr.noChangeMessage(task) : Pr.nudgeMessage(task); kind = 'continue';
      continue;
    }
    if (!changed.length) {
      return finish(c, 'failed', `no files changed outside .harness/ — ${!verdict ? 'there are no checks' : verdict.verdict === 'pass' ? 'the checks pass' : 'the checks are not worse'}, but nothing was done (the model was nudged once)`);
    }
    if (!verdict) return finish(c, 'done', 'no trusted checks — finished on the model\'s own report (verify the evidence yourself)');
    return finish(c, 'done', verdict.why);
  }
}

// ── 끝 ─────────────────────────────────────────────────────────────────
const isTestFile = f => TEST_FILE_RE.test(f);
function outsideGit(task, wt) {
  const untracked = G.statusEntries(wt).filter(e => e.code === '??').map(e => e.path);
  return { ignored_changed: G.ignoredChanges(wt, task.worktree_include || []), untracked_left: untracked };
}
// 검사 정의 파일 변경(M6) — 기준 커밋과 결과 브랜치의 내용을 git 에서 읽어 비교한다.
function checksModifiedOf(root, task, changedAll) {
  const ch = task.checks;
  if (!ch || !(ch.commands || []).length) return [];
  const show = ref => rel => { const r = G.git(root, ['show', `${ref}:${rel}`], { allowFail: true }); return r.ok ? r.out : null; };
  return K.checksModified({ changed: changedAll, commands: ch.commands, source: ch.source, from: ch.from, readBase: show(task.base_commit), readHead: show(task.branch) });
}

function finish(c, status, reason) {
  const { root, P, task, log } = c;
  if (c.stopHeartbeat) c.stopHeartbeat();
  task.status = status; task.reason = reason;
  task.spent.wall_ms = c.spentBefore + (Date.now() - c.t0);
  const wtExists = fs.existsSync(P.wt);
  if (wtExists) {
    try { checkpoint(c, status, { throwOnError: true }); }
    catch (e) { task.commit_error = e.message; }
    try { task.outside_git = outsideGit(task, P.wt); } catch { /* 보고용 */ }
    task.decisions = readDecisions(path.join(P.workDir, 'DECISIONS.md'));
  }
  try {
    if (task.base_commit && G.branchExists(root, task.branch)) {
      const all = G.diffNames(root, task.base_commit, task.branch);
      task.files_changed = all.filter(f => !f.startsWith('.harness/')).length;
      // 변경 규모 — 리뷰할 근거(판정이 아니라 표시). [2026-10-13 영상] AI 는 더하기 기계다 — 얼마나 더했는지 보이게.
      const st = G.git(root, ['diff', '--shortstat', task.base_commit, task.branch, '--', '.', ':(exclude).harness'], { allowFail: true }).out;
      task.diff = { insertions: Number((/(\d+) insertion/.exec(st) || [])[1] || 0), deletions: Number((/(\d+) deletion/.exec(st) || [])[1] || 0),
        added_files: G.diffNames(root, task.base_commit, task.branch, ['--diff-filter=A']).filter(f => !f.startsWith('.harness/')).length };
      task.tests_modified = G.diffNames(root, task.base_commit, task.branch, ['--diff-filter=MD']).filter(isTestFile);
      task.checks_modified = checksModifiedOf(root, task, all);
      task.head = G.headSha(root, task.branch);
    }
  } catch { /* 보고용 */ }
  if (wtExists) {
    if (task.commit_error) task.worktree_kept = `commit failed: ${task.commit_error.slice(0, 200)}`;
    else {
      // 무시된 파일(git 밖)이 바뀌었으면 지우지 않는다(M4) — 지우면 보고 직후 산출물이 사라진다.
      const rm = G.removeWorktree(root, P.wt, { include: task.worktree_include || [] });
      if (!rm.ok) task.worktree_kept = rm.error; else delete task.worktree_alt;
    }
  }
  if (task.owner) task.owner.heartbeat_at = S.nowIso();
  S.writeTask(root, task);
  S.log(root, task.id, { event: 'end', status, reason, cost_usd: task.spent.cost_usd, wall_ms: task.spent.wall_ms, worktree_kept: task.worktree_kept || null });
  if (c.lock) c.lock.release();
  log(`[harness] ${task.id} — ${status}`);
  const res = result(task);
  res.report = report(task, P);
  return res;
}

// 작업자가 묻지 않고 고른 갈림길(.harness/<id>/DECISIONS.md 의 `## <n>. <분기점>` 절) → [{ title, body[] }]. 파일이 없으면 [] — 갈림길이 없었다.
//   [2026-10-16 사용자 지시] 시작 때 묻지 않고 끝까지 스스로 판단하고, 어떤 분기점에서 무엇을 골라 어떻게 됐는지는 완성 뒤에 정리해 보인다.
function readDecisions(file) {
  let text; try { text = fs.readFileSync(file, 'utf8'); } catch { return []; }
  const out = [];
  for (const sec of text.split(/^##[ \t]+/m).slice(1)) {
    const lines = sec.split(/\r?\n/);
    const title = lines[0].replace(/^\d+[.)][ \t]*/, '').trim().slice(0, 200);
    if (title) out.push({ title, body: lines.slice(1).map(l => l.trim()).filter(Boolean).map(l => l.slice(0, 400)).slice(0, 8) });
  }
  if (!out.length && text.trim()) out.push({ title: '(형식 없이 적힌 결정)', body: text.split(/\r?\n/).map(l => l.trim()).filter(l => l && !/^#/.test(l)).slice(0, 12) });
  return out.slice(0, 30);
}
function decisionLines(task, ko) {
  const d = task.decisions;
  if (!Array.isArray(d)) return [];   // 이 기능 전의 작업
  if (!d.length) return [ko ? '결정 분기점: 없음 — 지시와 저장소만으로 모든 선택이 정해졌다' : 'decision points: none — the instructions and the repository settled every choice'];
  // [2026-10-16 자동 이슈 #14] "resume 으로 지시" 라고만 적어 실제로 할 수 있는 방법을 몰랐다 — 명령을 그대로 적는다.
  const how = `node harness/cli.js resume ${task.id} --note "<바꿀 내용>"  ·  긴 지시는 파일로: node harness/cli.js note ${task.id} --file <파일> 뒤 resume ${task.id}`;
  const out = [ko ? `결정 분기점: ${d.length}곳 — 작업자가 묻지 않고 고른 갈림길이다. 다르게 하려면(끝난 작업도 된다): ${how}`
    : `decision points: ${d.length} — forks the worker decided without asking. To change one (done tasks too): ${how.replace('<바꿀 내용>', '<what to change>').replace('<파일>', '<file>').replace('긴 지시는 파일로', 'longer instructions')}`];
  d.forEach((x, i) => { out.push(`  ${i + 1}. ${x.title}`); for (const l of x.body) out.push(`     ${l}`); });
  return out;
}

function result(task) {
  const ch = task.checks || null, last = ch && (ch.last || null);
  return { id: task.id, status: task.status, reason: task.reason, branch: task.branch, commit: task.head || (task.commits || []).slice(-1)[0] || null,
    base_branch: task.base_branch, base_commit: task.base_commit, session_id: task.session_id,
    checks: { source: ch ? ch.source : 'none', ok: last ? last.ok : null, pass: last ? last.pass : null, fail: last ? last.fail : null, baseline_fail: ch && ch.baseline ? ch.baseline.fail : null,
      verdict: ch && ch.verdict || null, baseline_warning: ch && ch.baseline_warning || null },
    cost_usd: task.spent.cost_usd, tokens: task.spent.tokens, continuations: task.spent.continuations, wall_ms: task.spent.wall_ms, unknown_cost_calls: task.spent.unknown_cost_calls || 0,
    files_changed: task.files_changed == null ? null : task.files_changed, tests_modified: task.tests_modified || [], checks_modified: task.checks_modified || [],
    secrets_excluded: task.secrets_excluded || [], commit_skipped: task.commit_skipped || [], outside_git: task.outside_git,
    worktree: task.worktree_kept ? task.worktree : null, worktree_kept: task.worktree_kept || null, merge_commit: task.merge_commit || null, revert_commit: task.revert_commit || null,
    docs: task.docs || [], decisions: task.decisions || null };
}

const listOf = (a, n) => `${a.slice(0, n).join(', ')}${a.length > n ? ` … (+${a.length - n})` : ''}`;
// [2026-10-01 · Python 서비스 저장소] 무인 거부로 끝난 작업 — 무엇이 거부됐고, 무엇을 허용해 이어 가면 되는지 한 줄로.
// 거부된 명령 → 허용 규칙 제안(rules) · 허용할 수 없어 사용자가 직접 해야 하는 명령(byUser).
function allowSuggestions(task) {
  const rules = [], byUser = [];
  for (const d of task.denied || []) {
    const s = Po.suggestAllowRule(d.tool, d.command);
    if (s) { for (const r of s) if (!rules.includes(r) && !(task.allow || []).includes(r)) rules.push(r); }
    else if (d.tool === 'Bash' || d.tool === 'PowerShell') byUser.push(d.command);
  }
  return { rules, byUser };
}
// 보고 맨 위의 한국어 요약 — 보고는 사용자에게 그대로 전해진다(스킬). 상태 · 판정 근거 · 비용, 다음에 할 일, 주의할 것.
const STATUS_KO = { done: '완료', failed: '실패', blocked: '막힘 — 사용자가 필요하다', capped: '상한 도달', stalled: '정체 — 같은 실패가 반복됐다',
  interrupted: '중단됨(이어 갈 수 있다)', error: '오류', running: '실행 중' };
const KIND_KO = { image: '이미지', video: '영상', audio: '음성', pdf: 'PDF', office: '문서', text: '텍스트', file: '파일' };
function summaryKo(task) {
  const ch = task.checks || { commands: [] }, last = ch.last, s = task.spent;
  let evidence;
  if (!(ch.commands || []).length) evidence = '신뢰할 검사 없음 — 결과는 모델의 보고뿐이니 직접 확인하세요';
  else if (!last) evidence = '검사를 돌리지 못함';
  else if (last.ok) evidence = `검사 통과 (${last.pass} 통과 / ${last.fail} 실패)`;
  else if (ch.verdict === 'not_worse') evidence = `검사가 작업 전부터 빨갰고 더 나빠지지 않음 (${last.pass} 통과 / ${last.fail} 실패) — 이 작업을 증명하지는 못함`;
  else evidence = `검사 실패 (${last.pass} 통과 / ${last.fail} 실패)`;
  const cost = task.runtime === 'codex' ? `${s.tokens || 0} 토큰` : Pr.money(s.cost_usd);
  const files = task.files_changed == null ? '' : ` · 바뀐 파일 ${task.files_changed}개${task.diff ? `(+${task.diff.insertions}/-${task.diff.deletions}줄)` : ''}`;
  const out = [`요약: ${STATUS_KO[task.status] || task.status} — ${evidence}${files} · ${cost} · ${((s.wall_ms || 0) / 60000).toFixed(1)}분`];
  const id = task.id, cli = 'node harness/cli.js';
  let next;
  if (task.status === 'done') next = `받아들이려면(사용자가 말한 뒤) ${cli} accept ${id} · 버리려면 ${cli} cancel ${id}`;
  else if (task.status === 'running') next = `멈추려면 ${cli} stop ${id}`;
  else {
    const { rules } = allowSuggestions(task);
    if (rules.length && task.runtime !== 'codex') next = `거부된 명령을 허용해 이어 가려면(허용은 사용자가 정한다) ${cli} resume ${id} ${rules.map(r => `--allow "${r}"`).join(' ')} · 버리려면 ${cli} cancel ${id}`;
    else if (task.status === 'capped') next = `상한을 늘려 이어 가려면 ${cli} resume ${id} --budget-usd <새 총액> --wall-min <새 총액> · 버리려면 ${cli} cancel ${id}`;
    else if (task.status === 'blocked') next = `.harness/${id}/BLOCKED.md 의 이유를 보고 ${cli} resume ${id} 로 이어 가거나 ${cli} cancel ${id}`;
    else next = `이어 가려면 ${cli} resume ${id} · 버리려면 ${cli} cancel ${id}`;
  }
  if ((task.attachments || []).length) out.push(`첨부: ${task.attachments.length}개 — ${task.attachments.map(a => `${a.name}(${KIND_KO[a.kind] || a.kind}${a.frames.length && a.kind === 'video' ? ` · 장면 ${a.frames.length}장` : ''}${a.transcript ? ' · 전사' : ''})`).join(', ')}`);
  out.push(`다음: ${next}`);
  const warn = [];
  if ((task.checks_modified || []).length) warn.push(`작업이 검사 정의를 고쳤다(${task.checks_modified.join(', ')}) — 통과를 그대로 믿지 마세요`);
  if ((task.tests_modified || []).length) warn.push(`기존 테스트 파일을 고쳤다(${listOf(task.tests_modified, 5)})`);
  if ((task.secrets_excluded || []).length) warn.push('비밀 파일은 커밋하지 않았다(worktree 에만 있다)');
  if (ch.baseline_warning) warn.push('작업 전 검사가 요약 없이 실패했다 — worktree 환경 문제일 수 있다');
  const dupLeft = ch.dup && ch.dup.on !== false ? (ch.dup.last || []) : [];
  if (dupLeft.length) warn.push(`새 코드에 중복 ${dupLeft.length}곳이 남았다(한 번 돌려보냈다) — ${dupLeft.slice(0, 3).map(b => `${b.file}:${b.start}-${b.end} ↔ ${b.other}`).join(' · ')}`);
  if ((ch.dropped || []).length) warn.push(`작업 전부터 시간 초과라 판정에서 뺐다(${ch.dropped.map(d => d.command).join(' ; ')}) — 이 검사는 이 작업을 판정하지 않았다`);
  if ((ch.flaky || []).length) warn.push(`불안정한 검사가 있다(${ch.flaky.length}개) — 다시 돌리면 통과한다`);
  if (ch.lint && ch.lint.last && !ch.lint.last.ok) warn.push('린트가 실패한 채 끝났다(작업 전부터 빨간 저장소 전체 린트)');
  const attNotes = (task.attachments || []).filter(a => a.notes.length).map(a => `${a.name}: ${a.notes[0]}`);
  if (attNotes.length) warn.push(`첨부를 다 바꾸지 못했다 — ${attNotes.join(' / ')}`);
  if (warn.length) out.push(`주의: ${warn.join(' · ')}`);
  return out;
}
function deniedLines(task) {
  const denied = task.denied || [];
  if (!denied.length) return [];
  const out = [`denied commands (unattended — nobody could approve them): ${listOf(denied.map(d => d.tool === 'Bash' ? d.command : `${d.tool}: ${d.command}`), 20)}`];
  if (task.runtime === 'codex') { out.push('  (Codex: its sandbox refused these — --allow has no effect there; run them yourself or resume under the Claude runtime)'); return out; }
  const { rules, byUser } = allowSuggestions(task);
  if (rules.length) out.push(`to continue with them allowed: node harness/cli.js resume ${task.id} ${rules.map(r => `--allow "${r}"`).join(' ')}`);
  if (byUser.length) out.push(`  cannot be allowed (git writes, shells or wrappers) — these must be done by the user: ${listOf(byUser, 10)}`);
  return out;
}
// ── 한국어 보고 ─────────────────────────────────────────────────────────
// [2026-10-13 사용자 보고] 한국어로 맡긴 작업의 결과가 영어로 나왔다(요약 세 줄 아래가 전부 영어) — 작업 언어가 Korean 이면 보고 전체를 한국어로.
//   명령 · 경로 · 브랜치 · 숫자는 원문 그대로. 이유(task.reason)는 하네스가 쓰는 문장만 옮기고, 모델 · 도구가 쓴 원문은 그대로 붙인다.
const REASON_KO = [
  [/^all checks pass$/, () => '모든 검사 통과'],
  [/^no trusted checks — finished on the model's own report \(verify the evidence yourself\)$/, () => '신뢰할 검사 없음 — 모델의 보고로 끝났다(증거를 직접 확인하세요)'],
  [/^baseline was red — (.*)$/s, (m) => `작업 전부터 검사가 빨갰다 — ${m[1]}`],
  [/^the model reported the task cannot be done: (.*)$/s, (m) => `모델이 할 수 없다고 보고했다: ${m[1]}`],
  [/^the same check failure twice in a row: (.*)$/s, (m) => `같은 검사 실패가 두 번 연속: ${m[1]}`],
  [/^cost (\S+) reached the budget (\S+)$/, (m) => `비용 ${m[1]} 이 예산 ${m[2]} 에 닿았다`],
  [/^tokens (\d+) reached the token budget (\d+)$/, (m) => `토큰 ${m[1]} 이 토큰 예산 ${m[2]} 에 닿았다`],
  [/^wall clock (\S+) min reached(.*)$/, (m) => `시간 상한 ${m[1]}분에 닿았다${m[2] ? ' (세션을 멈췄다)' : ''}`],
  [/^(\d+) continuations used \(max (\d+)\)$/, (m) => `이어 가기 ${m[1]}회를 다 썼다(최대 ${m[2]})`],
  [/^the same lint failure twice in a row: (.*)$/s, (m) => `같은 린트 실패가 두 번 연속: ${m[1]}`],
  [/^usage limit: (.*)$/s, (m) => `사용량 한도: ${m[1]}`],
  [/^authentication failed: (.*)$/s, (m) => `인증 실패: ${m[1]}`],
  [/^no files changed outside \.harness\/ — (.*)$/s, () => '.harness/ 밖에서 바뀐 파일이 없다 — 한 번 재촉했지만 아무것도 하지 않았다'],
  [/^the worktree is no longer on (\S+) \(the session moved HEAD to (\S+)\)(.*)$/s, (m) => `worktree 가 ${m[1]} 에서 벗어났다(세션이 HEAD 를 ${m[2]} 로 옮겼다) — 커밋도 판정도 하지 않았다`],
  [/^stopped by the user(.*)$/, (m) => `사용자가 멈췄다${m[1] ? m[1].replace('(process tree of pid', '(프로세스 트리 끝냄: pid').replace('(its process was already gone)', '(프로세스는 이미 없었다)') : ''}`],
];
function lintState(lt, lang) {
  const ko = lang === 'ko', last = lt.last || {};
  const st = !lt.last ? (ko ? '돌리지 않음' : 'not run') : last.skipped ? (ko ? '건너뜀 — 바뀐 파일이 없다' : 'skipped — no changed files') : last.ok ? (ko ? '통과' : 'PASS') : (ko ? '실패' : 'FAIL');
  const base = !lt.files && lt.baseline_ok === false ? (ko ? ' · 저장소 전체 린트가 작업 전부터 실패했다(기준선) — 막지 않고 보고만 한다. lint_command 에 {files} 를 쓰면 바꾼 파일만 본다' : ' · the whole-repo lint already failed before the task (baseline) — reported, not blocking; put {files} in lint_command to lint only changed files') : '';
  return `${st} — \`${lt.command}\`${base}`;
}
function reasonKo(r) {
  const s = String(r || '');
  for (const [re, f] of REASON_KO) { const m = re.exec(s); if (m) return f(m); }
  return s;
}
function reportKo(task, P) {
  const s = task.spent, c = task.caps, ch = task.checks || { source: 'none', commands: [] };
  const cli = 'node harness/cli.js';
  const L = [`harness ${task.id} — ${task.status.toUpperCase()}`, ...summaryKo(task), `이유: ${reasonKo(task.reason)}`, ...decisionLines(task, true)];
  L.push(`브랜치: ${task.branch}${task.head ? ` @ ${task.head.slice(0, 10)}` : ''} (${task.base_branch || 'detached HEAD'} @ ${String(task.base_commit || '').slice(0, 10)} 에서) — 사용자 브랜치는 그대로다.`);
  if (!ch.commands.length) L.push('검사: 없음 — 신뢰할 검사가 이 작업을 판정하지 않았다. 결과는 모델의 보고에만 기대고 있다.');
  else {
    const last = ch.last, base = ch.baseline, pf = x => `${x.ok ? '통과' : '실패'} — ${x.pass} 통과 / ${x.fail} 실패`;
    L.push(`검사(${ch.source === 'user' ? '사용자가 준 것' : '저장소에서 찾은 것'}): ${ch.commands.map(K.display).join(' ; ')}`);
    L.push(`  마지막: ${last ? pf(last) : '돌리지 않음'}${base ? ` · 작업 전 기준선: ${pf(base)}` : ''}`);
    if (ch.baseline_warning) L.push('  경고: 작업 전 검사가 읽을 수 있는 요약 없이 실패했다 — 새 worktree 의 환경 문제(의존성 미설치 등)일 수 있다. .worktreeinclude 에 필요한 파일을 적으세요');
    const cm = task.checks_modified || [];
    L.push(`작업이 고친 검사 정의: ${cm.length ? `${cm.join(', ')} — 확인하세요. 검사가 바뀌면 일을 하지 않고도 통과할 수 있다` : '없음'}`);
  }
  if ((ch.dropped || []).length) L.push(`판정에서 뺀 검사(저장소에서 찾은 것 · 작업 전부터 시간 초과 — 새 worktree 의 환경 문제일 수 있다): ${ch.dropped.map(d => d.command).join(' ; ')}`);
  if (ch.lint) L.push(`린트: ${lintState(ch.lint, 'ko')}`);
  if (ch.dup && ch.dup.on !== false) L.push(`중복 코드: ${(ch.dup.last || []).length ? (ch.dup.last || []).map(b => `${b.file}:${b.start}-${b.end}(${b.lines}줄) ↔ ${b.other}`).join(' · ') : '없음'}${ch.dup.sent ? ' (작업자에게 한 번 돌려보냈다)' : ''}`);
  L.push(`바뀐 파일: ${task.files_changed == null ? '?' : `${task.files_changed}개`}`);
  if (task.diff) L.push(`변경 규모: +${task.diff.insertions} / -${task.diff.deletions} 줄 · 새 파일 ${task.diff.added_files}개`);
  if ((ch.flaky || []).length) L.push(`불안정한 검사(실패했다가 다시 돌리니 통과 — 작업자에게 돌려보내지 않았다): ${ch.flaky.join(' ; ')}`);
  L.push(`고친 기존 테스트 파일: ${(task.tests_modified || []).length ? task.tests_modified.join(', ') : '없음'}`);
  if ((task.secrets_excluded || []).length) L.push(`커밋하지 않은 비밀 파일(worktree 에만 있고 병합되지 않는다): ${listOf(task.secrets_excluded, 20)}`);
  if ((task.commit_skipped || []).length) L.push(`git 이 넣지 못해 커밋에서 빠진 경로: ${listOf(task.commit_skipped, 20)}`);
  if (task.commit_failures) L.push(`실패한 체크포인트 커밋: ${task.commit_failures}회 (마지막: ${String(task.last_commit_error || '').replace(/\s+/g, ' ').slice(0, 200)})`);
  const og = task.outside_git || { ignored_changed: [], untracked_left: [] };
  if (og.ignored_changed.length || og.untracked_left.length) {
    L.push('git 밖(브랜치에 없다 — git 으로 되돌릴 수 없다):');
    if (og.ignored_changed.length) L.push(`  worktree 에서 바뀐 무시된 파일: ${listOf(og.ignored_changed, 20)}`);
    if (og.untracked_left.length) L.push(`  커밋되지 않고 남은 파일: ${listOf(og.untracked_left, 20)}`);
  } else L.push('git 밖 변경: 없음');
  const unknown = s.unknown_cost_calls || 0;
  const money = task.runtime === 'codex' ? 'Codex 는 비용(USD)을 알려 주지 않는다' : `${Pr.money(s.cost_usd)} / 예산 ${Pr.money(c.budget_usd)}`;
  L.push(`사용: ${money}${unknown ? ` (+ 비용을 모르는 호출 ${unknown}회 — 셈에 없음)` : ''}${s.tokens ? ` · 토큰 ${s.tokens}${c.token_budget ? ` / ${c.token_budget}` : ''}` : ''} · 이어 가기 ${s.continuations} / ${c.max_continuations} · ${(s.wall_ms / 60000).toFixed(1)}분 / ${c.wall_min}분`);
  L.push(task.worktree_kept ? `작업 폴더(worktree) 남김: ${task.worktree} (${task.worktree_kept})` : '작업 폴더(worktree): 지움 — 모두 브랜치에 커밋됐다');
  L.push(`계획: 브랜치의 .harness/${task.id}/PLAN.md · 결정: DECISIONS.md · 기록: ${P.logFile}`);
  if ((task.attachments || []).length) L.push(`첨부(git 밖 · ${path.join(P.dir, 'attachments', 'INDEX.md')}): ${task.attachments.map(a => `${a.name} [${KIND_KO[a.kind] || a.kind}${a.frames.length ? ` · ${a.frames.length}장` : ''}${a.transcript ? ' · 전사' : ''}${a.notes.length ? ` · 참고 ${a.notes.length}건` : ''}]`).join(', ')}`);
  if ((task.docs || []).length) L.push(`명세 문서(메인 체크아웃에서 읽음 · accept 때 이 작업과 연결): ${task.docs.join(', ')}`);
  if ((task.allow || []).length) L.push(`이 작업에 허용한 명령(go --allow · worker_allow): ${task.allow.join(', ')}${task.runtime === 'codex' ? ' — Codex 에는 효과 없음(샌드박스가 정한다)' : ''}`);
  if (['interrupted', 'capped', 'stalled', 'failed', 'error', 'blocked'].includes(task.status)) {
    L.push(`이어 가기: ${cli} resume ${task.id}${task.status === 'capped' ? ' --budget-usd <새 총액> --wall-min <새 총액> --max-continuations <새 총액>' : ''}`);
    if (task.status === 'capped') L.push(`  (상한은 작업 전체의 총액이다 — 더하는 값이 아니다. 지금까지: ${Pr.money(s.cost_usd)} · ${(s.wall_ms / 60000).toFixed(1)}분 · 이어 가기 ${s.continuations}회)`);
    const denied = task.denied || [];
    if (denied.length) {
      L.push(`거부된 명령(무인 실행 — 승인할 사람이 없었다): ${listOf(denied.map(d => d.tool === 'Bash' ? d.command : `${d.tool}: ${d.command}`), 20)}`);
      if (task.runtime === 'codex') L.push('  (Codex: 샌드박스가 거부했다 — --allow 는 효과가 없다. 직접 돌리거나 Claude 런타임으로 이어 가세요)');
      else {
        const { rules, byUser } = allowSuggestions(task);
        if (rules.length) L.push(`허용해 이어 가려면: ${cli} resume ${task.id} ${rules.map(r => `--allow "${r}"`).join(' ')}`);
        if (byUser.length) L.push(`  허용할 수 없는 것(git 쓰기 · 셸 · 래퍼) — 사용자가 직접 해야 한다: ${listOf(byUser, 10)}`);
      }
    }
  }
  if (task.status === 'blocked') {
    L.push(task.worktree_kept ? `직접 이어 받으려면: worktree 가 ${task.worktree} 에 남아 있다(브랜치 ${task.branch})`
      : `직접 이어 받으려면: git worktree add ../${path.basename(P.root || '.') || 'repo'}-${task.id} ${task.branch}`);
  }
  L.push(`받아들이기: ${cli} accept ${task.id}${task.base_branch ? '' : ' --into <브랜치>'}   (${task.base_branch || '<브랜치>'} 에 병합 — 사용자가 말할 때만)`);
  L.push(`취소: ${cli} cancel ${task.id}`);
  return L.join('\n');
}

function report(task, P) {
  if (task.language === 'Korean') return reportKo(task, P);
  const s = task.spent, c = task.caps, ch = task.checks || { source: 'none', commands: [] };
  const lines = [`harness ${task.id} — ${task.status.toUpperCase()}`, ...summaryKo(task), `why: ${task.reason}`, ...decisionLines(task, false)];
  lines.push(`branch: ${task.branch}${task.head ? ` @ ${task.head.slice(0, 10)}` : ''} (from ${task.base_branch || 'detached HEAD'} @ ${String(task.base_commit || '').slice(0, 10)}) — your branch is untouched.`);
  if (!ch.commands.length) lines.push('checks: none found — no trusted check judged this work; the result rests on the model\'s own report.');
  else {
    const last = ch.last, base = ch.baseline;
    lines.push(`checks (${ch.source}): ${ch.commands.map(K.display).join(' ; ')}`);
    lines.push(`  last: ${last ? `${last.ok ? 'PASS' : 'FAIL'} — ${last.pass} pass / ${last.fail} fail` : 'not run'}${base ? ` · baseline before the task: ${base.ok ? 'PASS' : 'FAIL'} — ${base.pass} pass / ${base.fail} fail` : ''}`);
    if (ch.baseline_warning) lines.push(`  warning: ${ch.baseline_warning}`);
    const cm = task.checks_modified || [];
    lines.push(`check definitions modified by the task: ${cm.length ? `${cm.join(', ')} — review these; a changed check can pass without the work being done` : 'none'}`);
  }
  if ((ch.dropped || []).length) lines.push(`checks dropped (auto-detected, timed out before the task — likely the new worktree's environment): ${ch.dropped.map(d => d.command).join(' ; ')}`);
  if (ch.lint) lines.push(`lint: ${lintState(ch.lint, 'en')}`);
  if (ch.dup && ch.dup.on !== false) lines.push(`duplicate code: ${(ch.dup.last || []).length ? (ch.dup.last || []).map(b => `${b.file}:${b.start}-${b.end} (${b.lines} lines) duplicates ${b.other}`).join(' · ') : 'none'}${ch.dup.sent ? ' (sent back to the worker once)' : ''}`);
  lines.push(`changed files: ${task.files_changed == null ? '?' : task.files_changed}`);
  if (task.diff) lines.push(`diff: +${task.diff.insertions} -${task.diff.deletions} lines · ${task.diff.added_files} new files`);
  if ((ch.flaky || []).length) lines.push(`flaky checks (failed, then passed on rerun — not sent back to the worker): ${ch.flaky.join(' ; ')}`);
  lines.push(`existing test files modified: ${(task.tests_modified || []).length ? task.tests_modified.join(', ') : 'none'}`);
  if ((task.secrets_excluded || []).length) lines.push(`secret files NOT committed (left in the worktree; never merged): ${listOf(task.secrets_excluded, 20)}`);
  if ((task.commit_skipped || []).length) lines.push(`paths git could not add (left out of the commits): ${listOf(task.commit_skipped, 20)}`);
  if (task.commit_failures) lines.push(`checkpoint commits that failed: ${task.commit_failures} (last: ${String(task.last_commit_error || '').replace(/\s+/g, ' ').slice(0, 200)})`);
  const og = task.outside_git || { ignored_changed: [], untracked_left: [] };
  if (og.ignored_changed.length || og.untracked_left.length) {
    lines.push('outside git (not in the branch; cannot be undone by git):');
    if (og.ignored_changed.length) lines.push(`  ignored files changed in the worktree: ${listOf(og.ignored_changed, 20)}`);
    if (og.untracked_left.length) lines.push(`  untracked files left uncommitted: ${listOf(og.untracked_left, 20)}`);
  } else lines.push('outside git: nothing');
  const unknown = s.unknown_cost_calls || 0;
  // Codex 는 USD 를 보고하지 않는다 — "$0.00 of $20.00" 은 공짜처럼 읽힌다(2026-09-30 실측). 토큰만 적는다.
  const money = task.runtime === 'codex' ? 'cost in USD not reported by Codex' : `${Pr.money(s.cost_usd)} of ${Pr.money(c.budget_usd)}`;
  lines.push(`spent: ${money}${unknown ? ` (+ cost unknown for ${unknown} call${unknown > 1 ? 's' : ''} — not counted)` : ''}${s.tokens ? ` · ${s.tokens} tokens${c.token_budget ? ` of ${c.token_budget}` : ''}` : ''} · ${s.continuations} continuations of ${c.max_continuations} · ${(s.wall_ms / 60000).toFixed(1)} min of ${c.wall_min}`);
  lines.push(task.worktree_kept ? `worktree kept: ${task.worktree} (${task.worktree_kept})` : 'worktree: removed (everything is committed on the branch)');
  lines.push(`plan: .harness/${task.id}/PLAN.md on the branch · decisions: DECISIONS.md · log: ${P.logFile}`);
  if ((task.attachments || []).length) lines.push(`attachments (outside git; ${path.join(P.dir, 'attachments', 'INDEX.md')}): ${task.attachments.map(a => `${a.name} [${a.kind}${a.frames.length ? ` · ${a.frames.length} frames` : ''}${a.transcript ? ' · transcript' : ''}${a.notes.length ? ' · ' + a.notes.length + ' note(s)' : ''}]`).join(', ')}`);
  if ((task.docs || []).length) lines.push(`spec documents (read from the main checkout; linked to this task on accept): ${task.docs.join(', ')}`);
  if ((task.allow || []).length) lines.push(`allowed for this task (go --allow · worker_allow): ${task.allow.join(', ')}${task.runtime === 'codex' ? ' — no effect on Codex (its sandbox governs what runs)' : ''}`);
  if (['interrupted', 'capped', 'stalled', 'failed', 'error', 'blocked'].includes(task.status)) {
    lines.push(`resume: node harness/cli.js resume ${task.id}${task.status === 'capped' ? ' --budget-usd <new total> --wall-min <new total> --max-continuations <new total>' : ''}`);
    if (task.status === 'capped') lines.push(`  (caps are totals for the whole task, not additions — so far: ${Pr.money(s.cost_usd)} · ${(s.wall_ms / 60000).toFixed(1)} min · ${s.continuations} continuations)`);
    lines.push(...deniedLines(task));
  }
  if (task.status === 'blocked') {
    lines.push(task.worktree_kept ? `to take it over by hand: the worktree is kept at ${task.worktree} (branch ${task.branch})`
      : `to take it over by hand: git worktree add ../${path.basename(P.root || '.') || 'repo'}-${task.id} ${task.branch}`);
  }
  lines.push(`accept: node harness/cli.js accept ${task.id}${task.base_branch ? '' : ' --into <branch>'}   (merges into ${task.base_branch || '<branch>'} only when you say so)`);
  lines.push(`cancel: node harness/cli.js cancel ${task.id}`);
  return lines.join('\n');
}

module.exports = { addNote, pendingNotes, go, resume, finish, result, report, capsFrom, isTestFile, getRun, DEFAULTS, RESUMABLE };
