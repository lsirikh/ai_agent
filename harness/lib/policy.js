'use strict';
// 워커 권한 — 하네스가 띄우는 모델 세션이 무엇을 묻지 않고 할 수 있고, 무엇을 절대 못 하는가.
//   Claude: `--settings <임시 파일>` 로 넘기는 객체. `-p` 는 미신뢰 폴더에서 프로젝트 settings 의 allow 를 적용하지
//     않으므로 허용은 여기서 직접 준다(--settings 는 신뢰와 무관하게 적용된다 — Claude 조사 §0·§7).
//     허용 = 검사를 돌리는 프로그램(Bash·PowerShell 짝) + 읽기 전용 git. 거부 = git 쓰기 전부 — git 은 하네스만 한다.
//     deny 는 어느 스코프의 allow 도 이긴다. Bash 규칙은 보안 경계가 아니다(`sh -c` 류 우회) — 대화형 쪽은 guard 훅이 보강한다.
//   Codex: `-s workspace-write`. 샌드박스가 `.git` 을 읽기 전용으로 두므로 git 쓰기는 원천 불가, 네트워크 기본 차단은 그대로 둔다.

// 워커가 실행해도 되는 프로그램 후보(설계 §3). 검사 명령의 argv[0] 과 저장소 종류에 맞는 것만 고른다.
const DEFAULT_PROGRAMS = ['node', 'npm', 'npx', 'pnpm', 'yarn', 'python', 'py', 'pytest', 'pip', 'dotnet', 'go', 'cargo', 'make', 'tsc', 'jest', 'vitest'];

// 저장소 종류 → 기본으로 허용할 프로그램.
const REPO_KIND_PROGRAMS = {
  node: ['node', 'npm', 'npx'], npm: ['node', 'npm', 'npx'], pnpm: ['node', 'pnpm', 'npx'], yarn: ['node', 'yarn', 'npx'],
  typescript: ['node', 'npm', 'npx', 'tsc'], python: ['python', 'py', 'pytest', 'pip'], dotnet: ['dotnet'],
  go: ['go'], rust: ['cargo'], cargo: ['cargo'], make: ['make'],
};

const READONLY_GIT = ['git status', 'git diff', 'git log', 'git show', 'git ls-files', 'git rev-parse', 'git grep', 'git blame'];
// 저장소를 읽기만 하는 명령 — [2026-10-16 자동 이슈 #12] 구조를 보는 명령까지 거부돼 작업자가 우회하거나 정체됐다.
//   find 는 넣지 않는다(-delete · -exec 로 지우거나 실행한다). SDK 정보 명령은 그 SDK 를 허용하지 않은 저장소에서도.
const READONLY_TOOLS = ['ls', 'cat', 'pwd', 'tree', 'stat', 'realpath', 'which',
  'Get-ChildItem', 'Get-Content', 'Get-Item', 'Test-Path', 'Resolve-Path', 'Get-Location',
  'dotnet --list-sdks', 'dotnet --list-runtimes', 'dotnet --info'];
// 읽기 전용 파이프 필터 — 출력을 줄이려고 붙이는 것들. Claude Code 는 파이프의 각 토막을 따로 보므로 하나라도 허용 밖이면 명령 전체가 거부된다.
//   [2026-10-15 현장 감사] 작업자 셸 호출의 17% 가 거부 · 그 65% 가 `dotnet build … | Select-String` 같은 파이프 — 빌드 · 테스트 확인이 108번 막혔다.
//   파일을 쓰거나 다른 명령을 실행하는 도구(sed -i · find -exec · xargs · awk · tee · ForEach-Object)는 넣지 않는다.
const READONLY_FILTERS = ['grep', 'head', 'tail', 'wc', 'sort', 'uniq', 'cut',
  'Select-String', 'Select-Object', 'Measure-Object', 'Sort-Object', 'Format-Table', 'Format-List', 'Out-String'];
