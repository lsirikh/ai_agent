'use strict';
// 실행 파일 찾기 — resolve(runtime, override, opts) → 절대 경로(없으면 EXE_NOT_FOUND / EXE_NOT_RUNNABLE 을 던진다).
//   우선순위: override(인자) → 환경 HARNESS_CLAUDE_EXE / HARNESS_CODEX_EXE → PATH → 알려진 설치 위치.
//   [실측 2026-09-27 · test_exec_candidates] Windows 에서 npm 전역 설치는 PATH 폴더에 확장자 없는 sh shim(`claude`)과
//   `claude.cmd` 를 둔다. 확장자 없는 파일은 CreateProcess 로 실행할 수 없고("올바른 Win32 응용 프로그램이 아닙니다"),
//   .cmd 는 셸 없이 spawn 할 수 없다 → Windows 후보는 **`.exe` 만**. 강제 경로도 같은 검사를 받는다.
//   Codex 는 PATH 에 없는 경우가 흔하다(데스크톱 앱 번들 · VS Code 확장 번들) — 그 위치를 차례로 본다.
const fs = require('node:fs'), os = require('node:os'), path = require('node:path');

const ENV_KEY = { claude: 'HARNESS_CLAUDE_EXE', codex: 'HARNESS_CODEX_EXE' };

function isFile(p) { try { return fs.statSync(p).isFile(); } catch { return false; } }
function isWin(opts) { return (opts && opts.platform ? opts.platform : process.platform) === 'win32'; }

function fail(code, msg) { return Object.assign(new Error(`${code}: ${msg}`), { code }); }

// Windows 에서 실행할 수 있는가 — 확장자가 .exe 이고 파일이 있다. POSIX 는 파일이 있으면 된다.
function runnable(file, opts) {
  if (!isFile(file)) return false;
  return isWin(opts) ? /\.exe$/i.test(file) : true;
}

// 'openai.chatgpt-26.5917.62051-win32-x64' → [26,5917,62051]. 숫자 비교(사전식이면 9.x 가 10.x 를 이긴다).
function extVersion(name) { const m = /^openai\.chatgpt-(\d+(?:\.\d+)*)/.exec(name); return m ? m[1].split('.').map(Number) : []; }
function cmpVersionDesc(a, b) {
  const x = extVersion(a), y = extVersion(b);
  for (let i = 0; i < Math.max(x.length, y.length); i++) { const d = (y[i] || 0) - (x[i] || 0); if (d) return d; }
  return b < a ? -1 : b > a ? 1 : 0;
}
function mtime(p) { try { return fs.statSync(p).mtimeMs; } catch { return 0; } }
function listDir(dir) { try { return fs.readdirSync(dir); } catch { return []; } }

// 후보 목록(존재·실행 가능한 것만, 중복 제거, 우선순위 순).
function candidates(runtime, opts) {
  opts = opts || {};
  const env = opts.env || process.env, win = isWin(opts), home = opts.home || env.USERPROFILE || env.HOME || os.homedir();
  const name = win ? `${runtime}.exe` : runtime;
  const found = [];
  const add = f => { if (f && runnable(f, opts)) found.push(path.resolve(f)); };
  const PATH = env.PATH || env.Path || env.path || '';
  for (const dir of PATH.split(win ? ';' : path.delimiter)) if (dir) add(path.join(dir.replace(/^"|"$/g, ''), name));

  if (runtime === 'claude') {
    // 네이티브 설치기 · npm 전역 패키지 안의 진짜 바이너리(shim 이 아니라).
    add(path.join(home, '.local', 'bin', name));
    const appData = env.APPDATA || (win ? path.join(home, 'AppData', 'Roaming') : null);
    if (appData) add(path.join(appData, 'npm', 'node_modules', '@anthropic-ai', 'claude-code', 'bin', name));
    if (!win) add(path.join('/usr', 'local', 'lib', 'node_modules', '@anthropic-ai', 'claude-code', 'bin', name));
  }
  if (runtime === 'codex') {
    // npm 전역 @openai/codex 안의 진짜 바이너리(shim 이 아니라) — [2026-09-30] VS Code 번들 0.155 는 Windows 샌드박스가 깨져 있었다.
    const appDataCx = env.APPDATA || (win ? path.join(home, 'AppData', 'Roaming') : null);
    if (appDataCx && win) add(path.join(appDataCx, 'npm', 'node_modules', '@openai', 'codex', 'node_modules', '@openai', 'codex-win32-x64', 'vendor', 'x86_64-pc-windows-msvc', 'bin', name));
    // VS Code 확장 번들 — 가장 새 버전부터.
    const plat = win ? 'windows-x86_64' : process.platform === 'darwin' ? 'macos-aarch64' : 'linux-x86_64';
    const extRoot = path.join(home, '.vscode', 'extensions');
    for (const d of listDir(extRoot).filter(n => n.startsWith('openai.chatgpt-')).sort(cmpVersionDesc)) add(path.join(extRoot, d, 'bin', plat, name));
    // 데스크톱 앱 번들: %LOCALAPPDATA%\OpenAI\Codex\bin\<hash>\codex.exe — 가장 최근에 바뀐 것부터.
    const local = env.LOCALAPPDATA || (win ? path.join(home, 'AppData', 'Local') : null);
    if (local) {
      const binRoot = path.join(local, 'OpenAI', 'Codex', 'bin');
      const files = listDir(binRoot).map(d => path.join(binRoot, d, name)).filter(f => runnable(f, opts));
      files.sort((a, b) => mtime(b) - mtime(a)).forEach(add);
    }
  }
  return [...new Set(found)];
}

