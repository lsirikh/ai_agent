'use strict';
// run(o) → Promise<r> — 두 런타임을 같은 모양으로 몬다(설계 §3).
//   o = { runtime:'claude'|'codex', cwd, prompt, sessionId /* null = 새 세션 */, newSessionId /* claude uuid */,
//         model, effort, budgetUsd /* claude */, tokenBudget /* codex, 권고 — 러너는 쓰지 않는다 */, timeoutMs, signal,
//         exe /* 경로 강제 */, exePrefixArgs /* exe 앞 인자 — 테스트가 node + 가짜 CLI 스크립트를 띄울 때 */,
//         allowCommands, systemAppend, priorSessionCostUsd /* claude 재개: 직전 세션 누계 */,
//         costMode /* claude: 'cumulative'|'per_call' 강제 — 없으면 CLI 버전으로 */, env /* 자식 환경 추가 */ }
//   r = { ok, session_id, final_text, cost_usd /* 이번 호출분 */, session_cost_usd /* 세션 누계 */, tokens, exit_code, is_error,
//         error_kind /* null|'quota'|'auth'|'timeout'|'aborted'|'crash'|'model' */, error_message, permission_denials, stderr_tail,
//         duration_ms, (claude) subtype · num_turns · budget_exhausted · cost_mode }
//   입력 오류(런타임·cwd·prompt 누락)는 던진다. 실행 중 생긴 일은 던지지 않고 r 로 돌려준다.
const claude = require('./runner-claude');
const codex = require('./runner-codex');

const RUNNERS = { claude, codex };

async function run(o) {
  if (!o || !RUNNERS[o.runtime]) throw Object.assign(new TypeError(`runtime 은 claude|codex: ${o && o.runtime}`), { code: 'BAD_RUNTIME' });
  if (!o.cwd) throw Object.assign(new TypeError('cwd 가 없다'), { code: 'BAD_INPUT' });
  if (typeof o.prompt !== 'string' || !o.prompt) throw Object.assign(new TypeError('prompt 가 없다'), { code: 'BAD_INPUT' });
  return RUNNERS[o.runtime].run(o);
}

module.exports = { run, claude, codex };
