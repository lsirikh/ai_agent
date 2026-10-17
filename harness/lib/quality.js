'use strict';
// 품질 규칙(하네스 내장 린트) — 작업이 새로 더한 줄에서 AI 가 흔히 남기는 군더더기를 종류별로 찾는다.
//   [2026-10-17 사용자 지시] 린트를 세분화해 정책으로: 중복(dup.js) 말고도 쓰이지 않는 새 정의 · 디버그 흔적 · 남긴 할 일 · 주석 처리된 코드 ·
//   검사 억누르기 · 테스트 약화 · 하드코딩(개인 경로 · 비밀 모양) · 형식만 바뀐 파일.
//   정책: 기존 코드의 옛 흔적은 보지 않는다(새로 더한 줄만). 루프가 걸린 것을 모아 작업자에게 한 번만 돌려보내고, 남으면 막지 않고 보고한다.
//   끄기: 프로젝트 블록 quality: off(전부) · quality_off: ["debug", …](규칙별).
const fs = require('node:fs'), path = require('node:path');
const G = require('./git'), D = require('./dup');

const RULES = ['unused', 'debug', 'todo', 'commented', 'suppress', 'test-weaken', 'hardcoded', 'format-only'];
const CONF_EXT = /\.(csproj|vbproj|fsproj|props|targets|json|ya?ml|toml|ini|cfg|config|xml|xaml)$/i;
const JS = /\.(js|mjs|cjs|ts|tsx|jsx|vue|svelte)$/i, PY = /\.py$/i, CS = /\.(cs|java|kt|vb|fs|scala|swift|dart)$/i;

