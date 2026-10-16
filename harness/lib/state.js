'use strict';
// v5 상태 — 경로 · 작업 기록 · 잠금 · 로그. 저장 위치는 <git-common-dir>/harness/ (모든 worktree 가 공유, 커밋되지 않음).
//   쓰기는 하네스만 한다. 작업 기록은 임시 파일 + rename 으로 원자적으로 쓴다.
//   잠금은 mkdir 원자 잠금 + owner.json {pid, host, at, token}. 같은 호스트의 죽은 pid 잠금은 빼앗는다.
const fs = require('node:fs'), path = require('node:path'), os = require('node:os'), crypto = require('node:crypto');
const { spawnSync } = require('node:child_process');

const HOST = os.hostname();
const IS_WIN = process.platform === 'win32';
const SLEEP_CELL = new Int32Array(new SharedArrayBuffer(4));
function sleepSync(ms) { if (ms > 0) Atomics.wait(SLEEP_CELL, 0, 0, ms); }
const nowIso = () => new Date().toISOString();

// ── 경로 ───────────────────────────────────────────────────────────────
function gitOut(cwd, args) {
  const r = spawnSync('git', args, { cwd, encoding: 'utf8', windowsHide: true });
  return r.status === 0 ? String(r.stdout || '').trim() : null;
}
// 저장소 최상위(현재 worktree 의). 없으면 NOT_A_REPO.
function repoRoot(start) {
  const dir = path.resolve(start || process.cwd());
  const top = gitOut(dir, ['rev-parse', '--show-toplevel']);
  if (!top) throw Object.assign(new Error(`not a git repository: ${dir}`), { code: 'NOT_A_REPO' });
  return path.resolve(top);
}
// 주 worktree(메인 체크아웃). 하네스의 모든 경로는 여기에 묶는다 — 연결된 worktree 안에서 불려도 같은 작업을 가리키게.
function mainRoot(start) {
  const top = repoRoot(start);
  const list = gitOut(top, ['worktree', 'list', '--porcelain']);
  const first = list && /^worktree (.+)$/m.exec(list);
  return first ? path.resolve(first[1].trim()) : top;
}
// 한 root 의 common dir 은 프로세스 동안 바뀌지 않는다 — 기록 한 줄마다 git 을 띄우지 않게 기억한다(Windows 에서 spawn 1회 ≈ 30ms).
const COMMON = new Map();
function commonDir(root) {
  const key = path.resolve(root);
  if (COMMON.has(key)) return COMMON.get(key);
  const c = gitOut(key, ['rev-parse', '--git-common-dir']);
  if (!c) throw Object.assign(new Error(`not a git repository: ${root}`), { code: 'NOT_A_REPO' });
  const v = path.resolve(key, c);
  COMMON.set(key, v);
  return v;
}
function paths(root0) {
  // 실경로로 — git 이 알려 주는 경로와 같은 표기여야 비교 · 상대 경로가 맞는다(심볼릭 링크 · Windows 짧은 이름).
  const root = require('../hooks/_common').real(root0);
  const common = commonDir(root), h = path.join(common, 'harness');
  return { root, commonDir: common, harnessDir: h, tasksDir: path.join(h, 'tasks'), sessionsDir: path.join(h, 'sessions'),
    locksDir: path.join(h, 'locks'), worktreesDir: path.join(root, '.harness-worktrees'), excludeFile: path.join(common, 'info', 'exclude') };
}
function taskPaths(root, id) {
  const P = paths(root), dir = path.join(P.tasksDir, id), wt = path.join(P.worktreesDir, id), relWork = `.harness/${id}`;
  return { ...P, id, dir, taskFile: path.join(dir, 'task.json'), logFile: path.join(dir, 'log.jsonl'), archiveDir: path.join(dir, 'archive'),
    branch: `harness/${id}`, wt, relWork, workDir: path.join(wt, '.harness', id), planFile: path.join(wt, '.harness', id, 'PLAN.md'),
    blockedFile: path.join(wt, '.harness', id, 'BLOCKED.md') };
}

