'use strict';
// v5 관리 문서 — 사용자가 요청할 때만 만든다. 세 종류만:
//   prd → docs/prds/ (분석 · 요구사항) · coordination → docs/coordinations/ (다른 프로젝트와의 통신) · design → docs/designs/ (디자인 · 와이어프레임 · 스토리보드)
//   만든 문서는 관리한다: front matter(kind · title · status · created · updated · tasks · supersedes · superseded_by [· with · direction]) ·
//   색인(docs/README.md 의 관리 블록) · 검사(doc check) · 이력(<git-common-dir>/harness/docs-history/ — docs 가 git 밖이어도 되돌릴 수 있게).
//   아무것도 자동으로 만들지 않는다 — go 때 생성 없음. go --doc 은 읽기 전용 명세로 넘기고, accept 때 문서의 tasks 에 작업 id 를 더한다.
const fs = require('node:fs'), path = require('node:path'), os = require('node:os'), crypto = require('node:crypto');
const { spawnSync } = require('node:child_process');
const S = require('./state'), G = require('./git');

const KINDS = { prd: 'prds', coordination: 'coordinations', design: 'designs' };
const ALIASES = { prd: 'prd', prds: 'prd', coordination: 'coordination', coordinations: 'coordination', coord: 'coordination', design: 'design', designs: 'design' };
const STATUSES = ['draft', 'active', 'done', 'superseded'];
const DIRECTIONS = ['outgoing', 'incoming'];
const BEGIN = '<!-- harness:docs:begin -->', END = '<!-- harness:docs:end -->';
const INDEX_REL = 'docs/README.md';
const MANAGED_RE = /^docs\/(prds|coordinations|designs)\/.+\.md$/i;
const VERSION_RE = /^\d{8}-\d{6}(-\d+)?$/;
const TITLES = { prd: 'PRD — 분석 · 요구사항', coordination: '협업 — 다른 프로젝트와의 통신', design: '디자인 — 디자인 · 와이어프레임 · 스토리보드' };
// 설치기 · check 가 git 추적 여부를 볼 대표 경로(없는 파일이어도 check-ignore 는 판정한다).
const TARGETS = ['docs/prds/', 'docs/coordinations/', 'docs/designs/', INDEX_REL];
const PROBES = { 'docs/prds/': 'docs/prds/_probe.md', 'docs/coordinations/': 'docs/coordinations/_probe.md', 'docs/designs/': 'docs/designs/_probe.md', [INDEX_REL]: INDEX_REL };

const usage = msg => Object.assign(new Error(msg), { code: 'USAGE' });
const docErr = msg => Object.assign(new Error(msg), { code: 'DOC' });
const p2 = n => String(n).padStart(2, '0');
function today(d) { d = d || new Date(); return `${d.getFullYear()}-${p2(d.getMonth() + 1)}-${p2(d.getDate())}`; }
function stamp(d) { d = d || new Date(); return `${d.getFullYear()}${p2(d.getMonth() + 1)}${p2(d.getDate())}-${p2(d.getHours())}${p2(d.getMinutes())}${p2(d.getSeconds())}`; }
function validDate(s) {
  if (typeof s !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(s)) return false;
  const [y, m, d] = s.split('-').map(Number), t = new Date(Date.UTC(y, m - 1, d));
  return t.getUTCFullYear() === y && t.getUTCMonth() === m - 1 && t.getUTCDate() === d;
}
function normKind(k) {
  const v = ALIASES[String(k || '').toLowerCase()];
  if (!v) throw usage(`unknown document kind: ${JSON.stringify(k)} (prd | coordination | design)`);
  return v;
}
function slugify(title) {
  const s = String(title || '').normalize('NFC').toLowerCase().replace(/[^\p{L}\p{M}\p{N}]+/gu, '-').replace(/^-+|-+$/g, '');
  return [...s].slice(0, 60).join('').replace(/-+$/, '') || 'untitled';
}
const rootOf = r => S.mainRoot(r || process.cwd());
const absOf = (root, rel) => path.join(root, ...rel.split('/'));
const readText = f => { try { return fs.readFileSync(f, 'utf8'); } catch { return null; } };
const eolOf = t => (t && /\r\n/.test(t) ? '\r\n' : '\n');
const withEol = (t, eol) => (eol === '\n' ? t : t.replace(/\r?\n/g, eol));
const key = p => (S.IS_WIN ? p.toLowerCase() : p);
function writeAtomic(file, text) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  const tmp = `${file}.${process.pid}.${crypto.randomBytes(3).toString('hex')}.tmp`;
  fs.writeFileSync(tmp, text);
  for (let i = 0; ; i++) {
    try { fs.renameSync(tmp, file); return; }
    catch (e) { if (i >= 8 || !/^(EPERM|EBUSY|EACCES)$/.test(e.code)) { try { fs.unlinkSync(tmp); } catch { /* 없음 */ } throw e; } S.sleepSync(25 * (i + 1)); }
  }
}