function checkForced(file, source, opts) {
  const abs = path.resolve(file);
  if (!isFile(abs)) throw fail('EXE_NOT_FOUND', `${source} 가 가리키는 파일이 없다: ${abs}`);
  if (!runnable(abs, opts)) throw fail('EXE_NOT_RUNNABLE', `${source} 가 가리키는 파일은 Windows 에서 실행할 수 없다(.exe 가 아님 — npm shim/.cmd 는 쓰지 않는다): ${abs}`);
  return abs;
}

function resolve(runtime, override, opts) {
  if (!ENV_KEY[runtime]) throw fail('BAD_RUNTIME', `모르는 runtime: ${runtime}`);
  opts = opts || {};
  const env = opts.env || process.env;
  if (override) return checkForced(override, 'exe 인자', opts);
  if (env[ENV_KEY[runtime]]) return checkForced(env[ENV_KEY[runtime]], ENV_KEY[runtime], opts);
  const list = candidates(runtime, opts);
  if (!list.length) throw fail('EXE_NOT_FOUND', `${runtime} 실행 파일을 찾지 못했다(PATH · 설치 위치). ${ENV_KEY[runtime]} 로 경로를 지정하라`);
  if (list.length === 1 || opts.pathOrder) return list[0];
  // [2026-09-29 실측] 이 PC 의 PATH 는 WinGet claude 2.1.248 을 npm 2.1.283 보다 먼저 준다 — 워커는 가장 새 설치본을 쓴다
  //   (--settings 권한·비용 의미가 버전마다 다르다). 버전을 못 읽는 후보는 뒤로, 같으면 PATH 순서.
  const cmp = (a, b) => { for (let i = 0; i < 3; i++) if (a[i] !== b[i]) return a[i] - b[i]; return 0; };
  const scored = list.map((file, i) => ({ file, i, v: version(file, [], opts.env) }));
  scored.sort((a, b) => (a.v && b.v) ? (cmp(b.v, a.v) || a.i - b.i) : (a.v ? -1 : b.v ? 1 : a.i - b.i));
  return scored[0].file;
}

// `<exe> --version` → [major, minor, patch] | null. 실행 파일(+앞 인자 · 환경)마다 한 번만 묻는다.
const versionCache = new Map();
function version(file, prefixArgs, extraEnv) {
  const key = JSON.stringify([file, prefixArgs || [], extraEnv || {}]);
  if (versionCache.has(key)) return versionCache.get(key);
  let v = null;
  try {
    const { childEnv } = require('./proc');
    const r = require('node:child_process').spawnSync(file, [...(prefixArgs || []), '--version'], { input: '', encoding: 'utf8', windowsHide: true, timeout: 15000, env: childEnv(extraEnv) });
    const m = /(\d+)\.(\d+)\.(\d+)/.exec(String(r.stdout || ''));
    if (m) v = [Number(m[1]), Number(m[2]), Number(m[3])];
  } catch { v = null; }
  versionCache.set(key, v);
  return v;
}

module.exports = { resolve, candidates, runnable, version, ENV_KEY, extVersion };
