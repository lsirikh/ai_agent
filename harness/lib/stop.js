'use strict';
// stop — 실행 중인 작업을 멈추는 공식 방법.
//   [버그 2026-10-01 · Python 서비스 저장소] cancel 이 "task is still running; wait for it or stop it first" 라고만 안내해, 사용자는 go 를 띄운
//   셸 프로세스를 죽였다 → 작업은 영구히 running · OWNER DEAD 로 남고, 죽은 프로세스의 자식이 worktree 폴더를 붙잡아 cancel 이 반쯤 실패했다.
//   stop 은 그 작업의 주인 프로세스 트리(go/resume 과 그 워커)를 끝내고, 지금까지의 작업을 결과 브랜치에 커밋하고, 상태를 interrupted 로
//   바꾼다. 그 뒤에는 resume(이어서) 이나 cancel(버리기)을 평소처럼 쓸 수 있다.
const fs = require('node:fs'), path = require('node:path');
const { spawnSync } = require('node:child_process');
const S = require('./state'), G = require('./git');

function usage(m) { return Object.assign(new Error(m), { code: 'USAGE' }); }

// POSIX: 작업자(claude · codex)는 detached — 자기 프로세스 그룹으로 뜬다(proc.spawnCapture). 주인의 그룹만 죽이면 작업자가 살아남아
//   worktree 를 계속 고친다(Linux 실측 2026-10-02). ps 로 자손을 모두 찾아 각자와 그 그룹에 신호를 보낸다.
function descendants(pid) {
  const r = spawnSync('ps', ['-A', '-o', 'pid=,ppid='], { encoding: 'utf8' });
  if (r.status !== 0) return [];
  const kids = new Map();
  for (const line of String(r.stdout).split('\n')) {
    const m = /^\s*(\d+)\s+(\d+)\s*$/.exec(line);
    if (m) { const p = Number(m[2]); if (!kids.has(p)) kids.set(p, []); kids.get(p).push(Number(m[1])); }
  }
  const out = [], todo = [Number(pid)];
  while (todo.length) for (const k of kids.get(todo.pop()) || []) if (!out.includes(k)) { out.push(k); todo.push(k); }
  return out;
}
function signalAll(pids, sig) {
  for (const p of pids) {
    try { process.kill(-p, sig); } catch { /* 그룹 리더가 아니다 */ }
    try { process.kill(p, sig); } catch { /* 이미 끝났다 */ }
  }
}
async function killTree(pid) {
  if (process.platform === 'win32') { spawnSync('taskkill', ['/PID', String(pid), '/T', '/F'], { stdio: 'ignore', windowsHide: true }); return; }
  const all = [Number(pid), ...descendants(pid)];   // 주인이 먼저 끝나면 자손의 부모가 바뀐다 — 신호 전에 모은다
  signalAll(all, 'SIGTERM');
  for (let i = 0; i < 25 && all.some(S.pidAlive); i++) await new Promise(r => setTimeout(r, 200));
  signalAll(all.filter(S.pidAlive), 'SIGKILL');
}

async function stop(o) {
  const root = S.mainRoot(o.root);
  if (!S.validId(o.id)) throw usage('invalid task id');
  const task = S.readTask(root, o.id);
  if (!task) throw usage(`unknown task ${o.id}`);
  const P = S.taskPathsFor(root, task);
  if (task.status !== 'running') return { task, ok: true, stopped: false, reason: `status is ${task.status} — nothing is running` };
  const owner = task.owner || {};
  let killed = false;
  if (S.isSelf && S.isSelf(owner)) throw usage('stop: this process owns the task — it cannot stop itself');
  if (S.ownerAlive(owner) && owner.host && owner.host !== require('node:os').hostname()) {
    return { task, ok: false, stopped: false, reason: `the task runs on another host (${owner.host}); stop it there` };
  }
  if (S.ownerAlive(owner)) {
    await killTree(owner.pid);
    killed = true;
    for (let i = 0; i < 50 && S.pidAlive(owner.pid); i++) await new Promise(r => setTimeout(r, 200));
    if (S.pidAlive(owner.pid)) return { task, ok: false, stopped: false, reason: `could not stop pid ${owner.pid}` };
    await new Promise(r => setTimeout(r, 500));   // 자식이 파일 핸들을 놓을 틈
  }
  // 지금까지의 작업을 커밋한다 — 이 작업의 worktree 일 때만(버그: 등록 없는 폴더에서는 git 이 메인 저장소를 본다).
  let commit = null, commitError = null;
  if (fs.existsSync(P.wt) && G.isWorktreeRoot(P.wt, task.branch)) {
    try { commit = G.commitAll(P.wt, `harness(${task.id}): stopped by the user — saving work in progress`, { branch: task.branch }); }
    catch (e) { commitError = e.message; }
  }
  const fresh = S.readTask(root, task.id) || task;
  if (commit) (fresh.commits = fresh.commits || []).push(commit);
  Object.assign(fresh, { status: 'interrupted', reason: `stopped by the user${killed ? ` (process tree of pid ${owner.pid} ended)` : ' (its process was already gone)'}`, owner: null });
  S.writeTask(root, fresh);
  S.log(root, task.id, { event: 'stopped', killed, pid: owner.pid || null, commit, commit_error: commitError });
  try { S.removeDeadLocks && S.removeDeadLocks(root); } catch { /* 잠금은 다음 작업이 빼앗는다 */ }
  return { task: fresh, ok: true, stopped: true, killed, commit, commitError,
    reason: fresh.reason, next: [`continue: node harness/cli.js resume ${task.id}`, `discard:  node harness/cli.js cancel ${task.id}`] };
}

function format(r) {
  const L = [`harness ${r.task.id} — ${r.stopped ? 'STOPPED' : r.ok ? 'NOT RUNNING' : 'NOT STOPPED'}`, `why: ${r.reason}`];
  if (r.commit) L.push(`work in progress committed on ${r.task.branch} @ ${r.commit.slice(0, 10)}`);
  if (r.commitError) L.push(`could not commit the worktree: ${r.commitError}`);
  if (r.next) L.push(...r.next);
  return L.join('\n');
}

module.exports = { stop, format };
