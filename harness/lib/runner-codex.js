'use strict';
// Codex 러너 — `codex exec --json` 한 번 = 한 턴.
//   새:   codex exec --json -s workspace-write -C <cwd> [-m M] [-c model_reasoning_effort=E] --skip-git-repo-check -
//   재개: codex exec --json -s workspace-write -C <cwd> [-m M] [-c …] --skip-git-repo-check resume <thread_id> -
//   [0.155 --help 대조] `-s/-C` 는 `resume` 뒤에 올 수 없다("unexpected argument '-s'") → 옵션은 모두 `resume` 앞.
//     재개 때 cwd·샌드박스는 이번 호출의 설정으로 다시 정해지므로 매번 같은 -s -C 를 준다.
//   프롬프트: exec 와 exec resume 모두 PROMPT 자리에 `-` 를 주면 stdin 에서 읽는다(--help 확인) → 명령줄 32K 상한과 무관.
//   JSONL: thread.started.thread_id → session_id · 마지막 item.completed(agent_message).text → final_text ·
//     turn.completed.usage 는 스레드 누계 → 합산하지 않고 마지막 값 · turn.failed / 재시도 없는 error → 실패.
//     `error` 이벤트는 재시도 중인 일시 오류에도 나온다 → 그것만으로 실패라 하지 않는다(turn.failed · 종료 코드로 판정).
//   토큰 예산은 CLI 에서 권고일 뿐 — 러너는 누계만 보고하고 강제는 엔진이 한다. 비용(USD)은 Codex 가 주지 않는다(null).
const { spawnCapture, noPushEnv } = require('./proc');
const policy = require('./policy');
const exe = require('./exe');
const { QUOTA, AUTH } = require('./runner-claude');

const CODEX_QUOTA = /usage limit|hit your limit|rate.?limit|usageLimitExceeded|rateLimitExceeded|purchase more credits|quota|too many requests/i;
const CODEX_AUTH = /unauthori[sz]ed|\b401\b|not logged in|codex login|login required|invalid api key|authentication/i;
const SAFE_VALUE = /^[A-Za-z0-9._:-]+$/;

// [2026-09-30 실측] 이 PC 의 Codex 설정은 [windows] sandbox = "elevated" — 전용 샌드박스 사용자가 준비되지 않아 모든 쓰기·실행이
//   "apply deny-read ACLs" 로 실패했다(0.155 · 0.159.1 모두). "unelevated"(현재 사용자에서 파생한 제한 토큰)는 worktree 쓰기·node 실행이 되고
//   .git 쓰기(index.lock)와 작업공간 밖 쓰기는 여전히 거부됐다(실측). HARNESS_CODEX_WINDOWS_SANDBOX=elevated|unelevated|inherit 로 바꾼다.
function windowsSandbox(o) {
  const env = (o && o.env) || process.env;
  const v = String(env.HARNESS_CODEX_WINDOWS_SANDBOX || '').trim().toLowerCase();
  if (v === 'inherit') return null;
  if (v === 'elevated' || v === 'unelevated') return v;
  return ((o && o.platform) || process.platform) === 'win32' ? 'unelevated' : null;
}

const SANDBOX_FAIL = /apply deny-read ACLs|Failed to create unified exec process|helper_unknown_error|sandbox (?:setup|initiali[sz]ation) failed/i;

function buildArgs(o) {
  const a = ['exec', '--json', ...policy.codexArgs(), '-C', String(o.cwd)];
  if (o.model) a.push('-m', String(o.model));
  if (o.effort) {
    if (!SAFE_VALUE.test(String(o.effort))) throw Object.assign(new TypeError(`effort 값이 이상하다: ${o.effort}`), { code: 'BAD_EFFORT' });
    a.push('-c', `model_reasoning_effort=${o.effort}`);
  }
  const winSandbox = windowsSandbox(o);
  if (winSandbox) a.push('-c', 'windows.sandbox="' + winSandbox + '"');
  a.push('--skip-git-repo-check');
  // 첨부 이미지(원본 · 영상 장면) — 첫 호출에만. 이어 가는 세션은 이미 받았다.
  if (!o.sessionId) for (const img of o.images || []) a.push('-i', String(img));
  if (o.sessionId) a.push('resume', String(o.sessionId), '-');
  else a.push('-');
  return a;
}

