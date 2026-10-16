'use strict';
// 중복 코드 — 작업이 새로 더한 코드가 저장소의 다른 곳(또는 자기가 더한 다른 곳)을 블록째 베꼈는가.
//   [2026-10-16 사용자 지시 · 영상 「쓰레기 코드 없애는 법」] AI 는 이미 있는 것을 재사용하지 않고 다시 쓴다.
//   판정이 아니라 결정적 검사다: 공백을 뺀 줄이 minLines(기본 8) 줄 연달아 같으면 중복. 의미 있는 줄만 센다(빈 줄 · 괄호만 · 주석만 · 짧은 줄 제외).
//   보는 것: 작업이 바꾼 코드 파일에서 "새로 더한 줄로만 된" 창. 테스트 · 생성 파일 · 빌드 산출물은 보지 않는다.
const fs = require('node:fs'), path = require('node:path'), crypto = require('node:crypto');
const G = require('./git');

const CODE_EXT = /\.(js|mjs|cjs|ts|tsx|jsx|py|cs|vb|fs|java|kt|go|rs|rb|php|swift|c|cc|cpp|h|hpp|vue|svelte|scala|dart|lua|ps1|sh)$/i;
const SKIP = /(^|\/)(node_modules|dist|build|bin|obj|out|vendor|\.harness|\.harness-worktrees|\.git|migrations?)\/|\.min\.|\.(designer|g|generated)\.[a-z]+$|-lock\.|\.lock$/i;
const TEST = /(^|\/)(tests?|__tests__|specs?)\/|(^|\/)test_[^/]+\.py$|[._-](test|spec)s?\.[A-Za-z0-9]+$|(^|\/)[^/]*Tests?\.(cs|fs|vb|java|kt)$/i;
const MAX_FILES = 6000, MAX_BYTES = 512 * 1024;

// 의미 있는 줄만(공백 제거) — 빈 줄 · 괄호/구두점만 · 주석만 · 6글자 미만은 뺀다.
function meaningful(line) {
  const s = line.replace(/\s+/g, '');
  if (s.length < 6) return null;
  if (/^[{}()[\];,]+$/.test(s)) return null;
  if (/^(\/\/|#|\*|\/\*|<!--|--|'''|""")/.test(s)) return null;
  return s;
}
// 파일 → [{ n: 줄 번호(1부터), s: 정규화한 줄 }]
function linesOf(abs) {
  let st; try { st = fs.statSync(abs); } catch { return []; }
  if (!st.isFile() || st.size > MAX_BYTES) return [];
  let text; try { text = fs.readFileSync(abs, 'utf8'); } catch { return []; }
  const out = [];
  text.split(/\r?\n/).forEach((l, i) => { const s = meaningful(l); if (s) out.push({ n: i + 1, s }); });
  return out;
}
const h = arr => crypto.createHash('sha1').update(arr.join('\n')).digest('hex');
// 작업이 더한 줄 번호들(기준 커밋 대비 · 작업 트리 그대로)
function addedLines(wt, base, file) {
  const r = G.git(wt, ['diff', '-U0', '--no-color', '--no-ext-diff', base, '--', file], { allowFail: true });
  const set = new Set();
  if (!r.ok) return set;
  for (const m of r.out.matchAll(/^@@ -\S+ \+(\d+)(?:,(\d+))? @@/gm)) { const a = Number(m[1]), n = m[2] == null ? 1 : Number(m[2]); for (let i = 0; i < n; i++) set.add(a + i); }
  return set;
}
const eligible = f => CODE_EXT.test(f) && !SKIP.test(f) && !TEST.test(f);

// → [{ file, start, end, lines, other: 'path:start-end' }] (최대 10)
function find(wt, base, o) {
  const K = Math.max(4, Number(o && o.minLines) || 8);
  const changed = G.diffNames(wt, base, null, ['--diff-filter=AM']).concat(G.statusEntries(wt).filter(e => e.code === '??').map(e => e.path))
    .map(f => f.replace(/\\/g, '/')).filter((f, i, a) => a.indexOf(f) === i && eligible(f) && fs.existsSync(path.join(wt, f)));
  if (!changed.length) return [];
  const exts = new Set(changed.map(f => path.extname(f).toLowerCase()));
  // 색인: 같은 확장자의 모든 파일(추적 + 새 파일)의 K줄 창 → 위치들
  const all = G.git(wt, ['ls-files', '-co', '--exclude-standard'], { allowFail: true }).out.split(/\r?\n/).filter(Boolean)
    .map(f => f.replace(/\\/g, '/')).filter(f => exts.has(path.extname(f).toLowerCase()) && !SKIP.test(f) && !TEST.test(f)).slice(0, MAX_FILES);
  const index = new Map(), cache = new Map();
  for (const f of all) {
    const L = linesOf(path.join(wt, f)); cache.set(f, L);
    for (let i = 0; i + K <= L.length; i++) {
      const k = h(L.slice(i, i + K).map(x => x.s));
      if (!index.has(k)) index.set(k, []);
      index.get(k).push({ file: f, start: L[i].n, end: L[i + K - 1].n });
    }
  }
  const out = [];
  for (const f of changed) {
    const L = cache.get(f) || linesOf(path.join(wt, f));
    const added = addedLines(wt, base, f);
    let cur = null;
    for (let i = 0; i + K <= L.length; i++) {
      const win = L.slice(i, i + K);
      if (!win.every(x => added.has(x.n))) continue;
      const here = { start: win[0].n, end: win[K - 1].n };
      const others = (index.get(h(win.map(x => x.s))) || []).filter(x => !(x.file === f && x.start <= here.end && here.start <= x.end));
      if (!others.length) continue;
      if (cur && here.start <= cur.end + 1) { cur.end = here.end; continue; }
      if (cur) out.push(cur);
      cur = { file: f, start: here.start, end: here.end, other: `${others[0].file}:${others[0].start}-${others[0].end}` };
    }
    if (cur) out.push(cur);
  }
  // 같은 블록 한 쌍은 한 번만(새 코드 안에서 서로를 가리키는 두 블록) — 뒤의 것만 남긴다
  const seen = new Set(), uniq = [];
  for (const b of out) { const key = [b.file + ':' + b.start, b.other.replace(/-\d+$/, '')].sort().join('|'); if (seen.has(key)) continue; seen.add(key); uniq.push({ ...b, lines: b.end - b.start + 1 }); }
  return uniq.slice(0, 10);
}

module.exports = { find, meaningful };
