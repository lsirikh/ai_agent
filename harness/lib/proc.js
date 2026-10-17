'use strict';
// 러너 공용 프로세스 도구 — 의존성 없음.
//   spawnCapture(o): 프롬프트를 stdin 으로 넘기고, stdout/stderr 를 머리+꼬리만 남기며, 상한 시간·AbortSignal 에
//   프로세스 트리를 강제 종료한다(Windows `taskkill /PID <pid> /T /F`, POSIX 프로세스 그룹 SIGKILL).
//   자식 환경에서 CLAUDECODE · CLAUDE_CODE_ENTRYPOINT · NODE_TEST_CONTEXT 를 지운다 — 이 프로세스가
//   Claude Code 안에서, 또는 node:test 안에서 돌아도 자식은 독립된 세션이어야 한다.
const { spawn, spawnSync } = require('node:child_process');
const { StringDecoder } = require('node:string_decoder');

const IS_WIN = process.platform === 'win32';
const SCRUB = ['CLAUDECODE', 'CLAUDE_CODE_ENTRYPOINT', 'NODE_TEST_CONTEXT'];

function childEnv(extra) {
  const env = { ...process.env, ...(extra || {}) };
  // Windows 환경 변수 이름은 대소문자를 가리지 않는다 — 이름을 대문자로 비교해 지운다.
  for (const k of Object.keys(env)) if (SCRUB.includes(k.toUpperCase())) delete env[k];
  return env;
}