const DEBUG = [[JS, /\bconsole\.(log|debug|trace|dir)\s*\(|^\s*debugger\s*;?\s*$/], [PY, /\bbreakpoint\(\)|\b(i?pdb)\.set_trace\(/], [CS, /\bDebugger\.(Break|Launch)\(\)/]];
const TODO = /(\/\/|#|\/\*|\*|--|<!--)\s*.*\b(TODO|FIXME|XXX|HACK)\b/;
const SUPPRESS = /eslint-disable|@ts-ignore|@ts-nocheck|@ts-expect-error|#\s*noqa\b|#\s*type:\s*ignore|pylint:\s*disable|#\s*nosec\b|#pragma\s+warning\s+disable|SuppressMessage|NOSONAR|@SuppressWarnings|rubocop:disable|<NoWarn>|TreatWarningsAsErrors>\s*false/i;
const WEAKEN = /\b(it|test|describe|context|suite)\.(skip|only)\s*\(|\b(xit|xdescribe|xtest|fit|fdescribe)\s*\(|@pytest\.mark\.(skip|xfail)|\bpytest\.skip\(|\[Ignore\b|\bSkip\s*=\s*"|@Disabled\b|@Ignore\b|^\s*assert\s+True\s*$|expect\(true\)\.toBe\(true\)|Assert\.(True|IsTrue)\(\s*true\s*\)/;
const HARD_PATH = /\b[A-Za-z]:(\\\\|\\|\/)Users(\\\\|\\|\/)[^\\/\s"'`]+|\/home\/[a-z_][\w.-]*\/|\/Users\/[A-Za-z][\w.-]*\//;
const SECRET = /\b(ghp|gho|ghs|ghu|github_pat)_[A-Za-z0-9_]{20,}|\bAKIA[0-9A-Z]{16}\b|\bsk-[A-Za-z0-9]{20,}|-----BEGIN [A-Z ]*PRIVATE KEY-----|\bxox[baprs]-[A-Za-z0-9-]{10,}/;
// 주석 표시는 언어별로 — C# · JS 의 #if · #region 은 전처리 지시문이다. 문서 주석(/// · /** · *)은 코드가 아니다. [2026-10-17 실측 오탐]
const COMMENT_BY = [
  [/\.(js|mjs|cjs|ts|tsx|jsx|vue|svelte|cs|java|kt|go|rs|swift|c|cc|cpp|h|hpp|scala|dart|php|fs)$/i, /^\s*\/\/(?!\/)\s?(.*)$/],
  [/\.(py|rb|sh|ps1|ya?ml|toml)$/i, /^\s*#(?![!#])\s?(.*)$/], [/\.(sql|lua)$/i, /^\s*--\s?(.*)$/], [/\.vb$/i, /^\s*'\s?(.*)$/]];
const commentOf = (f, t) => { const m = COMMENT_BY.find(([ext]) => ext.test(f)); const c = m && m[1].exec(t); return c ? c[1] : null; };
const CODEY = /(\w+\s*\(.*\)\s*;?\s*$|[;{}]\s*$|^\s*(return|if|for|while|const|let|var|def|class|import|from|await|throw)\b|\w\s*[+\-*/]?=\s*\S)/;
const DEFS = [
  [PY, /^\s*(?:async\s+)?def\s+([A-Za-z_]\w*)\s*\(/], [PY, /^\s*class\s+([A-Za-z_]\w*)/],
  [JS, /^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*\*?\s*([A-Za-z_$][\w$]*)\s*\(/],
  [JS, /^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s+)?(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>/],
  [JS, /^\s*(?:export\s+)?(?:default\s+)?class\s+([A-Za-z_$][\w$]*)/],
  [CS, /^\s*(?:(?:public|private|protected|internal|static|async|virtual|sealed|abstract|partial|final|readonly|unsafe|extern|new)\s+)+(?!class\b|interface\b|struct\b|record\b|enum\b|override\b)[\w<>[\],.?]+(?:\s*<[^>]*>)?\s+([A-Za-z_]\w*)\s*\([^;]*$/],
];
const NOT_UNUSED = /^(main|Main|__\w+__|setUp|tearDown|setup|teardown|constructor|render|default)$|^(test|Test)/;
const MAX_BYTES = 512 * 1024;

const rel = f => f.replace(/\\/g, '/');
function readLines(abs) { try { const st = fs.statSync(abs); if (!st.isFile() || st.size > MAX_BYTES) return null; const b = fs.readFileSync(abs); if (b.includes(0)) return null; return b.toString('utf8').split(/\r?\n/); } catch { return null; } }

// → [{ rule, file, line, text }] — o: { off: [규칙 이름] }
function find(wt, base, o) {
  const off = new Set((o && o.off) || []);
  const on = r => !off.has(r);
  const untracked = new Set(G.statusEntries(wt).filter(e => e.code === '??').map(e => rel(e.path)));
  const modified = new Set(G.diffNames(wt, base, null, ['--diff-filter=M']).map(rel));
  const changed = [...new Set([...G.diffNames(wt, base, null, ['--diff-filter=AM']).map(rel), ...untracked])]
    .filter(f => !D.SKIP.test(f) && !/^\.harness\//.test(f) && fs.existsSync(path.join(wt, f)) && (D.CODE_EXT.test(f) || CONF_EXT.test(f)));
  const out = [], defs = [], amap = D.addedMap(wt, base);
  for (const f of changed) {
    const lines = readLines(path.join(wt, f)); if (!lines) continue;
    const added = untracked.has(f) ? new Set(lines.map((_, i) => i + 1)) : (amap.get(f) || new Set());
    const isTest = D.TEST.test(f), isCode = D.CODE_EXT.test(f);
    let run = [];
    const flushRun = () => { if (run.length >= 3 && on('commented')) out.push({ rule: 'commented', file: f, line: run[0], text: lines[run[0] - 1].trim().slice(0, 120) }); run = []; };
    for (let n = 1; n <= lines.length; n++) {
      const t = lines[n - 1];
      if (!added.has(n)) { flushRun(); continue; }
      const hit = (rule, text) => { if (on(rule)) out.push({ rule, file: f, line: n, text: (text || t.trim()).slice(0, 120) }); };
      if (SUPPRESS.test(t)) hit('suppress');
      if (isTest) { if (WEAKEN.test(t)) hit('test-weaken'); continue; }
      if (!isCode) continue;
      if (DEBUG.some(([ext, re]) => ext.test(f) && re.test(t))) hit('debug');
      if (TODO.test(t)) hit('todo');
      if (HARD_PATH.test(t) || SECRET.test(t)) hit('hardcoded', t.trim().replace(SECRET, m => `${m.slice(0, 6)}…`));
      const c = commentOf(f, t);
      if (c != null && CODEY.test(c) && !/<\/?\w+[^>]*>/.test(c) && !TODO.test(t) && !SUPPRESS.test(t)) run.push(n); else flushRun();
      if (on('unused')) for (const [ext, re] of DEFS) { if (!ext.test(f)) continue; const m = re.exec(t); if (m && !NOT_UNUSED.test(m[1]) && !/\boverride\b/.test(t)) { defs.push({ file: f, line: n, name: m[1], text: t }); break; } }
    }
    flushRun();
  }
  // 쓰이지 않는 새 정의: 저장소의 텍스트 파일 어디에도(정의한 줄 말고) 이름이 나오지 않는다 — XAML · 설정의 참조도 센다
  //   git grep(색인 · 여러 스레드)으로 찾는다 — [2026-10-17 실측] 파일을 모두 읽어 줄마다 훑으니 큰 .NET 저장소에서 30초가 걸렸다.
  //   이름 전부를 한 번의 git grep 으로(이름마다 따로 돌리니 큰 저장소에서 수십 초) — 그 결과 줄에서 이름별로 가른다.
  const ds = defs.slice(0, 40);
  if (ds.length) {
    const r = G.git(wt, ['grep', '-n', '-w', '-F', '-I', '--untracked', ...ds.flatMap(d => ['-e', d.name]), '--', '.', ':(exclude).harness'], { allowFail: true });
    const hits = r.out.split(/\r?\n/).filter(Boolean).map(rel);
    for (const d of ds) {
      const word = new RegExp(`(^|[^\\w$])${d.name.replace(/\$/g, '\\$')}(?![\\w$])`);
      const used = hits.some(l => { const m = /^(.*?):(\d+):(.*)$/.exec(l); return m && !(m[1] === d.file && Number(m[2]) === d.line) && word.test(m[3]); });
      if (!used) out.push({ rule: 'unused', file: d.file, line: d.line, text: d.name });
    }
  }
  // 형식만 바뀐 파일: 공백 · 빈 줄을 빼면 바뀐 것이 없다(범위 밖 재정렬)
  if (on('format-only')) {
    // --numstat 두 번(전체 · 공백 무시)으로 — 파일마다 git 을 띄우지 않는다. 공백을 무시하면 바뀐 줄이 0 인 수정 파일.
    const stat = extra => { const m = new Map(); for (const l of G.git(wt, ['-c', 'core.quotepath=off', 'diff', '--numstat', '--no-renames', ...extra, base], { allowFail: true }).out.split(/\r?\n/)) { const p = /^(\d+|-)\t(\d+|-)\t(.+)$/.exec(l); if (p) m.set(rel(p[3]), p[1] === '-' ? -1 : Number(p[1]) + Number(p[2])); } return m; };
    const all = stat([]), ws = stat(['-w', '--ignore-blank-lines']);
    for (const f of modified) {
      if (D.SKIP.test(f) || /^\.harness\//.test(f) || !(all.get(f) > 0)) continue;
      if (!(ws.get(f) > 0)) out.push({ rule: 'format-only', file: f, line: 0, text: '공백 · 들여쓰기만 바뀌었다' });
    }
  }
  return out.slice(0, 40);
}

// 규칙 이름 → 사람이 읽는 이름(보고 · 지시)
const LABEL_KO = { dup: '중복', unused: '쓰이지 않는 새 정의', debug: '디버그 흔적', todo: '남긴 할 일', commented: '주석 처리된 코드', suppress: '검사 억누르기', 'test-weaken': '테스트 약화', hardcoded: '하드코딩(개인 경로 · 비밀)', 'format-only': '형식만 바뀐 파일' };
const LABEL_EN = { dup: 'duplicate code', unused: 'new definitions nothing uses', debug: 'debug leftovers', todo: 'TODO/FIXME left behind', commented: 'commented-out code', suppress: 'lint/type checks suppressed', 'test-weaken': 'tests weakened (skip/only/always-true)', hardcoded: 'hard-coded personal paths or secrets', 'format-only': 'files with only whitespace/indentation changes' };

module.exports = { find, RULES, LABEL_KO, LABEL_EN };