// JSONL 스트림 파서 — 한 줄씩 먹이고 state() 로 요약을 받는다.
function makeParser() {
  const s = { thread_id: null, final_text: '', usage: null, turn_completed: false, turn_failed: null, last_error: null, denials: [], tool_failures: [], events: 0, bad_lines: 0 };
  return {
    line(l) {
      const t = String(l).trim(); if (!t.startsWith('{')) return;
      let e; try { e = JSON.parse(t); } catch { s.bad_lines++; return; }
      s.events++;
      switch (e.type) {
        case 'thread.started': if (e.thread_id) s.thread_id = e.thread_id; break;
        case 'turn.completed': s.turn_completed = true; if (e.usage) s.usage = e.usage; break;
        case 'turn.failed': s.turn_failed = (e.error && e.error.message) || 'turn failed'; if (e.usage) s.usage = e.usage; break;
        case 'error': s.last_error = e.message || (e.error && e.error.message) || 'error'; break;
        case 'item.completed': {
          const it = e.item || {};
          if (it.type === 'agent_message' && typeof it.text === 'string') s.final_text = it.text;
          if (it.type === 'command_execution' && it.status === 'declined') s.denials.push({ tool_name: 'command_execution', tool_input: { command: it.command } });
          if (it.type === 'file_change' && it.status === 'declined') s.denials.push({ tool_name: 'file_change', tool_input: { changes: it.changes } });
          if ((it.type === 'command_execution' || it.type === 'file_change') && it.status === 'failed') s.tool_failures.push({ type: it.type, output: String(it.aggregated_output || '').slice(0, 300) });
          break;
        }
        default: break;
      }
    },
    state() { return s; },
  };
}

function tokensOf(u) {
  if (!u || typeof u !== 'object') return null;
  const input = u.input_tokens || 0, output = u.output_tokens || 0;
  return { input, output, total: input + output, cached_input: u.cached_input_tokens || 0, reasoning_output: u.reasoning_output_tokens || 0 };
}

function classify(text) { return CODEX_QUOTA.test(text) || QUOTA.test(text) ? 'quota' : CODEX_AUTH.test(text) || AUTH.test(text) ? 'auth' : null; }

function toResult(p, s, o) {
  const stderrTail = String(p.stderr || '').slice(-2000);
  const r = {
    // thread.started 를 봤을 때만 확인된 세션(H1) — 재개 호출은 기존 id 를 그대로 돌려준다.
    ok: false, session_id: s.thread_id || o.sessionId || null, session_confirmed: !!s.thread_id, final_text: s.final_text, cost_usd: null, session_cost_usd: null,
    tokens: tokensOf(s.usage), exit_code: p.code, is_error: true, error_kind: null, error_message: null,
    permission_denials: s.denials, tool_failures: s.tool_failures, stderr_tail: stderrTail, duration_ms: p.durationMs,
  };
  if (p.spawnError) { r.error_kind = 'crash'; r.error_message = `실행 실패: ${p.spawnError.message}`; return r; }
  if (p.timedOut) { r.error_kind = 'timeout'; r.error_message = `상한 시간(${o.timeoutMs}ms)에 프로세스 트리를 종료했다`; return r; }
  if (p.aborted) { r.error_kind = 'aborted'; r.error_message = '취소 신호로 프로세스 트리를 종료했다'; return r; }
  // 샌드박스가 도구 실행 자체를 거부했다 — 모델은 턴을 끝내지만 아무것도 할 수 없었다. 판정·넛지 대신 곧장 멈춰 이유를 보인다.
  const sandboxText = s.tool_failures.map(t => t.output).concat([stderrTail]).join('\n');
  const sb = SANDBOX_FAIL.exec(sandboxText);
  if (sb) {
    r.error_kind = 'sandbox';
    r.error_message = 'Codex sandbox refused file writes/commands (' + sb[0] + '). On Windows the harness passes windows.sandbox="unelevated" by default; check HARNESS_CODEX_WINDOWS_SANDBOX and [windows] sandbox in ~/.codex/config.toml.';
    return r;
  }
  if (s.turn_completed && !s.turn_failed && p.code === 0) { r.ok = true; r.is_error = false; return r; }
  if (s.turn_failed) {
    r.error_kind = classify(s.turn_failed) || 'model';
    r.error_message = s.turn_failed.slice(0, 900);
    return r;
  }
  // 턴 이벤트 없이 끝났다 — 재시도 없는 오류·중단·시작 실패.
  const said = [s.last_error, stderrTail.trim()].filter(Boolean).join(' · ');
  r.error_kind = classify(said) || (s.last_error ? 'model' : 'crash');
  r.error_message = (said || `턴 결과 없이 종료(exit ${p.code})`).slice(0, 900);
  return r;
}

async function run(o) {
  let bin;
  try { bin = exe.resolve('codex', o.exe); }
  catch (e) { return toResult({ spawnError: e, code: null, stderr: '', durationMs: 0 }, makeParser().state(), o); }
  const parser = makeParser();
  const args = [...(o.exePrefixArgs || []), ...buildArgs(o)];
  const p = await spawnCapture({ exe: bin, args, cwd: o.cwd, input: o.prompt, env: noPushEnv(o.env, o.cwd), timeoutMs: o.timeoutMs, signal: o.signal,
    onLine: l => parser.line(l), stdoutHead: 16 * 1024, stdoutTail: 64 * 1024 });
  return toResult(p, parser.state(), o);
}

module.exports = { run, buildArgs, makeParser, toResult, classify, windowsSandbox, SANDBOX_FAIL };