// git 쓰기(설계 §3 목록) + 같은 효과의 이웃들. 접두 규칙이라 `git restore <file>` 같은 무해한 쓰임도 막히지만,
//   워커는 Edit 로 되돌리면 된다 — git 상태는 하네스만 바꾼다(stash 는 하네스 커밋이 변경을 못 보게 숨긴다).
const DENY_GIT = [
  'git push', 'git merge', 'git reset', 'git rebase', 'git checkout', 'git switch',
  'git branch -D', 'git branch -d', 'git branch --delete', 'git clean', 'git commit',
  'git stash', 'git restore', 'git cherry-pick', 'git revert', 'git am', 'git tag', 'git worktree', 'git update-ref',
  'git config', 'git -C', 'git --git-dir', 'git --work-tree',
];
const SHELLS = ['Bash', 'PowerShell'];

const SAFE_NAME = /^[A-Za-z0-9][A-Za-z0-9._+-]*$/;

// 절대 허용하지 않는 프로그램 — 임의 명령을 실행하는 셸 · 래퍼(`bash x.sh` · `env git push` 로 deny 를 우회한다).
//   검사 명령이 이것으로 시작해도(사용자가 준 검사라도) 허용 목록에는 넣지 않는다. git 은 하네스만 쓴다.
//   checks.js 의 allowCommands 도 이 목록을 쓴다 — 목록이 둘이면 한쪽만 고쳐져 어긋난다.
const NEVER_ALLOW = ['bash', 'sh', 'zsh', 'dash', 'ksh', 'fish', 'busybox', 'cmd', 'powershell', 'pwsh', 'env', 'wsl',
  'sudo', 'doas', 'xargs', 'nohup', 'exec', 'eval', 'start', 'git'];
function isNeverAllowed(name) {
  const base = String(name || '').split(/[\\/]/).pop().replace(/\.(exe|cmd|bat|com|ps1)$/i, '').toLowerCase();
  return NEVER_ALLOW.includes(base);
}

function rules(prefixes) {
  const out = [];
  for (const sh of SHELLS) for (const p of prefixes) out.push(`${sh}(${p}:*)`);
  return out;
}

// ── 사용자가 준 추가 허용 규칙(go --allow · 프로젝트 블록 worker_allow) ──────────────
//   [2026-10-01 · Python 서비스 저장소] 무인 작업자는 `docker build` · `cp -r` 같은 인프라 단계를 물을 사람이 없어 자동 거부당해 BLOCKED 로 끝났다.
//   사용자가 보낼 때 명시한 규칙만 더한다. git 쓰기 · 셸 · 통째 허용은 규칙이 무엇이든 받지 않는다(git 은 하네스만 쓴다).
//   deny 목록은 그대로 두므로(deny 가 allow 를 이긴다) 여기를 빠져나간 규칙도 git 쓰기는 못 한다 — 이 검증은 그 앞의 첫 벽이다.
const ALLOW_TOOLS = ['Bash', 'PowerShell', 'Read', 'Edit', 'Write', 'WebFetch'];
// 규칙으로 허용해도 되는 git 하위 명령 — 읽기 전용만.
const READONLY_GIT_SUB = ['status', 'diff', 'log', 'show', 'rev-parse', 'ls-files', 'ls-tree', 'blame', 'grep', 'describe', 'cat-file', 'shortlog'];
// PowerShell 의 임의 실행기(셸 이름 목록 밖).
const PS_RUNNERS = ['invoke-expression', 'iex', 'start-process', 'saps', 'invoke-command', 'icm', 'invoke-item', 'ii'];