// t-<yyyymmdd-HHMMss>-<4hex>
function newId(d) {
  d = d || new Date();
  const p = n => String(n).padStart(2, '0');
  return `t-${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}-${p(d.getHours())}${p(d.getMinutes())}${p(d.getSeconds())}-${crypto.randomBytes(2).toString('hex')}`;
}
const ID_RE = /^t-\d{8}-\d{6}-[0-9a-f]{4}$/;
const validId = id => typeof id === 'string' && ID_RE.test(id);

// ── 파일 ───────────────────────────────────────────────────────────────
function readJson(file, fallback) { try { return JSON.parse(fs.readFileSync(file, 'utf8')); } catch { return fallback; } }
// 임시 파일 + rename. Windows 에서 읽는 쪽이 파일을 잡고 있으면 rename 이 EPERM/EBUSY 로 실패한다 → 짧게 재시도.
//   noMkdir: 폴더를 다시 만들지 않는다(잠금의 owner.json — 빼앗겨 사라진 잠금 폴더를 되살리면 주인이 둘이 된다).
function writeJsonAtomic(file, obj, opts) {
  if (!(opts && opts.noMkdir)) fs.mkdirSync(path.dirname(file), { recursive: true });
  const tmp = `${file}.${process.pid}.${crypto.randomBytes(3).toString('hex')}.tmp`;
  fs.writeFileSync(tmp, JSON.stringify(obj, null, 2) + '\n');
  for (let i = 0; ; i++) {
    try { fs.renameSync(tmp, file); return; }
    catch (e) {
      if (i >= 8 || !/^(EPERM|EBUSY|EACCES)$/.test(e.code)) { try { fs.unlinkSync(tmp); } catch { /* 없음 */ } throw e; }
      sleepSync(25 * (i + 1));
    }
  }
}
function appendJsonl(file, obj) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.appendFileSync(file, JSON.stringify({ at: nowIso(), ...obj }) + '\n');
}

// ── 작업 기록 ─────────────────────────────────────────────────────────
function readTask(root, id) { return readJson(taskPaths(root, id).taskFile, null); }
function writeTask(root, task) {
  task.updated_at = nowIso();
  writeJsonAtomic(taskPaths(root, task.id).taskFile, task);
  return task;
}
function log(root, id, event) { appendJsonl(taskPaths(root, id).logFile, event); }
function readLog(root, id) {
  let text = ''; try { text = fs.readFileSync(taskPaths(root, id).logFile, 'utf8'); } catch { return []; }
  return text.split(/\r?\n/).filter(Boolean).map(l => { try { return JSON.parse(l); } catch { return null; } }).filter(Boolean);
}
function listTasks(root) {
  const { tasksDir } = paths(root);
  let names = []; try { names = fs.readdirSync(tasksDir); } catch { return []; }
  return names.filter(validId).sort().map(id => readTask(root, id)).filter(Boolean);
}
function newTask(fields) {
  const at = nowIso();
  return { id: null, goal: '', runtime: 'claude', model: 'opus', effort: null, status: 'running', reason: '', base_branch: null, base_commit: null,
    branch: null, worktree: null, session_id: null, owner: null,
    checks: { source: 'none', commands: [], baseline: null, last: null },
    caps: { budget_usd: 20, token_budget: null, wall_min: 120, max_continuations: 8 },
    spent: { cost_usd: 0, tokens: 0, continuations: 0, wall_ms: 0 },
    commits: [], merge_commit: null, revert_commit: null,
    outside_git: { ignored_changed: [], untracked_left: [] }, tests_modified: [],
    created_at: at, updated_at: at, ...fields };
}

