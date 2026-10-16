'use strict';
// v5 status · gc — 작업 목록(주인 생존) · 겹침(두 작업이 같은 파일을 바꿈) · 메인 체크아웃의 미커밋 변경을 주인별로.
//   주인 없는 변경은 목록만 보인다 — 지우거나 커밋하지 않는다.
const fs = require('node:fs'), path = require('node:path');
const S = require('./state'), G = require('./git');

const FINAL = new Set(['accepted', 'cancelled']);
const norm = f => { const p = String(f).replace(/\\/g, '/').replace(/^\.\//, ''); return S.IS_WIN ? p.toLowerCase() : p; };

function taskFiles(root, t) {
  const files = new Set();
  if (t.base_commit && t.branch && G.branchExists(root, t.branch)) for (const f of G.diffNames(root, t.base_commit, t.branch)) files.add(f);
  if (t.worktree && fs.existsSync(t.worktree)) for (const e of G.dirtyFiles(t.worktree)) files.add(e.path);
  return [...files].filter(f => !f.startsWith('.harness/'));
}

function status(o) {
  const root = S.mainRoot((o && o.root) || process.cwd());
  const now = Date.now();
  const tasks = S.listTasks(root).map(t => {
    const running = t.status === 'running';
    const alive = running && S.ownerAlive(t.owner);
    const files = FINAL.has(t.status) ? [] : taskFiles(root, t);
    const hb = t.owner && t.owner.heartbeat_at ? Date.parse(t.owner.heartbeat_at) : null;
    return { id: t.id, status: t.status, reason: t.reason || '', goal: String(t.goal || '').split(/\r?\n/)[0].slice(0, 100), runtime: t.runtime,
      owner: t.owner ? { pid: t.owner.pid, host: t.owner.host, alive, heartbeat_at: t.owner.heartbeat_at || null, heartbeat_age_s: hb ? Math.round((now - hb) / 1000) : null } : null,
      stale: running && !alive, branch: t.branch, branch_exists: !!(t.branch && G.branchExists(root, t.branch)), base_branch: t.base_branch,
      files_changed: files.length, files, cost_usd: t.spent ? t.spent.cost_usd : 0, worktree: t.worktree && fs.existsSync(t.worktree) ? t.worktree : null,
      merge_commit: t.merge_commit || null, updated_at: t.updated_at };
  });
  // 겹침: 끝나지 않은(병합·취소 전) 작업들이 같은 파일을 바꿈.
  const byFile = new Map();
  for (const t of tasks) {
    if (FINAL.has(t.status) || !t.branch_exists) continue;
    for (const f of t.files) { const k = norm(f); if (!byFile.has(k)) byFile.set(k, { file: f, tasks: [] }); byFile.get(k).tasks.push(t.id); }
  }
  const overlaps = [...byFile.values()].filter(x => x.tasks.length > 1).sort((a, b) => a.file.localeCompare(b.file));
  // 메인 체크아웃의 미커밋 변경 → 세션별 · 주인 없음.
  const main = G.mainWorktree(root);
  const dirty = G.dirtyFiles(main).map(e => e.path).filter(f => !f.startsWith('.harness-worktrees/'));
  const sessions = S.readSessions(root);
  const bySession = [], owned = new Set();
  for (const s of sessions) {
    const mine = new Set(s.files.map(norm));
    const files = dirty.filter(f => mine.has(norm(f)));
    if (!files.length) continue;
    files.forEach(f => owned.add(f));
    bySession.push({ session_id: s.session_id, runtime: s.runtime, updated_at: s.updated_at, files });
  }
  const unowned = dirty.filter(f => !owned.has(f));
  // 출력 언어 — 저장소 블록 reply_language(부른 체크아웃 · 메인), 없으면 지정 없음(영어). [2026-10-13] 결과가 영어로 나온다는 보고.
  let language = null; try { const K = require('./checks'); language = K.yamlString(main, 'reply_language') || K.yamlString(root, 'reply_language'); } catch { /* 블록 없음 */ }
  const cost_total = Math.round(tasks.reduce((a, t) => a + (Number(t.cost_usd) || 0), 0) * 100) / 100;
  return { root, checkout: main, branch: G.currentBranch(main), language, cost_total, tasks: tasks.map(({ files, ...t }) => t), broken: S.listBrokenTasks(root), overlaps, uncommitted: { by_session: bySession, unowned } };
}

function formatStatusKo(s) {
  const L = [`저장소: ${s.root} (${s.branch || 'detached HEAD'})`];
  if (!s.tasks.length) L.push('작업: 없음');
  else {
    L.push(`작업 (${s.tasks.length}):`);
    for (const t of s.tasks) {
      const own = t.status === 'running' ? (t.owner && t.owner.alive ? ` · 실행 중 pid ${t.owner.pid}(신호 ${t.owner.heartbeat_age_s}초 전)` : ' · 주인 프로세스 없음 — resume 하세요') : '';
      L.push(`  ${t.id}  ${t.status}${own} · ${t.branch}${t.branch_exists ? '' : ' (없음)'} · 파일 ${t.files_changed}개 · $${Number(t.cost_usd || 0).toFixed(2)} — ${t.goal}`);
    }
    L.push(`누적 비용: 작업 ${s.tasks.length}개 · $${Number(s.cost_total || 0).toFixed(2)}`);
  }
  for (const b of s.broken || []) L.push(`  ${b.id}  손상 — task.json 을 읽을 수 없다(${b.task_file}) · 기록: ${b.log} — ${b.goal}`);
  if (s.overlaps.length) {
    L.push('겹침(열린 작업 둘 이상이 같은 파일을 바꿨다 — 두 번째를 들일 때 충돌한다):');
    for (const o of s.overlaps) L.push(`  ! ${o.file} — ${o.tasks.join(', ')}`);
  }
  const u = s.uncommitted;
  if (!u.by_session.length && !u.unowned.length) L.push(`${s.checkout} 의 미커밋 변경: 없음`);
  else {
    L.push(`${s.checkout} 의 미커밋 변경:`);
    for (const x of u.by_session) L.push(`  세션 ${String(x.session_id).slice(0, 8)}${x.runtime ? ` (${x.runtime})` : ''}: ${x.files.join(', ')}`);
    if (u.unowned.length) L.push(`  주인을 모름(보여 주기만 — 하네스는 커밋하거나 지우지 않는다): ${u.unowned.join(', ')}`);
  }
  return L.join('\n');
}
function formatStatus(s) {
  if (s.language === 'Korean') return formatStatusKo(s);
  const L = [`repository: ${s.root} (on ${s.branch || 'detached HEAD'})`];
  if (!s.tasks.length) L.push('tasks: none');
  else {
    L.push(`tasks (${s.tasks.length}):`);
    for (const t of s.tasks) {
      const own = t.status === 'running' ? (t.owner && t.owner.alive ? ` · owner pid ${t.owner.pid} alive (heartbeat ${t.owner.heartbeat_age_s}s ago)` : ' · OWNER DEAD — resume it') : '';
      L.push(`  ${t.id}  ${t.status}${own} · ${t.branch}${t.branch_exists ? '' : ' (gone)'} · ${t.files_changed} files · $${Number(t.cost_usd || 0).toFixed(2)} — ${t.goal}`);
    }
    L.push(`spent across ${s.tasks.length} tasks: $${Number(s.cost_total || 0).toFixed(2)}`);
  }
  for (const b of s.broken || []) L.push(`  ${b.id}  BROKEN — task.json cannot be read (${b.task_file}) · its log: ${b.log} — ${b.goal}`);
  if (s.overlaps.length) {
    L.push('overlaps (the same file changed by more than one open task — integrating the second will conflict):');
    for (const o of s.overlaps) L.push(`  ! ${o.file} — ${o.tasks.join(', ')}`);
  }
  const u = s.uncommitted;
  if (!u.by_session.length && !u.unowned.length) L.push(`uncommitted changes in ${s.checkout}: none`);
  else {
    L.push(`uncommitted changes in ${s.checkout}:`);
    for (const x of u.by_session) L.push(`  session ${String(x.session_id).slice(0, 8)}${x.runtime ? ` (${x.runtime})` : ''}: ${x.files.join(', ')}`);
    if (u.unowned.length) L.push(`  no known owner (listed only; the harness never commits or deletes them): ${u.unowned.join(', ')}`);
  }
  return L.join('\n');
}

// ── git 밖 변경 ────────────────────────────────────────────────────────
// worktree 의 무시된(gitignore) 파일 중 .worktreeinclude 복사분(복사 때와 같은 내용)이 아닌 것 — worktree 를 지우면 함께 사라지고
// git 으로 되살릴 수 없다. include: task.worktree_include([{path, sha1}]); 목록에 없는 경로는 메인 체크아웃의 같은 파일과 비교한다.
const EXPAND_MAX = 2000;
function listFiles(wt, rel, acc) {
  let ents = []; try { ents = fs.readdirSync(path.join(wt, rel), { withFileTypes: true }); } catch { return acc; }
  for (const e of ents) {
    if (acc.length > EXPAND_MAX) return acc;
    const r = rel ? `${rel.replace(/\/$/, '')}/${e.name}` : e.name;
    if (e.isDirectory()) listFiles(wt, r, acc); else acc.push(r);
  }
  return acc;
}
function ignoredChanged(root, wt, include) {
  const inc = new Map((include || []).map(x => [norm(x.path), x.sha1]));
  let rootInc = null;
  const copyOnly = rel => {
    const h = G.sha1(path.join(wt, rel));
    if (!h) return false;
    if (inc.has(norm(rel))) return inc.get(norm(rel)) === h;
    if (!rootInc) rootInc = new Set(G.worktreeIncludeFiles(root).map(norm));
    return rootInc.has(norm(rel)) && G.sha1(path.join(root, rel)) === h;
  };
  // 1차 목록은 git.js 의 ignoredChanges(복사 기록과 같은 내용이면 뺌)가 있으면 그것 — 여기서는 폴더를 펼치고
  //   기록이 없는 worktree(임시 revert · 손으로 만든 것)를 위해 메인 체크아웃의 같은 파일과 한 번 더 비교한다.
  const cand = typeof G.ignoredChanges === 'function' ? G.ignoredChanges(wt, include || [])
    : G.statusEntries(wt, { ignored: true }).filter(e => e.code === '!!').map(e => e.path);
  const out = [];
  for (const p of cand) {
    if (!p.endsWith('/')) { if (!copyOnly(p)) out.push(p); continue; }
    const files = listFiles(wt, p, []);
    if (files.length > EXPAND_MAX) { out.push(p); continue; }   // 너무 크다 — 폴더째 "바뀜" 으로 본다
    for (const f of files) if (!copyOnly(f)) out.push(f);
  }
  return out;
}
const ignoredWhy = files => `ignored files changed (outside git; removing the worktree would delete them): ${files.slice(0, 10).join(', ')}${files.length > 10 ? ` … (+${files.length - 10})` : ''} — copy what you need, then remove it with git worktree remove --force`;

// 작업 worktree 를 지워도 되면 지우고 {ok:true}, 아니면 {ok:false, why}. 무시된 파일이 바뀌었으면 남긴다.
function removeIfSafe(root, wt, include) {
  const ign = fs.existsSync(wt) ? ignoredChanged(root, wt, include) : [];
  if (ign.length) return { ok: false, why: ignoredWhy(ign), ignored: ign };
  const rm = G.removeWorktree(root, wt);
  return rm.ok ? { ok: true } : { ok: false, why: rm.error };
}

const ID_PREFIX_RE = /^(t-\d{8}-\d{6}-[0-9a-f]{4})-/;
// gc: 끝난 작업의 깨끗한 worktree 제거 · 더러운 것 · git 밖 파일이 바뀐 것 · 통합 중인 것(산 잠금)은 남김 · 죽은 잠금 해제 · git worktree prune.
function gc(o) {
  const root = S.mainRoot((o && o.root) || process.cwd());
  const P = S.paths(root);
  const removed = [], kept = [];
  const known = new Set();
  const lockHeldWhy = name => `lock ${name} is held by a live owner (an accept/cancel/restore/resume is in progress) — skipped`;
  for (const t of S.listTasks(root)) {
    const tp = S.taskPaths(root, t.id);
    known.add(norm(tp.wt));
    if (!fs.existsSync(tp.wt)) continue;
    if (t.status === 'running' && S.ownerAlive(t.owner)) { kept.push({ id: t.id, worktree: tp.wt, why: 'task is running' }); continue; }
    // 지우는 동안 task-<id> 잠금을 잡는다 — 잡을 수 없으면(산 주인) 통합이 이 worktree 를 쓰는 중이다.
    let h = null;
    try { h = S.acquire(root, `task-${t.id}`); }
    catch (e) { if (e.code !== 'LOCK_HELD') throw e; kept.push({ id: t.id, worktree: tp.wt, why: lockHeldWhy(`task-${t.id}`) }); continue; }
    try {
      const r = removeIfSafe(root, tp.wt, t.worktree_include);
      if (r.ok) removed.push({ id: t.id, worktree: tp.wt }); else kept.push({ id: t.id, worktree: tp.wt, why: r.why, ...(r.ignored ? { ignored_changed: r.ignored } : {}) });
    } finally { h.release(); }
  }
  // 작업에 속하지 않는 하네스 worktree(중단된 임시 revert 등): 등록돼 있고 깨끗하면 제거.
  //   임시 revert worktree(<id>-cancel-* · <id>-restore-*)는 merge 잠금 아래에서만 쓰인다 — gc 도 merge 잠금을 잡고 지운다.
  let extra = []; try { extra = fs.readdirSync(P.worktreesDir); } catch { /* 없음 */ }
  extra = extra.filter(name => !known.has(norm(path.join(P.worktreesDir, name))));
  // worktree_links 의 링크(.harness-worktrees/<이름> → 메인의 형제 폴더)는 worktree 가 아니다 — 보지도 보고하지도 않는다.
  extra = extra.filter(name => { try { return !fs.lstatSync(path.join(P.worktreesDir, name)).isSymbolicLink(); } catch { return false; } });
  let mh = null, mergeHeld = false;
  if (extra.length) {
    try { mh = S.acquire(root, 'merge'); } catch (e) { if (e.code !== 'LOCK_HELD') throw e; mergeHeld = true; }
  }
  try {
    for (const name of extra) {
      const wt = path.join(P.worktreesDir, name);
      if (!G.worktreeRegistered(root, wt)) { kept.push({ id: null, worktree: wt, why: 'not a registered worktree (left alone)' }); continue; }
      if (mergeHeld) { kept.push({ id: null, worktree: wt, why: lockHeldWhy('merge') }); continue; }
      const m = ID_PREFIX_RE.exec(name);
      if (m && S.lockLive(root, `task-${m[1]}`)) { kept.push({ id: null, worktree: wt, why: lockHeldWhy(`task-${m[1]}`) }); continue; }
      const r = removeIfSafe(root, wt, null);
      if (r.ok) removed.push({ id: null, worktree: wt }); else kept.push({ id: null, worktree: wt, why: r.why, ...(r.ignored ? { ignored_changed: r.ignored } : {}) });
    }
  } finally { if (mh) mh.release(); }
  const locks = S.removeDeadLocks(root);
  G.git(root, ['worktree', 'prune'], { allowFail: true });
  return { root, removed, kept, locks_removed: locks };
}
function formatGc(g) {
  return [`gc: ${g.root}`, `removed worktrees: ${g.removed.length ? g.removed.map(x => x.id || x.worktree).join(', ') : 'none'}`,
    ...g.kept.map(k => `kept ${k.id || k.worktree}: ${k.why}`), `dead locks released: ${g.locks_removed.length ? g.locks_removed.join(', ') : 'none'}`].join('\n');
}

module.exports = { status, formatStatus, gc, formatGc, taskFiles, ignoredChanged, ignoredWhy, removeIfSafe };