// 규칙 하나 → 문제가 있으면 이유(문자열), 괜찮으면 null.
function validateAllowRule(rule) {
  const s = String(rule == null ? '' : rule).trim();
  const m = /^([A-Za-z]+)\(([\s\S]*)\)$/.exec(s);
  if (!m) return `allow rule must look like Tool(...) with Tool one of ${ALLOW_TOOLS.join('|')}: ${JSON.stringify(s)}`;
  const tool = m[1], spec = m[2].trim();
  if (!ALLOW_TOOLS.includes(tool)) return `allow rule tool must be one of ${ALLOW_TOOLS.join('|')}: ${JSON.stringify(s)}`;
  if (!spec || /^[*:\s]+$/.test(spec)) return `allow rule ${s} allows everything — name the command or path`;
  if (/[\r\n]/.test(spec)) return `allow rule must be one line: ${JSON.stringify(s)}`;
  if (tool === 'Read' || tool === 'Edit' || tool === 'Write') {
    if (tool !== 'Read' && /(^|[\\/])\.git([\\/]|$)/i.test(spec)) return `allow rule ${s} writes inside .git — git state is changed only by the harness`;
    return null;
  }
  if (tool === 'WebFetch') return null;
  // Bash · PowerShell: "<프로그램> [하위 명령 …][:*| *]"
  if (/&&|\|\||[;|`<>]|\$\(/.test(spec)) return `allow rule ${s} contains shell operators — allow one command prefix per rule`;
  const words = spec.replace(/:\*$/, '').replace(/\s*\*$/, '').trim().split(/\s+/).filter(Boolean);
  if (!words.length) return `allow rule ${s} allows everything — name the command`;
  const prog = words[0].replace(/^["']|["']$/g, '');
  if (/[*?]/.test(prog) || (/:/.test(prog) && !/^[A-Za-z]:[\\/]/.test(prog))) return `allow rule ${s} must start with a program name (no wildcard in the program)`;
  const base = prog.split(/[\\/]/).pop().replace(/\.(exe|cmd|bat|com|ps1)$/i, '').toLowerCase();
  if (base === 'git') {
    const sub = (words[1] || '').toLowerCase();
    if (!sub) return `allow rule ${s} allows every git command — git writes (commit · push · reset · checkout · merge · rebase · branch · tag · stash · clean) are done only by the harness`;
    if (!READONLY_GIT_SUB.includes(sub)) return `allow rule ${s} allows git ${sub} — git writes are done only by the harness (read-only git: ${READONLY_GIT_SUB.join(', ')})`;
    return null;
  }
  if (isNeverAllowed(base)) return `allow rule ${s} allows ${base}, which runs arbitrary commands (shells and wrappers can bypass the git deny list)`;
  if (tool === 'PowerShell' && PS_RUNNERS.includes(base)) return `allow rule ${s} allows ${base}, which runs arbitrary commands`;
  return null;
}
// 목록 검증 · 중복 제거. 하나라도 금지면 USAGE 로 던진다(where: 어디서 왔는지).
function checkAllowRules(list, where) {
  const out = [];
  for (const r of list || []) {
    const why = validateAllowRule(r);
    if (why) throw Object.assign(new Error(`${where ? where + ': ' : ''}${why}`), { code: 'USAGE' });
    const v = String(r).trim();
    if (!out.includes(v)) out.push(v);
  }
  return out;
}

// allowCommands: ['node','npm',…] — 이름만. 규칙 문법을 깰 수 있는 이름(괄호·공백·경로)은 버린다.
// extraAllow: 사용자가 준 규칙(go --allow · worker_allow) — 다시 검증해 금지 규칙은 버리고 allow 끝에 덧붙인다. deny 는 바꾸지 않는다.
function claudeSettings(allowCommands, extraAllow) {
  const progs = [...new Set((allowCommands || []).map(String).filter(n => SAFE_NAME.test(n) && !isNeverAllowed(n)))];
  const base = [...rules(progs), ...rules(READONLY_GIT), ...rules(READONLY_FILTERS), ...rules(READONLY_TOOLS)];
  const extra = [...new Set((extraAllow || []).map(x => String(x).trim()).filter(x => !validateAllowRule(x) && !base.includes(x)))];
  return {
    permissions: {
      allow: [...base, ...extra],
      deny: rules(DENY_GIT),
      disableBypassPermissionsMode: 'disable',
    },
  };
}

// 거부된 명령 하나 → 그것을 허용할 규칙 제안(없으면 null — git 쓰기 · 셸 등 사용자가 직접 해야 하는 것).
//   프로그램 + 첫 하위 명령(`docker build …` → Bash(docker build:*)). 하위 명령이 없는 파일 도구(cp · mv …)와 플래그는 프로그램만.
//   인터프리터 + 스크립트 경로(`python scripts/x.py …`)는 스크립트까지.
const NO_SUBCOMMAND = new Set(['cp', 'mv', 'rm', 'mkdir', 'rmdir', 'touch', 'cat', 'ls', 'chmod', 'chown', 'ln', 'tar', 'zip', 'unzip', 'curl', 'wget', 'find', 'grep', 'sed', 'awk', 'head', 'tail', 'echo', 'copy', 'xcopy', 'robocopy', 'del', 'move', 'md', 'rd', 'type', 'dir']);
const INTERPRETERS = new Set(['python', 'python3', 'py', 'node', 'deno', 'bun', 'ruby', 'perl', 'php', 'pwsh']);
function suggestAllowRule(tool, command) {
  const t = tool === 'PowerShell' ? 'PowerShell' : tool === 'Bash' ? 'Bash' : null;
  if (!t) return null;
  const out = [];
  for (const seg of String(command || '').split(/&&|\|\||;|\|/)) {
    const words = seg.trim().split(/\s+/).filter(w => w && !/^[A-Za-z_][A-Za-z0-9_]*=/.test(w));
    if (!words.length) continue;
    const prog = words[0];
    const name = prog.split(/[\\/]/).pop().replace(/\.(exe|cmd|bat|com)$/i, '').toLowerCase();
    if (name === 'cd' || name === 'set-location') continue;
    let prefix = prog;
    const w1 = words[1] || '';
    if (INTERPRETERS.has(name) && /^[\w./\\-]+\.(py|js|mjs|cjs|ts|rb|pl|php|ps1)$/i.test(w1)) prefix = `${prog} ${w1}`;
    else if (!NO_SUBCOMMAND.has(name) && !INTERPRETERS.has(name) && /^[a-z][a-z0-9-]*$/.test(w1)) prefix = `${prog} ${w1}`;
    if (/["'`$]/.test(prefix)) return null;
    const rule = `${t}(${prefix}:*)`;
    if (validateAllowRule(rule)) return null;
    out.push(rule);
  }
  return out.length ? [...new Set(out)] : null;
}