// 워커 환경의 git push 무력화(M8). 권한 규칙(Bash(git push:*) deny)은 경계가 아니다 — `node -e` 의 child_process 로도
//   push 할 수 있다. 그래서 워커 프로세스 트리 전체에 명령 수준 git 설정(GIT_CONFIG_COUNT/KEY_n/VALUE_n, git ≥2.31)을 준다:
//     push.default=nothing          — 대상 없는 `git push` 는 아무것도 고르지 않는다.
//     remote.pushDefault=           — 기본 push 원격 없음.
//     url.<막힌 스킴>.pushInsteadOf= — 빈 접두어는 모든 URL 과 맞는다 → 원격 이름 · 경로 · file:// · https 모두 막힌 스킴으로 바뀌어 실패.
//     url.<막힌 스킴>.insteadOf=<P>  — 명시적 remote.*.pushurl 에는 pushInsteadOf 가 적용되지 않으므로 그 값마다(fetch 도 그 URL 이면 막힌다).
//   [실측 2026-09-30 · git 2.53 · 임시 bare 원격] 위 설정으로 push origin/경로/file:// 모두 128 "remote helper 'harness-push-disabled'
//   aborted session", fetch 는 그대로 된다. 이미 있는 GIT_CONFIG_* 는 보존하고 뒤에 덧붙인다. 워커가 환경을 지우고 git 을 띄우면
//   우회된다 — 경계가 아니라 사고 방지층이다(대화형 쪽은 guard 훅, Codex 는 샌드박스가 .git 쓰기를 막는다).
const PUSH_DISABLED = 'harness-push-disabled://';
function pushUrls(cwd) {
  if (!cwd) return [];
  try {
    const r = spawnSync('git', ['config', '--get-regexp', '^remote\\..*\\.pushurl$'], { cwd, encoding: 'utf8', windowsHide: true, timeout: 10000 });
    return r.status === 0 ? String(r.stdout).split(/\r?\n/).map(l => l.replace(/^\S+\s+/, '').trim()).filter(Boolean) : [];
  } catch { return []; }
}
// 워커는 이 저장소의 ref(브랜치 · 태그 · HEAD)를 바꾸지 못한다 — 하네스가 턴마다 대신 커밋한다.
//   권한 규칙(git 쓰기 deny)은 `node -e` 의 child_process 로 우회된다: 워커가 메인 체크아웃에서 `git -C <root> commit -a` 하면
//   다른 세션의 미커밋 변경까지 사용자 브랜치에 커밋된다. 그래서 워커 프로세스 트리의 git 에 core.hooksPath 를 환경으로 주고,
//   reference-transaction 훅(git ≥2.28)이 prepared 단계에서 이 저장소(공통 .git 이 같은 것)의 ref 갱신을 모두 거부한다.
//   다른 저장소(테스트 스위트가 만드는 임시 저장소)는 통과 — 그 저장소의 훅은 워커 환경에서만 건너뛴다. 하네스 자신의 git 은 이 환경이 없다.
//   push 막기와 같이 경계가 아니라 사고 방지층이다(환경을 지우고 git 을 띄우면 우회된다).
const REF_HOOK = `#!/bin/sh
# harness worker guard (harness/lib/proc.js) — 하네스가 띄운 무인 작업자는 이 저장소의 ref 를 바꾸지 못한다.
[ "$1" = prepared ] || exit 0
[ -n "$HARNESS_PROTECT_GIT_DIR" ] || exit 0
c=$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null) || exit 0
a=$(printf '%s' "$c" | tr 'A-Z\\\\' 'a-z/' | sed 's:/*$::')
b=$(printf '%s' "$HARNESS_PROTECT_GIT_DIR" | tr 'A-Z\\\\' 'a-z/' | sed 's:/*$::')
[ "$a" = "$b" ] || exit 0
cat >/dev/null
echo "harness: this session may not change git refs (commit/branch/tag/checkout) in this repository - the harness commits your work after each turn; just edit files" >&2
exit 1
`;
function commonDirOf(cwd) {
  if (!cwd) return null;
  try {
    const r = spawnSync('git', ['rev-parse', '--path-format=absolute', '--git-common-dir'], { cwd, encoding: 'utf8', windowsHide: true, timeout: 10000 });
    return r.status === 0 && r.stdout.trim() ? r.stdout.trim() : null;
  } catch { return null; }
}
// <공통 .git>/harness/worker-hooks/reference-transaction 을 (내용이 다르면) 쓴다. 쓰지 못하면 null — 보호 없이 계속한다(push 막기는 그대로).
function refHookDir(common) {
  const fs = require('node:fs'), path = require('node:path');
  const dir = path.join(common, 'harness', 'worker-hooks'), f = path.join(dir, 'reference-transaction');
  try {
    let cur = null; try { cur = fs.readFileSync(f, 'utf8'); } catch { /* 없음 */ }
    if (cur !== REF_HOOK) { fs.mkdirSync(dir, { recursive: true }); fs.writeFileSync(f, REF_HOOK, { mode: 0o755 }); }
    if (!IS_WIN) fs.chmodSync(f, 0o755);
    return dir;
  } catch { return null; }
}
// 작업 worktree 에서 도는 프로세스(작업자 · 하네스 검사)의 격리 환경 — [2026-10-17 자동 보고 caed67b9a2f1] 작업자가 worktree 의 compose 로
//   사용자의 실행 중 컨테이너를 다시 만들었다(프로젝트 이름이 메인과 같았다). COMPOSE_PROJECT_NAME 은 compose 에서 .env · name: 보다 앞선다.
const WT_RE = /[\\/]\.harness-worktrees[\\/](t-\d{8}-\d{6}-[0-9a-f]{4})(?:-\d+)?(?:[\\/]|$)/;
function isolationEnv(cwd) {
  const m = WT_RE.exec(String(cwd || ''));
  return m ? { COMPOSE_PROJECT_NAME: `harness-${m[1]}` } : {};
}
function noPushEnv(extra, cwd) {
  const merged = { ...process.env, ...(extra || {}) };
  const countKey = Object.keys(merged).find(k => k.toUpperCase() === 'GIT_CONFIG_COUNT');
  let n = countKey ? parseInt(merged[countKey], 10) : 0;
  if (!(n >= 0)) n = 0;
  const common = commonDirOf(cwd), hooks = common && refHookDir(common);
  const pairs = [['push.default', 'nothing'], ['remote.pushDefault', ''], [`url.${PUSH_DISABLED}.pushInsteadOf`, ''],
    ...[...new Set(pushUrls(cwd))].map(u => [`url.${PUSH_DISABLED}.insteadOf`, u]),
    ...(hooks ? [['core.hooksPath', hooks.replace(/\\/g, '/')]] : [])];
  const out = { ...isolationEnv(cwd), ...(extra || {}) };
  pairs.forEach(([k, v], i) => { out[`GIT_CONFIG_KEY_${n + i}`] = k; out[`GIT_CONFIG_VALUE_${n + i}`] = v; });
  out[countKey || 'GIT_CONFIG_COUNT'] = String(n + pairs.length);
  if (hooks) out.HARNESS_PROTECT_GIT_DIR = common;
  return out;
}

function killTree(pid) {
  if (pid == null) return;
  if (IS_WIN) spawnSync('taskkill', ['/PID', String(pid), '/T', '/F'], { stdio: 'ignore', windowsHide: true, timeout: 15000 });
  else { try { process.kill(-pid, 'SIGKILL'); } catch { try { process.kill(pid, 'SIGKILL'); } catch { /* 이미 끝났다 */ } } }
}

// 앞 head 글자 + 뒤 tail 글자만 붙든다. 가운데는 몇 글자를 버렸는지만 센다.
class Capture {
  constructor(head, tail) { this.head = Math.max(0, head | 0); this.tail = Math.max(0, tail | 0); this.h = ''; this.t = ''; this.total = 0; }
  push(s) {
    if (!s) return;
    this.total += s.length;
    if (this.h.length < this.head) { const room = this.head - this.h.length; this.h += s.slice(0, room); s = s.slice(room); if (!s) return; }
    this.t += s;
    if (this.t.length > this.tail * 2 || this.t.length > this.tail + 65536) this.t = this.t.slice(this.t.length - this.tail);
  }
  get omitted() { return Math.max(0, this.total - this.h.length - Math.min(this.t.length, this.tail)); }
  text() {
    const t = this.t.length > this.tail ? this.t.slice(this.t.length - this.tail) : this.t;
    const cut = this.total - this.h.length - t.length;
    return cut > 0 ? `${this.h}\n…[${cut} chars omitted]…\n${t}` : this.h + t;
  }
  tailText(n) { const s = this.text(); return s.length > n ? s.slice(s.length - n) : s; }
}