// 문서 경로 → 저장소 상대 posix. 절대 경로면 루트 기준으로 바꾼다. 관리 폴더 밖이면 거부.
function docRel(root, p) {
  if (!p) throw usage('a document path is required');
  const R = require('../hooks/_common').real;   // 실경로로 비교(심볼릭 링크 · 짧은 이름)
  const abs = R(path.isAbsolute(p) ? path.resolve(p) : path.resolve(root, p));
  const rel = path.relative(R(root), abs).split(path.sep).join('/');
  if (!rel || rel.startsWith('..') || path.isAbsolute(rel) || !MANAGED_RE.test(rel)) throw usage(`not a managed document: ${p} (docs/prds/ · docs/coordinations/ · docs/designs/ 의 .md)`);
  return rel;
}
// front matter 안의 경로 값(supersedes · superseded_by) → 저장소 상대. docs/ 로 시작하면 그대로, 아니면 그 문서 폴더 기준.
function refPath(fromRel, v) {
  if (!v || typeof v !== 'string') return '';
  const s = v.replace(/\\/g, '/').replace(/^\.\//, '');
  return s.startsWith('docs/') ? path.posix.normalize(s) : path.posix.normalize(path.posix.join(path.posix.dirname(fromRel), s));
}

// ── front matter (평평한 키 · 단순 [a, b] 목록만) ────────────────────────
function splitList(inner) {
  const items = []; let cur = '', q = null;
  for (let i = 0; i < inner.length; i++) {
    const c = inner[i];
    if (q) { cur += c; if (c === '\\' && q === '"' && i + 1 < inner.length) { cur += inner[++i]; continue; } if (c === q) q = null; continue; }
    if (c === '"' || c === "'") { q = c; cur += c; continue; }
    if (c === ',') { items.push(cur); cur = ''; continue; }
    cur += c;
  }
  items.push(cur);
  return items.map(x => parseValue(x)).filter(x => x !== '');
}
function parseValue(src) {
  const s = String(src).trim();
  if (!s) return '';
  if (s[0] === '"') { const m = /^"((?:[^"\\]|\\.)*)"/.exec(s); if (m) { try { return JSON.parse(`"${m[1]}"`); } catch { return m[1]; } } }
  if (s[0] === "'") { const m = /^'((?:[^']|'')*)'/.exec(s); if (m) return m[1].replace(/''/g, "'"); }
  if (s[0] === '[') {
    let q = null, end = -1;
    for (let i = 1; i < s.length; i++) { const c = s[i]; if (q) { if (c === '\\' && q === '"') i++; else if (c === q) q = null; continue; } if (c === '"' || c === "'") q = c; else if (c === ']') { end = i; break; } }
    if (end > 0) return splitList(s.slice(1, end));
  }
  return s.replace(/\s+#.*$/, '').trim();
}
function scalar(v, inList) {
  const s = String(v);
  if (s === '') return '""';
  if (/^[\s"'[\]{}>|*&!%@`#?:,-]|\s$|: |\s#|[\r\n\t]/.test(s) || (inList && /[,\]]/.test(s))) return JSON.stringify(s);
  return s;
}
function lineOf(k, v) {
  if (Array.isArray(v)) return `${k}: [${v.map(x => scalar(x, true)).join(', ')}]`;
  return v == null || v === '' ? `${k}:` : `${k}: ${scalar(v)}`;
}
function parseDoc(text) {
  const bom = text.startsWith('﻿'), t = bom ? text.slice(1) : text;
  const doc = { bom, eol: eolOf(t), fm: false, entries: [], data: {}, errors: [], body: t };
  const open = /^---[ \t]*\r?\n/.exec(t);
  if (!open) return doc;
  const rest = t.slice(open[0].length);
  const close = /^---[ \t]*(?:\r?\n|$)/m.exec(rest);
  if (!close) { doc.errors.push('front matter 가 닫히지 않았다(두 번째 --- 줄이 없다)'); return doc; }
  const inner = rest.slice(0, close.index);
  doc.fm = true;
  doc.body = rest.slice(close.index + close[0].length);
  const lines = inner.split(/\r?\n/);
  if (lines.length && lines[lines.length - 1] === '') lines.pop();
  for (const line of lines) {
    const m = /^([A-Za-z_][\w-]*)[ \t]*:(.*)$/.exec(line);
    if (!m) {
      if (line.trim() && !line.trim().startsWith('#')) doc.errors.push(`front matter 에서 읽을 수 없는 줄: ${line.trim().slice(0, 80)}`);
      doc.entries.push({ key: null, line });
      continue;
    }
    if (Object.prototype.hasOwnProperty.call(doc.data, m[1])) doc.errors.push(`front matter 키가 두 번 있다: ${m[1]}`);
    const value = parseValue(m[2]);
    doc.data[m[1]] = value;
    doc.entries.push({ key: m[1], line, value });
  }
  return doc;
}
function setField(doc, k, v) {
  const line = lineOf(k, v);
  const e = doc.entries.find(x => x.key === k);
  if (e) { e.line = line; e.value = v; } else doc.entries.push({ key: k, line, value: v });
  doc.data[k] = v;
}
function serialize(doc) {
  const { eol } = doc;
  const head = ['---', ...doc.entries.map(e => e.line), '---'].join(eol) + eol;
  return (doc.bom ? '﻿' : '') + head + doc.body;
}
const listOf = v => (Array.isArray(v) ? v : v ? [v] : []);

// 문서 읽기 — {rel, abs, exists, fm, data, entries, body, errors, text}
function readDoc(root, rel) {
  const abs = absOf(root, rel), text = readText(abs);
  if (text === null) return { rel, abs, exists: false, fm: false, data: {}, entries: [], errors: [], body: '' };
  return { rel, abs, exists: true, text, ...parseDoc(text) };
}

// ── 이력 ──────────────────────────────────────────────────────────────
function historyRoot(root) { return path.join(S.paths(root).harnessDir, 'docs-history'); }
function historyDir(root, rel) { return path.join(historyRoot(root), rel.split('/').join('__')); }
// 바꾸기 전 판을 남긴다(파일이 있을 때만). 같은 초에 여러 번이면 -2, -3…
function snapshot(root, rel) {
  const abs = absOf(root, rel);
  if (!fs.existsSync(abs)) return null;
  const dir = historyDir(root, rel);
  fs.mkdirSync(dir, { recursive: true });
  const s = stamp();
  for (let n = 1; ; n++) {
    const name = n === 1 ? s : `${s}-${n}`;
    try { fs.copyFileSync(abs, path.join(dir, `${name}.md`), fs.constants.COPYFILE_EXCL); return name; }
    catch (e) { if (e.code !== 'EEXIST') throw e; }
  }
}
const verKey = v => { const m = /^(\d{8}-\d{6})(?:-(\d+))?$/.exec(v); return m ? [m[1], Number(m[2] || 1)] : [v, 0]; };
function history(rootIn, p) {
  const root = rootOf(rootIn), rel = docRel(root, p), dir = historyDir(root, rel);
  let names = []; try { names = fs.readdirSync(dir); } catch { return []; }
  return names.filter(n => n.endsWith('.md') && VERSION_RE.test(n.slice(0, -3))).map(n => {
    const f = path.join(dir, n), st = fs.statSync(f);
    return { version: n.slice(0, -3), file: f, bytes: st.size, at: st.mtime.toISOString() };
  }).sort((a, b) => { const x = verKey(a.version), y = verKey(b.version); return x[0] < y[0] ? -1 : x[0] > y[0] ? 1 : x[1] - y[1]; });
}
function restore(rootIn, p, version) {
  const root = rootOf(rootIn), rel = docRel(root, p);
  if (!VERSION_RE.test(String(version || ''))) throw usage(`invalid version: ${JSON.stringify(version)} (expected YYYYMMDD-HHMMSS[-n] from doc history)`);
  const src = path.join(historyDir(root, rel), `${version}.md`);
  if (!fs.existsSync(src)) throw docErr(`no version ${version} for ${rel} — see: node harness/cli.js doc history ${rel}`);
  const saved = snapshot(root, rel);
  writeAtomic(absOf(root, rel), fs.readFileSync(src));
  const idx = writeIndex(root);
  return { path: rel, restored: version, saved, index_changed: idx.changed };
}
function saveDoc(root, doc) {
  snapshot(root, doc.rel);
  writeAtomic(doc.abs, serialize(doc));
}

// ── 목록 ──────────────────────────────────────────────────────────────
function walkFiles(dir, base) {
  const out = [];
  let ents = []; try { ents = fs.readdirSync(dir, { withFileTypes: true }); } catch { return out; }
  for (const e of ents) {
    if (e.name.startsWith('.')) continue;
    const p = path.join(dir, e.name);
    if (e.isDirectory()) { if (e.name !== 'node_modules') out.push(...walkFiles(p, base)); }
    else if (e.isFile()) out.push(path.relative(base, p).split(path.sep).join('/'));
  }
  return out;
}
function scan(root) {
  const docs = [], attachments = [];
  for (const [kind, dir] of Object.entries(KINDS)) {
    for (const rel of walkFiles(path.join(root, 'docs', dir), root)) {
      if (/\.md$/i.test(rel)) docs.push({ folderKind: kind, ...readDoc(root, rel) });
      else if (kind === 'design') attachments.push(rel);
    }
  }
  return { docs, attachments };
}
function summaryOf(d) {
  const x = d.data;
  const s = { path: d.rel, kind: typeof x.kind === 'string' && x.kind ? x.kind : d.folderKind, status: d.fm ? (x.status || '') : '?', created: x.created || '', updated: x.updated || '',
    title: d.fm ? String(x.title || '') : '(front matter 없음)', tasks: listOf(x.tasks), supersedes: x.supersedes || '', superseded_by: x.superseded_by || '' };
  if (d.folderKind === 'coordination') { s.with = x.with || ''; s.direction = x.direction || ''; }
  return s;
}
const newestFirst = (a, b) => (a.created === b.created ? (a.path < b.path ? 1 : a.path > b.path ? -1 : 0) : a.created < b.created ? 1 : -1);
function list(rootIn, o) {
  const root = rootOf(rootIn), opt = o || {};
  const kind = opt.kind ? normKind(opt.kind) : null;
  if (opt.status && !STATUSES.includes(opt.status)) throw usage(`invalid status: ${opt.status} (${STATUSES.join(' | ')})`);
  return scan(root).docs.filter(d => !kind || d.folderKind === kind).map(summaryOf)
    .filter(s => !opt.status || s.status === opt.status).sort(newestFirst);
}
function formatList(rows) {
  if (!rows.length) return '문서 없음 (만들려면: node harness/cli.js doc new <prd|coordination|design> "<제목>")';
  const cols = [['path', '경로'], ['kind', '종류'], ['status', '상태'], ['updated', '갱신'], ['title', '제목']];
  if (rows.some(r => r.kind === 'coordination')) cols.push(['with', '상대'], ['direction', '방향']);
  const cell = (r, k) => String(r[k] == null ? '' : r[k]);
  const w = cols.map(([k, h]) => Math.max(h.length, ...rows.map(r => cell(r, k).length)));
  const line = vals => vals.map((v, i) => (i === vals.length - 1 ? v : v.padEnd(w[i]))).join('  ').replace(/\s+$/, '');
  return [line(cols.map(c => c[1])), ...rows.map(r => line(cols.map(([k]) => cell(r, k))))].join('\n');
}

// ── 링크 · 첨부 ────────────────────────────────────────────────────────
function linksOf(docRelPath, body) {
  const out = new Set(), raw = [];
  let m;
  const md = /!?\[[^\]]*\]\(\s*<?([^)\s>]+)>?(?:\s+["'][^)]*["'])?\s*\)/g;
  while ((m = md.exec(body))) raw.push(m[1]);
  const attr = /\b(?:src|href)\s*=\s*["']([^"']+)["']/gi;
  while ((m = attr.exec(body))) raw.push(m[1]);
  const ref = /^[ \t]*\[[^\]]+\]:[ \t]*<?(\S+?)>?(?:[ \t]|$)/gm;
  while ((m = ref.exec(body))) raw.push(m[1]);
  for (let t of raw) {
    t = t.replace(/[#?].*$/, '');
    if (!t || /^[a-z][a-z0-9+.-]*:/i.test(t) || t.startsWith('//')) continue;
    try { t = decodeURIComponent(t); } catch { /* 그대로 */ }
    t = t.replace(/\\/g, '/');
    out.add(t.startsWith('/') ? path.posix.normalize(t.slice(1)) : path.posix.normalize(path.posix.join(path.posix.dirname(docRelPath), t)));
  }
  return out;
}
// 디자인 문서 → 그 문서가 링크한 첨부(저장소 상대) · 어느 문서도 링크하지 않은 첨부
function attachmentMap(docs, attachments) {
  const byKey = new Map(attachments.map(a => [key(a), a]));
  const map = new Map(), linked = new Set();
  for (const d of docs) {
    if (d.folderKind !== 'design') continue;
    const hits = [];
    for (const l of linksOf(d.rel, d.body || '')) { const a = byKey.get(key(l)); if (a) { hits.push(a); linked.add(a); } }
    map.set(d.rel, [...new Set(hits)].sort());
  }
  return { map, unlinked: attachments.filter(a => !linked.has(a)).sort() };
}

// ── 색인 ──────────────────────────────────────────────────────────────
const esc = s => String(s == null ? '' : s).replace(/\r?\n/g, ' ').replace(/\|/g, '\\|');
const escLink = s => esc(s).replace(/([[\]])/g, '\\$1');
const href = rel => (rel.startsWith('docs/') ? rel.slice(5) : `../${rel}`).replace(/ /g, '%20').replace(/\(/g, '%28').replace(/\)/g, '%29');
function renderBlock(docs, amap) {
  const L = [BEGIN, '<!-- `node harness/cli.js doc index` 가 쓰는 블록이다 — 손으로 고치지 않는다(다음 색인이 덮어쓴다). -->'];
  for (const kind of Object.keys(KINDS)) {
    const rows = docs.filter(d => d.fm && d.folderKind === kind).map(d => ({ d, s: summaryOf(d) })).sort((a, b) => newestFirst(a.s, b.s));
    L.push('', `### ${TITLES[kind]} (\`docs/${KINDS[kind]}/\`)`, '');
    if (!rows.length) { L.push('_(없음)_'); continue; }
    const head = kind === 'prd' ? ['문서', '상태', '갱신', '작업'] : kind === 'coordination' ? ['문서', '상대', '방향', '상태', '갱신', '작업'] : ['문서', '상태', '갱신', '첨부', '작업'];
    L.push(`| ${head.join(' | ')} |`, `| ${head.map(() => '---').join(' | ')} |`);
    for (const { d, s } of rows) {
      const sup = s.status === 'superseded';
      const link = `[${escLink(s.title || d.rel)}](${href(d.rel)})`;
      const by = sup && s.superseded_by ? refPath(d.rel, s.superseded_by) : '';
      const status = sup ? `superseded${by ? ` → [${escLink(path.posix.basename(by, '.md'))}](${href(by)})` : ''}` : esc(s.status);
      const cells = [sup ? `~~${link}~~` : link];
      if (kind === 'coordination') cells.push(esc(s.with), esc(s.direction));
      cells.push(status, esc(s.updated));
      if (kind === 'design') cells.push((amap.map.get(d.rel) || []).map(a => `[${escLink(path.posix.basename(a))}](${href(a)})`).join(' · '));
      cells.push(esc(s.tasks.join(', ')));
      L.push(`| ${cells.join(' | ')} |`);
    }
  }
  L.push('', END);
  return L.join('\n');
}
function planIndex(root) {
  const { docs, attachments } = scan(root);
  const amap = attachmentMap(docs, attachments);
  const block = renderBlock(docs, amap);
  const file = absOf(root, INDEX_REL), cur = readText(file);
  let next;
  const b = cur === null ? -1 : cur.indexOf(BEGIN), e = b >= 0 ? cur.indexOf(END, b) : -1;
  if (cur === null) next = block + '\n';
  else {
    const eol = eolOf(cur), blk = withEol(block, eol);
    if (b >= 0 && e >= 0) next = cur.slice(0, b) + blk + cur.slice(e + END.length);
    else next = cur + (cur === '' ? '' : cur.endsWith(eol) ? eol : eol + eol) + blk + eol;
  }
  return { file, cur, next, hasBlock: b >= 0 && e >= 0, docs, attachments, amap };
}
function writeIndex(rootIn) {
  const root = rootOf(rootIn), p = planIndex(root);
  if (p.cur === p.next) return { path: INDEX_REL, changed: false };
  writeAtomic(p.file, p.next);
  return { path: INDEX_REL, changed: true };
}

// ── 새 문서 ────────────────────────────────────────────────────────────
function skeleton(kind, title, o) {
  const h = s => `## ${s}\n\n`;
  if (kind === 'prd') return `# ${title}\n\n` + ['배경', '목표', '요구사항', '범위 밖', '완료 기준', '열린 질문'].map(h).join('');
  if (kind === 'coordination') {
    return `# ${title}\n\n## 상대\n\n- 프로젝트: ${o.with || ''}\n- 방향: ${o.direction === 'incoming' ? '받음(incoming)' : '보냄(outgoing)'}\n\n` + ['요청', '응답', '합의', '기한'].map(h).join('');
  }
  return `# ${title}\n\n` + h('목적') + h('화면·흐름') +
    '## 첨부\n\n<!-- 이미지 · HTML 은 docs/designs/ 에 두고 이 문서에서 상대 경로로 링크한다. 링크되지 않은 첨부는 doc check 가 알린다. -->\n\n' + h('결정');
}
function stripFrontMatter(text) {
  const t = text.replace(/^﻿/, '');
  const d = parseDoc(t);
  return d.fm ? d.body : t;
}
function newDoc(o) {
  const root = rootOf(o.root);
  const kind = normKind(o.kind);
  const title = String(o.title || '').replace(/\s+/g, ' ').trim();
  if (!title) throw usage('doc new needs a title');
  if (kind !== 'coordination' && (o.with != null || o.direction != null)) throw usage('--with / --direction are for coordination documents only');
  const direction = kind === 'coordination' ? (o.direction || 'outgoing') : null;
  if (direction && !DIRECTIONS.includes(direction)) throw usage(`--direction must be ${DIRECTIONS.join(' or ')}`);
  let body;
  if (o.fromFile != null) {
    const t = readText(path.resolve(o.fromFile));
    if (t === null) throw usage(`cannot read --from-file ${o.fromFile}`);
    body = stripFrontMatter(t);
  } else body = skeleton(kind, title, { with: o.with, direction });
  const day = o.today || today();
  const entries = [['kind', kind], ['title', title], ['status', 'draft'], ['created', day], ['updated', day], ['tasks', []], ['supersedes', ''], ['superseded_by', '']];
  if (kind === 'coordination') entries.push(['with', o.with || ''], ['direction', direction]);
  const eol = o.fromFile != null ? eolOf(body) : '\n';
  const text = ['---', ...entries.map(([k, v]) => lineOf(k, v)), '---'].join(eol) + eol + body;
  const dir = path.join(root, 'docs', KINDS[kind]);
  fs.mkdirSync(dir, { recursive: true });
  const stem = `${day}-${slugify(title)}`;
  for (let n = 1; ; n++) {
    const name = n === 1 ? `${stem}.md` : `${stem}-${n}.md`;
    const abs = path.join(dir, name);
    try { fs.writeFileSync(abs, text, { flag: 'wx' }); }
    catch (e) { if (e.code === 'EEXIST') continue; throw e; }
    const rel = `docs/${KINDS[kind]}/${name}`;
    const idx = writeIndex(root);
    return { path: rel, abs, kind, index_changed: idx.changed, tracking: trackingOf(root, rel) };
  }
}

// ── 상태 ──────────────────────────────────────────────────────────────
function loadManaged(root, rel) {
  const d = readDoc(root, rel);
  if (!d.exists) throw docErr(`no such document: ${rel}`);
  if (!d.fm) throw docErr(`${rel} has no front matter — not a managed document (doc check lists it)`);
  return d;
}
function setStatus(o) {
  const root = rootOf(o.root);
  const status = String(o.status || '');
  if (!STATUSES.includes(status)) throw usage(`invalid status: ${JSON.stringify(o.status)} (${STATUSES.join(' | ')})`);
  const rel = docRel(root, o.path);
  if (status === 'superseded' && !o.by) throw usage('status superseded needs --by <the document that replaces it>');
  if (status !== 'superseded' && o.by) throw usage('--by is only for status superseded');
  const d = loadManaged(root, rel);
  const day = today(), from = d.data.status || '';
  const touched = new Map([[rel, d]]);
  const get = r => { if (!touched.has(r)) touched.set(r, loadManaged(root, r)); return touched.get(r); };
  let byRel = null;
  if (status === 'superseded') {
    byRel = docRel(root, o.by);
    if (key(byRel) === key(rel)) throw usage('a document cannot supersede itself');
    get(byRel);
  }
  // 옛 대체 링크를 푼다(가리키던 문서의 supersedes 가 여기를 가리키면 비운다).
  const prev = refPath(rel, d.data.superseded_by);
  if (prev && (!byRel || key(prev) !== key(byRel))) {
    const pd = readDoc(root, prev);
    if (pd.exists && pd.fm && key(refPath(prev, pd.data.supersedes)) === key(rel)) { touched.set(prev, pd); setField(pd, 'supersedes', ''); setField(pd, 'updated', day); }
    setField(d, 'superseded_by', '');
  }
  if (byRel) {
    const other = get(byRel);
    setField(other, 'supersedes', rel); setField(other, 'updated', day);
    setField(d, 'superseded_by', byRel);
  }
  setField(d, 'status', status); setField(d, 'updated', day);
  for (const x of touched.values()) saveDoc(root, x);
  const idx = writeIndex(root);
  return { path: rel, from, to: status, by: byRel, index_changed: idx.changed };
}

// ── git 추적 여부 ──────────────────────────────────────────────────────
// check-ignore -v -n -z: 경로마다 source · line · pattern · path. 부정 패턴(!…)이 마지막으로 맞으면 무시되지 않는다.
function ignoreProbe(root, paths) {
  const r = G.git(root, ['check-ignore', '-v', '-n', '-z', '--stdin'], { allowFail: true, input: paths.join('\0') + '\0' });
  const f = r.out.split('\0'), out = new Map();
  for (let i = 0; i + 3 < f.length; i += 4) {
    const [source, line, pattern, p] = f.slice(i, i + 4);
    out.set(p, { path: p, ignored: !!pattern && !pattern.startsWith('!'), source, line: Number(line) || null, pattern });
  }
  return paths.map(p => out.get(p) || { path: p, ignored: false, source: '', line: null, pattern: '' });
}
function isTracked(root, rel) { return !!G.git(root, ['ls-files', '-z', '--', `:(literal)${rel}`], { allowFail: true }).out; }
const causeOf = h => `${h.source}:${h.line} \`${h.pattern}\``;
function trackingOf(root, rel) {
  if (isTracked(root, rel)) return 'git';
  return ignoreProbe(root, [rel])[0].ignored ? 'ignored' : 'untracked';
}
// 관리 폴더 · README 가 git 에서 무시되는가 — 폴더에 실제 문서가 있으면 그 파일로, 없으면 대표 경로로 본다.
function tracking(rootIn) {
  const root = rootOf(rootIn);
  const probe = TARGETS.map(t => {
    if (t === INDEX_REL) return t;
    const real = walkFiles(path.join(root, ...t.split('/')), root).find(f => /\.md$/i.test(f));
    return real || PROBES[t];
  });
  return ignoreProbe(root, probe).map((h, i) => ({ target: TARGETS[i], ignored: h.ignored && !(TARGETS[i] !== INDEX_REL && isTracked(root, h.path)), source: h.source, line: h.line, pattern: h.pattern }));
}

// ── 설치기용: .gitignore 관리 블록 ──────────────────────────────────────
// 실측(git 2.53): 부모 폴더가 제외되면(`docs/`) 그 안을 `!docs/prds/` 로 다시 넣지 못한다 — 하지만 뒤에 `!docs/` 로 폴더를 다시 열고
//   `docs/*` 로 나머지를 다시 무시하면 된다. `docs/**` 는 파일 단위라 `!docs/prds/**` 가 있어야 한다.
//   패턴이 docs 폴더 자체를 제외하는지는 빈 임시 저장소에 그 패턴만 두고 실제 폴더로 본다(없는 경로로는 폴더인지 알 수 없다).
function patternExcludesDir(pattern, dir) {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'harness-gi-'));
  try {
    const run = args => spawnSync('git', args, { cwd: tmp, encoding: 'utf8', windowsHide: true });
    run(['init', '-q']);
    fs.writeFileSync(path.join(tmp, '.gitignore'), pattern + '\n');
    fs.mkdirSync(path.join(tmp, dir));
    return run(['-c', `core.excludesFile=${path.join(tmp, 'none')}`, 'check-ignore', '-q', dir]).status === 0;
  } finally { try { fs.rmSync(tmp, { recursive: true, force: true }); } catch { /* 남아도 무해 */ } }
}
const ROOT_SOURCE = s => s === '.gitignore' || /(^|[\\/])info[\\/]exclude$/.test(s) || path.isAbsolute(s);
function gitignorePlan(root) {
  const hits = ignoreProbe(root, TARGETS.map(t => PROBES[t])).map((h, i) => ({ ...h, target: TARGETS[i] })).filter(h => h.ignored);
  const nested = hits.filter(h => !ROOT_SOURCE(h.source));
  const fixable = hits.filter(h => ROOT_SOURCE(h.source));
  const dirCauses = [...new Map(fixable.filter(h => patternExcludesDir(h.pattern.replace(/^\\/, ''), 'docs')).map(h => [causeOf(h), h])).values()];
  const lines = [...(dirCauses.length ? ['!docs/', 'docs/*'] : []),
    ...['prds', 'coordinations', 'designs'].flatMap(d => [`!docs/${d}/`, `!docs/${d}/**`]), `!${INDEX_REL}`];
  return { hits, nested, dirCauses, needed: hits.length > 0, lines };
}

// ── check ─────────────────────────────────────────────────────────────
function check(rootIn) {
  const root = rootOf(rootIn);
  const p = planIndex(root);
  const problems = [], unmanaged = [], add = (rel, problem) => problems.push({ path: rel, problem });
  const byKey = new Map(p.docs.map(d => [key(d.rel), d]));
  for (const d of p.docs) {
    const x = d.data;
    // [2026-09-30 실측 · Python 서비스 저장소] 옛 하네스가 만든 문서 94개가 이 폴더들에 이미 있었다 — 관리 밖 문서는 오류가 아니다.
    //   관리에 넣으려면 doc adopt. 머리를 쓰려다 깨진 문서(닫히지 않은 ---)만 문제다.
    if (!d.fm) { if (d.errors.length) add(d.rel, d.errors.join('; ')); else unmanaged.push(d.rel); continue; }
    for (const e of d.errors) add(d.rel, e);
    if (!Object.prototype.hasOwnProperty.call(KINDS, x.kind)) add(d.rel, `kind 가 잘못됐다: ${JSON.stringify(x.kind || '')} (prd | coordination | design)`);
    else if (x.kind !== d.folderKind) add(d.rel, `kind: ${x.kind} 인데 docs/${KINDS[d.folderKind]}/ 에 있다(kind 와 폴더가 다르다)`);
    if (!x.title) add(d.rel, 'title 이 비었다');
    if (!STATUSES.includes(x.status)) add(d.rel, `status 가 잘못됐다: ${JSON.stringify(x.status || '')} (${STATUSES.join(' | ')})`);
    for (const k of ['created', 'updated']) if (!validDate(x[k])) add(d.rel, `${k} 가 YYYY-MM-DD 날짜가 아니다: ${JSON.stringify(x[k] || '')}`);
    if (x.tasks !== undefined && x.tasks !== '' && !Array.isArray(x.tasks)) add(d.rel, 'tasks 는 [a, b] 목록이어야 한다');
    if (d.folderKind === 'coordination' && x.direction && !DIRECTIONS.includes(x.direction)) add(d.rel, `direction 이 잘못됐다: ${JSON.stringify(x.direction)} (outgoing | incoming)`);
    const by = refPath(d.rel, x.superseded_by), sup = refPath(d.rel, x.supersedes);
    if (x.status === 'superseded' && !by) add(d.rel, 'status 가 superseded 인데 superseded_by 가 없다');
    if (by) {
      const o = byKey.get(key(by));
      if (x.status !== 'superseded') add(d.rel, `superseded_by 가 있는데 status 가 superseded 가 아니다(${x.status || '없음'})`);
      if (!o || !o.fm) add(d.rel, `superseded_by 가 가리키는 문서가 없다: ${by}`);
      else if (key(refPath(o.rel, o.data.supersedes)) !== key(d.rel)) add(d.rel, `superseded_by → ${by} 인데 그 문서의 supersedes 가 이 문서를 가리키지 않는다(한쪽 링크)`);
    }
    if (sup) {
      const o = byKey.get(key(sup));
      if (!o || !o.fm) add(d.rel, `supersedes 가 가리키는 문서가 없다: ${sup}`);
      else if (key(refPath(o.rel, o.data.superseded_by)) !== key(d.rel)) add(d.rel, `supersedes → ${sup} 인데 그 문서의 superseded_by 가 이 문서를 가리키지 않는다(한쪽 링크)`);
    }
  }
  for (const a of p.amap.unlinked) add(a, '어느 디자인 문서도 링크하지 않은 첨부(unlinked attachment) — 디자인 문서 본문에서 상대 경로로 링크하거나 지운다');
  const stale = p.hasBlock ? p.cur !== p.next : p.docs.some(d => d.fm);
  if (stale) add(INDEX_REL, `색인이 낡았다(index is stale — ${p.hasBlock ? '관리 블록이 문서와 다르다' : '관리 블록이 없다'}) — node harness/cli.js doc index`);
  return { ok: problems.length === 0, documents: p.docs.length - unmanaged.length, unmanaged, attachments: p.attachments.length, problems, tracking: tracking(root), history_dir: historyRoot(root) };
}
function formatCheck(r) {
  const L = [];
  for (const x of r.problems) L.push(`✗ ${x.path}: ${x.problem}`);
  const git = r.tracking.filter(t => !t.ignored), local = r.tracking.filter(t => t.ignored);
  if (git.length) L.push(`보관: git 추적 — ${git.map(t => t.target).join(' · ')}`);
  if (local.length) L.push(`보관: 로컬 전용(git 이 무시한다 — 변경 이력만 남는다) — ${local.map(t => `${t.target} (${causeOf(t)})`).join(' · ')}`);
  L.push(`이력(docs-history): ${r.history_dir} — doc new · status · restore · accept 연결이 바꾸기 전 판을 남긴다`);
  if ((r.unmanaged || []).length) L.push(`관리 밖 문서 ${r.unmanaged.length}개(front matter 없음 — 오류 아님 · 관리에 넣으려면 node harness/cli.js doc adopt <경로>): ${r.unmanaged.slice(0, 5).join(', ')}${r.unmanaged.length > 5 ? ` 외 ${r.unmanaged.length - 5}개` : ''}`);
  L.push(`doc check: 관리 문서 ${r.documents} · 첨부 ${r.attachments} · ${r.ok ? '문제 없음' : `문제 ${r.problems.length}`}`);
  return L.join('\n');
}

// ── adopt: 기존 문서를 관리에 넣는다(요청할 때만) ──────────────────────
//   종류는 폴더에서 · 제목은 첫 `# ` 제목(없으면 파일 이름) · created 는 파일 수정일 · 본문은 그대로 · 바꾸기 전 판을 이력에 남긴다.
function adopt(o) {
  const root = rootOf(o.root), rel = docRel(root, o.path);
  const kind = Object.keys(KINDS).find(k => rel.startsWith(`docs/${KINDS[k]}/`));
  if (!kind || !/\.md$/i.test(rel)) throw usage(`doc adopt: ${rel} is not a .md file under docs/prds · docs/coordinations · docs/designs`);
  const d = readDoc(root, rel);
  if (!d.exists) throw usage(`doc adopt: no such file ${rel}`);
  if (d.fm) throw usage(`doc adopt: ${rel} already has front matter (use doc status)`);
  const status = o.status || 'active';
  if (!STATUSES.includes(status) || status === 'superseded') throw usage(`doc adopt --status must be draft | active | done`);
  const h1 = /^#[ \t]+(.+?)[ \t]*#*[ \t]*$/m.exec(d.body || '');
  const title = (h1 ? h1[1] : path.posix.basename(rel, path.posix.extname(rel))).replace(/\s+/g, ' ').trim();
  let created = today(); try { created = today(fs.statSync(d.abs).mtime); } catch { /* 오늘 */ }
  const q = v => (/^[\w가-힣 .·-]*$/.test(v) ? v : JSON.stringify(v));
  const lines = [`kind: ${kind}`, `title: ${q(title)}`, `status: ${status}`, `created: ${created}`, `updated: ${today()}`, 'tasks: []'];
  if (kind === 'coordination') { lines.push(`with: ${q(String(o.with || ''))}`, `direction: ${o.direction === 'incoming' ? 'incoming' : 'outgoing'}`); }
  const eol = d.eol || '\n';
  snapshot(root, rel);
  writeAtomic(d.abs, (d.bom ? '\ufeff' : '') + ['---', ...lines, '---'].join(eol) + eol + d.body);
  const idx = writeIndex(root);
  return { path: rel, kind, title, status, created, index_changed: idx.changed };
}

// ── 작업 연결 ──────────────────────────────────────────────────────────
// go --doc: 경로를 확인하고 저장소 상대 posix 로. 없는 파일 · 저장소 밖은 USAGE(작업을 만들기 전에).
function resolveDocs(root, list0) {
  const out = [];
  for (const p of list0 || []) {
    const abs = path.isAbsolute(p) ? path.resolve(p) : path.resolve(root, p);
    let st = null; try { st = fs.statSync(abs); } catch { /* 없음 */ }
    if (!st || !st.isFile()) throw usage(`--doc ${p}: no such file (${abs})`);
    const R = require('../hooks/_common').real;   // 실경로로 비교(심볼릭 링크 · 짧은 이름)
    const rel = path.relative(R(root), R(abs)).split(path.sep).join('/');
    if (!rel || rel.startsWith('..') || path.isAbsolute(rel)) throw usage(`--doc ${p}: outside the repository ${root}`);
    if (!out.some(x => key(x) === key(rel))) out.push(rel);
  }
  return out;
}
// accept 뒤: 연결된 관리 문서의 tasks 에 id 를 더하고 updated 를 올린 뒤 색인. 문서가 git 이 추적하는 파일이고
//   메인 체크아웃이 대상 브랜치면 그 문서(와 docs/README.md)만 경로로 커밋한다(`git commit -- <files>` — add -A 없음).
function linkTask(rootIn, task, o) {
  const root = rootOf(rootIn), id = task.id, opt = o || {};
  const updated = [], skipped = [], lines = [];
  for (const rel of task.docs || []) {
    const d = readDoc(root, rel);
    if (!MANAGED_RE.test(rel)) { skipped.push(`${rel} (not a managed document — left as is)`); continue; }
    if (!d.exists) { skipped.push(`${rel} (missing)`); continue; }
    if (!d.fm) { skipped.push(`${rel} (no front matter)`); continue; }
    const tasks = listOf(d.data.tasks);
    if (tasks.includes(id)) continue;
    setField(d, 'tasks', [...tasks, id]); setField(d, 'updated', today());
    saveDoc(root, d);
    updated.push(rel);
  }
  let commit = null, committed = [];
  if (updated.length) {
    writeIndex(root);
    const tracked = updated.filter(r => isTracked(root, r)), local = updated.filter(r => !tracked.includes(r));
    lines.push(`docs linked to ${id}: ${updated.join(', ')}`);
    if (tracked.length) {
      if (opt.target && G.currentBranch(root) !== opt.target) lines.push(`  not committed — ${root} is not on ${opt.target}; commit them yourself: ${tracked.join(', ')}`);
      else {
        const files = [...tracked];
        if (isTracked(root, INDEX_REL)) files.push(INDEX_REL);
        else if (fs.existsSync(absOf(root, INDEX_REL)) && !ignoreProbe(root, [INDEX_REL])[0].ignored && G.git(root, ['add', '--', INDEX_REL], { allowFail: true, retryLock: true }).ok) files.push(INDEX_REL);
        const r = G.git(root, [...G.identityArgs(root), 'commit', '-q', '--no-verify', '-m', `docs: link ${id}`, '--', ...files], { allowFail: true, retryLock: true });
        if (r.ok) { commit = G.headSha(root); committed = files; lines.push(`  committed ${commit.slice(0, 10)} "docs: link ${id}" (${files.join(', ')})`); }
        else lines.push(`  warning: could not commit ${files.join(', ')}: ${r.err.trim().slice(0, 200)} — the files are updated; commit them yourself`);
      }
    }
    if (local.length) lines.push(`  not in git (ignored or untracked — local only; the previous versions are in ${historyRoot(root)}): ${local.join(', ')}`);
  }
  if (skipped.length) lines.push(`docs not linked: ${skipped.join(', ')}`);
  return { updated, skipped, commit, committed, lines };
}

module.exports = {
  KINDS, STATUSES, DIRECTIONS, BEGIN, END, INDEX_REL, TARGETS, PROBES,
  today, stamp, validDate, normKind, slugify, docRel, parseDoc, serialize, readDoc, newDoc, setStatus, adopt, list, formatList,
  writeIndex, planIndex, check, formatCheck, history, restore, snapshot, historyRoot, historyDir,
  ignoreProbe, isTracked, tracking, trackingOf, gitignorePlan, patternExcludesDir, causeOf, resolveDocs, linkTask,
};