// ── 프로세스 ──────────────────────────────────────────────────────────
function pidAlive(pid) {
  const n = Number(pid);
  if (!Number.isInteger(n) || n <= 0) return false;
  try { process.kill(n, 0); } catch (e) { return e.code === 'EPERM'; }
  // Linux: 끝났지만 부모가 거두지 않은 프로세스(좀비)도 kill(0) 에는 살아 있다 — /proc 의 상태가 Z 면 끝난 것이다.
  if (process.platform === 'linux') { try { if (/^\d+ \(.*\) Z /s.test(fs.readFileSync(`/proc/${n}/stat`, 'utf8'))) return false; } catch { /* /proc 없음 — kill(0) 을 믿는다 */ } }
  // macOS 등(/proc 없음) — ps 의 상태가 Z(좀비)면 끝난 것이다. [2026-10-13 CI 실측] stop 이 "could not stop" 으로 실패했다.
  else if (process.platform !== 'win32') {
    try { const r = require('node:child_process').spawnSync('ps', ['-o', 'stat=', '-p', String(n)], { encoding: 'utf8', timeout: 5000 }); if (r.status === 0 && /^\s*Z/.test(r.stdout)) return false; } catch { /* ps 없음 — kill(0) 을 믿는다 */ }
  }
  return true;
}
// 주인이 살아 있는가 — 같은 호스트면 pid 로, 다른 호스트면 판단할 수 없으니 살아 있다고 본다(오래된 at 은 예외).
const FOREIGN_STALE_MS = 24 * 3600 * 1000;
const isSelf = owner => !!owner && owner.pid === process.pid && (!owner.host || owner.host === HOST);
function ownerAlive(owner) {
  if (!owner || owner.pid == null) return false;
  if (owner.host && owner.host !== HOST) {
    const at = Date.parse(owner.heartbeat_at || owner.at || '');
    return !(at && Date.now() - at > FOREIGN_STALE_MS);
  }
  return pidAlive(owner.pid);
}