// o = { exe, args, cwd, input, env, timeoutMs, signal, onLine, stdoutHead, stdoutTail, stderrHead, stderrTail, graceMs }
//   → Promise<{ code, signal, stdout, stderr, stdoutOmitted, timedOut, aborted, spawnError, pid, durationMs }>
//   onLine(line): stdout 을 줄 단위로 받는다(스트림 파싱용). 한 줄이 maxLine 을 넘으면 그 줄은 버리고 overlong 을 센다.
function spawnCapture(o) {
  return new Promise(resolve => {
    const t0 = Date.now();
    const out = new Capture(o.stdoutHead != null ? o.stdoutHead : 64 * 1024, o.stdoutTail != null ? o.stdoutTail : 8 * 1024 * 1024);
    const err = new Capture(o.stderrHead != null ? o.stderrHead : 8 * 1024, o.stderrTail != null ? o.stderrTail : 32 * 1024);
    const dOut = new StringDecoder('utf8'), dErr = new StringDecoder('utf8');
    const maxLine = o.maxLine || 64 * 1024 * 1024;
    let lineBuf = '', overlong = 0, dropping = false;
    let done = false, timedOut = false, aborted = false, spawnError = null, child = null, timer = null, grace = null, onAbort = null;

    const feedLines = s => {
      if (!o.onLine) return;
      let i;
      while ((i = s.indexOf('\n')) >= 0) {
        const piece = s.slice(0, i); s = s.slice(i + 1);
        if (!dropping) { const line = (lineBuf + piece).replace(/\r$/, ''); try { o.onLine(line); } catch { /* 파서 오류는 스트림을 멈추지 않는다 */ } }
        lineBuf = ''; dropping = false;
      }
      if (dropping) return;
      lineBuf += s;
      if (lineBuf.length > maxLine) { lineBuf = ''; dropping = true; overlong++; }
    };
    const finish = (code, sig) => {
      if (done) return; done = true;
      clearTimeout(timer); clearTimeout(grace);
      if (o.signal && onAbort) o.signal.removeEventListener('abort', onAbort);
      const restOut = dOut.end(); out.push(restOut); feedLines(restOut);
      if (o.onLine && lineBuf && !dropping) { try { o.onLine(lineBuf.replace(/\r$/, '')); } catch { /* 위와 같다 */ } }
      err.push(dErr.end());
      resolve({ code: code == null ? null : code, signal: sig || null, stdout: out.text(), stderr: err.text(), stdoutOmitted: out.omitted, overlongLines: overlong,
        timedOut, aborted, spawnError, pid: child ? child.pid : null, durationMs: Date.now() - t0 });
    };
    const kill = why => {
      if (done) return;
      if (why === 'timeout') timedOut = true; else aborted = true;
      if (child && child.pid != null) killTree(child.pid);
      // 손자가 파이프를 붙들고 있어도 곧 돌아온다.
      grace = setTimeout(() => { try { child.stdout.destroy(); child.stderr.destroy(); } catch { /* 이미 닫힘 */ } finish(null, 'SIGKILL'); }, o.graceMs || 3000);
      if (grace.unref) grace.unref();
    };

    if (o.signal && o.signal.aborted) { aborted = true; return finish(null); } // 이미 취소됐다 — 띄우지 않는다
    try {
      child = spawn(o.exe, o.args || [], { cwd: o.cwd, env: childEnv(o.env), stdio: ['pipe', 'pipe', 'pipe'], windowsHide: true, detached: !IS_WIN });
    } catch (e) { spawnError = e; return finish(null); }

    child.on('error', e => { spawnError = spawnError || e; finish(null); });
    child.on('close', (code, sig) => finish(code, sig));
    child.stdout.on('data', b => { const s = dOut.write(b); out.push(s); feedLines(s); });
    child.stderr.on('data', b => { err.push(dErr.write(b)); });
    child.stdin.on('error', () => { /* 자식이 먼저 끝났다 — close 가 결과를 낸다 */ });

    if (o.timeoutMs > 0) timer = setTimeout(() => kill('timeout'), Math.min(o.timeoutMs, 2 ** 31 - 1));
    if (o.signal) {
      onAbort = () => kill('abort');
      if (o.signal.aborted) onAbort(); else o.signal.addEventListener('abort', onAbort, { once: true });
    }
    child.stdin.end(o.input == null ? '' : String(o.input));
  });
}

module.exports = { isolationEnv, IS_WIN, SCRUB, childEnv, noPushEnv, PUSH_DISABLED, killTree, Capture, spawnCapture };