// Codex 권한 인자. 승인 정책은 exec 가 `never` 로 강제한다(-a 는 exec 에 없다). danger/yolo 는 절대 쓰지 않는다.
function codexArgs() { return ['-s', 'workspace-write']; }

// 명령 하나의 프로그램 이름: argv 배열이면 [0], 문자열이면 첫 토큰. 경로·확장자(.exe/.cmd/.bat/.ps1)를 걷어 낸다.
function programOf(cmd) {
  let a0 = Array.isArray(cmd) ? cmd[0] : String(cmd || '').trim().match(/^"([^"]+)"|^(\S+)/);
  if (!Array.isArray(cmd)) a0 = a0 ? (a0[1] || a0[2]) : '';
  const base = String(a0 || '').split(/[\\/]/).pop();
  return base.replace(/\.(exe|cmd|bat|ps1)$/i, '').toLowerCase();
}

// allowFor(checkCommands, repoKind) → allowCommands.
//   checkCommands: [['node','tests/run.js'], 'npm test', …] · repoKind: 'node'|'python'|…|[…]|null
//   검사의 argv[0] 중 기본 후보에 있는 것 + 저장소 종류의 기본 도구. 후보 밖 프로그램(bash·sh·cmd 등 임의 실행기)은 넣지 않는다.
function allowFor(checkCommands, repoKind) {
  const out = new Set();
  for (const c of checkCommands || []) { const p = programOf(c); if (DEFAULT_PROGRAMS.includes(p) && !isNeverAllowed(p)) out.add(p); }
  for (const k of [].concat(repoKind || [])) for (const p of REPO_KIND_PROGRAMS[String(k).toLowerCase()] || []) out.add(p);
  return DEFAULT_PROGRAMS.filter(p => out.has(p));
}

module.exports = { DEFAULT_PROGRAMS, REPO_KIND_PROGRAMS, READONLY_GIT, DENY_GIT, NEVER_ALLOW, ALLOW_TOOLS, isNeverAllowed, claudeSettings, codexArgs, allowFor, programOf,
  validateAllowRule, checkAllowRules, suggestAllowRule };