// ── 잠금 ───────────────────────────────────────────────────────────────
// mkdir 은 원자적이다. owner.json 을 쓰기 전에 죽은 잠금(owner 없음)은 10초가 지나면 버려진 것으로 본다.
const ORPHAN_MS = 10000;
function lockDir(root, name) { return path.join(paths(root).locksDir, `${name}.lock`); }
function lockOwner(root, name) { return readJson(path.join(lockDir(root, name), 'owner.json'), null); }
// {stale, owner} — owner 는 판정 때 본 owner.json(없으면 null). 빼앗기는 이 owner 를 들고 가 그사이 바뀌지 않았는지 확인한다.
function staleInfo(dir) {
  const owner = readJson(path.join(dir, 'owner.json'), null);
  if (!owner) {
    let st = null; try { st = fs.statSync(dir); } catch { return { stale: false, owner: null }; }
    return { stale: Date.now() - st.mtimeMs > ORPHAN_MS, owner: null };
  }
  return { stale: !ownerAlive(owner), owner };
}
const lockStale = dir => staleInfo(dir).stale;
// 잠금이 있고 주인이 살아 있으면(또는 막 만들어지는 중이면) true.
function lockLive(root, name) {
  const dir = lockDir(root, name);
  if (!fs.existsSync(dir)) return false;
  return !staleInfo(dir).stale;
}
// 빼앗기(TOCTOU 방지): stale 판정과 옮기기 사이에 다른 이가 먼저 빼앗아 새로 잡을 수 있다 — 그 산 잠금을 지우면 주인이 둘이 된다.
//   1) 빼앗기 전용 뮤텍스(`<lock>.steal`, mkdir 원자)를 잡은 이만 빼앗는다 — 빼앗는 이들끼리 직렬.
//   2) 뮤텍스 아래에서 다시 판정하고, 지금 owner.json 의 토큰이 판정 때 본 것(seen)과 같을 때만 옮긴다.
//   3) 옮긴 뒤(grave) 토큰을 한 번 더 보고, 그사이 바뀌었으면 되돌린다.
//   seen 을 주지 않으면(undefined) 뮤텍스 아래 재판정만 한다. 뮤텍스가 오래 남아 있으면(주인이 그 짧은 구간에서 죽음) 치운다.
const STEAL_ORPHAN_MS = 5000;
function takeOver(dir, seen) {
  const mutex = `${dir}.steal`;
  try { fs.mkdirSync(mutex); }
  catch (e) {
    try { if (Date.now() - fs.statSync(mutex).mtimeMs > STEAL_ORPHAN_MS) fs.rmSync(mutex, { recursive: true, force: true }); } catch { /* 없음 */ }
    return false;   // 다른 이가 빼앗는 중 — 이번 차례는 양보
  }
  try {
    const now = staleInfo(dir);
    if (!now.stale) return false;
    const tok = x => (x ? String(x.token || `${x.pid}@${x.host}@${x.at}`) : null);
    if (seen !== undefined && tok(seen) !== tok(now.owner)) return false;
    const grave = `${dir}.stale-${process.pid}-${crypto.randomBytes(3).toString('hex')}`;
    try { fs.renameSync(dir, grave); } catch { return false; }
    if (tok(readJson(path.join(grave, 'owner.json'), null)) !== tok(now.owner)) {
      try { fs.renameSync(grave, dir); } catch { /* 그사이 새 잠금이 생겼다 — 그것을 건드리지 않는다 */ }
      return false;
    }
    try { fs.rmSync(grave, { recursive: true, force: true }); } catch { /* 남아도 무해 */ }
    return true;
  } finally {
    try { fs.rmdirSync(mutex); } catch { /* 없음 */ }
  }
}
function acquire(root, name, opts) {
  const o = opts || {}, waitMs = o.waitMs == null ? 0 : o.waitMs, pollMs = o.pollMs || 50;
  const dir = lockDir(root, name), deadline = Date.now() + waitMs;
  fs.mkdirSync(path.dirname(dir), { recursive: true });
  let staleMiss = 0;
  for (;;) {
    let made = false;
    try { fs.mkdirSync(dir); made = true; }
    catch (e) { if (e.code !== 'EEXIST' && e.code !== 'EPERM') throw e; }
    if (made) {
      const owner = { pid: process.pid, host: HOST, at: nowIso(), token: crypto.randomBytes(6).toString('hex'), name, ...(o.meta || {}) };
      try { writeJsonAtomic(path.join(dir, 'owner.json'), owner, { noMkdir: true }); }
      catch (e) {
        if (e.code === 'ENOENT') continue;   // owner.json 을 쓰기 전에 폴더가 사라졌다(빼앗김) — 처음부터 다시
        try { fs.rmSync(dir, { recursive: true, force: true }); } catch { /* 고아로 남으면 나중에 빼앗긴다 */ }
        throw e;
      }
      return makeHandle(root, name, dir, owner);
    }
    const st = staleInfo(dir);
    if (st.stale) {
      if (o.beforeTakeover) o.beforeTakeover(name);
      if (takeOver(dir, st.owner)) { if (o.onTakeover) o.onTakeover(name); continue; }
      // 빼앗기지 못했다(다른 이가 빼앗는 중이거나 이미 새 주인) — 잠깐 뒤 다시 본다. 판정이 계속 stale 이면 상한까지.
      if (++staleMiss <= 40) { sleepSync(pollMs); continue; }
    }
    if (Date.now() >= deadline) {
      const owner = readJson(path.join(dir, 'owner.json'), null);
      throw Object.assign(new Error(`lock "${name}" is held by pid ${owner ? owner.pid : '?'}@${owner ? owner.host : '?'} since ${owner ? owner.at : '?'}`), { code: 'LOCK_HELD', owner });
    }
    sleepSync(pollMs + Math.floor(Math.random() * pollMs));
  }
}
// owner.json 읽기: 없음(ENOENT)과 잠깐 못 읽음(Windows 에서 touch 의 rename 과 겹침)을 구별한다.
function readOwnerFile(dir) {
  const file = path.join(dir, 'owner.json');
  for (let i = 0; ; i++) {
    try { return { exists: true, owner: JSON.parse(fs.readFileSync(file, 'utf8')) }; }
    catch (e) {
      if (e.code === 'ENOENT') return { exists: false, owner: null };
      if (i >= 4) return { exists: true, owner: null };
      sleepSync(20);
    }
  }
}
function makeHandle(root, name, dir, owner) {
  let released = false;
  return {
    name, dir, owner,
    touch() { if (released) return; try { const cur = readJson(path.join(dir, 'owner.json'), null); if (cur && cur.token === owner.token) writeJsonAtomic(path.join(dir, 'owner.json'), { ...cur, at: nowIso() }, { noMkdir: true }); } catch { /* 무시 */ } },
    release() {
      if (released) return; released = true;
      // 자기 토큰이 확인될 때만 지운다. owner.json 이 없거나(빼앗긴 뒤 새 주인이 mkdir 만 한 상태) 못 읽으면 남의 것일 수 있다 —
      // 지우지 않는다(우리 것이라면 이 프로세스가 끝난 뒤 죽은 잠금으로 빼앗긴다).
      const cur = readOwnerFile(dir);
      if (!cur.owner || cur.owner.token !== owner.token) return;
      try { fs.rmSync(dir, { recursive: true, force: true }); } catch { /* 남으면 다음에 빼앗긴다 */ }
    },
  };
}
function withLockSync(root, name, fn, opts) {
  const h = acquire(root, name, opts);
  try { return fn(h); } finally { h.release(); }
}
async function withLock(root, name, fn, opts) {
  const h = acquire(root, name, opts);
  try { return await fn(h); } finally { h.release(); }
}
function listLocks(root) {
  const { locksDir } = paths(root);
  let names = []; try { names = fs.readdirSync(locksDir); } catch { return []; }
  return names.filter(n => n.endsWith('.lock')).map(n => {
    const dir = path.join(locksDir, n), owner = readJson(path.join(dir, 'owner.json'), null);
    return { name: n.slice(0, -5), dir, owner, stale: lockStale(dir) };
  });
}
function removeDeadLocks(root) {
  const removed = [];
  const { locksDir } = paths(root);
  let names = []; try { names = fs.readdirSync(locksDir); } catch { return removed; }
  for (const n of names) {
    const dir = path.join(locksDir, n);
    if (/\.stale-/.test(n)) { try { fs.rmSync(dir, { recursive: true, force: true }); } catch { /* 무시 */ } continue; }
    if (n.endsWith('.lock.steal')) {   // 빼앗기 뮤텍스 — 주인이 그 짧은 구간에서 죽어 남은 것만
      try { if (Date.now() - fs.statSync(dir).mtimeMs > STEAL_ORPHAN_MS) fs.rmSync(dir, { recursive: true, force: true }); } catch { /* 무시 */ }
      continue;
    }
    if (!n.endsWith('.lock')) continue;
    const st = staleInfo(dir);
    if (st.stale && takeOver(dir, st.owner)) removed.push(n.slice(0, -5));
  }
  return removed;
}

// ── heartbeat ─────────────────────────────────────────────────────────
// 작업 소유 잠금과 task.owner 를 주기적으로 갱신한다. 타이머는 프로세스를 붙잡지 않는다.
//   task 객체를 주면 그 객체(루프가 들고 있는 것)를 갱신해 쓴다 — 파일을 읽고 덮어 루프의 최신 값을 지우지 않는다.
function startHeartbeat(root, id, handle, everyMs, task) {
  const beat = () => {
    try {
      const t = task || readTask(root, id);
      if (t && t.owner && t.owner.pid === process.pid) { t.owner.heartbeat_at = nowIso(); writeTask(root, t); }
      if (handle) handle.touch();
    } catch { /* heartbeat 실패는 작업을 멈추지 않는다 */ }
  };
  const timer = setInterval(beat, everyMs || 30000);
  if (timer.unref) timer.unref();
  return { beat, stop() { clearInterval(timer); } };
}
const ownerRecord = () => ({ pid: process.pid, host: HOST, heartbeat_at: nowIso() });

// ── 세션 기록 (A3 의 track 훅이 쓴다; 여기서는 읽기만) ────────────────────
function readSessions(root) {
  const { sessionsDir } = paths(root);
  let names = []; try { names = fs.readdirSync(sessionsDir); } catch { return []; }
  return names.filter(n => n.endsWith('.json')).map(n => {
    const s = readJson(path.join(sessionsDir, n), null);
    if (!s || typeof s !== 'object') return null;
    return { session_id: s.session_id || n.slice(0, -5), runtime: s.runtime || null, files: Array.isArray(s.files) ? s.files.filter(f => typeof f === 'string') : [], updated_at: s.updated_at || null };
  }).filter(Boolean);
}

module.exports = {
  HOST, IS_WIN, sleepSync, nowIso, repoRoot, mainRoot, commonDir, paths, taskPaths, newId, validId, ID_RE,
  readJson, writeJsonAtomic, appendJsonl, readTask, writeTask, log, readLog, listTasks, newTask,
  pidAlive, ownerAlive, isSelf, lockDir, lockOwner, takeOver, acquire, withLock, withLockSync, listLocks, removeDeadLocks, lockStale, staleInfo, lockLive,
  startHeartbeat, ownerRecord, readSessions,
};
