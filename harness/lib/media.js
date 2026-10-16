'use strict';
// 첨부 — 멀티모달 입력(이미지 · 영상 · 음성 · 문서)을 무인 작업자가 읽을 수 있는 모양으로 준비한다.
//   [2026-10-08 사용자 지시] 대화창에 붙인 이미지가 작업자에게 전달되지 않았다(스킬은 요청을 텍스트로만 넘겼다) · 영상 · 음성도 받아야 한다.
//   모델이 직접 읽는 것: 이미지(png · jpg · gif · webp) · PDF · 텍스트. 나머지는 하네스가 바꾼다:
//     영상 → 고르게 뽑은 장면 이미지(최대 maxFrames 장, 시각 표시) + 소리가 있으면 전사
//     음성 → 전사(전사기: 프로젝트 블록 transcribe_command · 환경 HARNESS_TRANSCRIBE · 없으면 PATH 의 whisper)
//     그 밖의 이미지(bmp · tiff …) → png
//   바꾸는 도구(ffmpeg · 전사기)가 없으면 원본만 붙이고 무엇을 못 했는지 적는다 — 작업자와 보고가 그 사실을 본다.
//   첨부는 <git-common-dir>/harness/tasks/<id>/attachments/ 에 둔다 — worktree 밖이라 결과 브랜치에 커밋되지 않는다.
const fs = require('node:fs'), path = require('node:path'), crypto = require('node:crypto');
const { spawnSync } = require('node:child_process');

const EXT = {
  image: ['png', 'jpg', 'jpeg', 'gif', 'webp'],
  image_convert: ['bmp', 'tif', 'tiff', 'ico', 'heic', 'avif'],
  pdf: ['pdf'],
  video: ['mp4', 'mov', 'avi', 'mkv', 'webm', 'wmv', 'm4v', 'flv', 'mpg', 'mpeg', '3gp'],
  audio: ['mp3', 'wav', 'm4a', 'ogg', 'oga', 'flac', 'aac', 'wma', 'opus', 'amr'],
  text: ['txt', 'md', 'json', 'csv', 'tsv', 'log', 'xml', 'yaml', 'yml', 'html', 'htm', 'svg', 'ini', 'toml', 'sql'],
  office: ['docx', 'xlsx', 'pptx', 'doc', 'xls', 'ppt', 'hwp', 'hwpx'],
};
const MAX_BYTES = 1024 * 1024 * 1024;   // 1 GB — 그보다 큰 것은 경로만 알려 주는 편이 낫다
function kindOf(file) {
  const ext = path.extname(String(file)).slice(1).toLowerCase();
  for (const [k, list] of Object.entries(EXT)) if (list.includes(ext)) return k === 'image_convert' ? 'image' : k;
  return 'file';
}

// 프로그램 찾기 — 환경 변수(HARNESS_FFMPEG · HARNESS_FFPROBE)가 먼저, 그다음 PATH.
function tool(name, env) {
  const e = (env || process.env)[`HARNESS_${name.toUpperCase()}`];
  for (const cand of [e, name].filter(Boolean)) {
    try { const r = spawnSync(cand, ['-version'], { encoding: 'utf8', windowsHide: true, timeout: 15000 }); if (r.status === 0) return cand; } catch { /* 없다 */ }
  }
  return null;
}
const run = (exe, args, timeoutMs) => spawnSync(exe, args, { encoding: 'utf8', windowsHide: true, timeout: timeoutMs || 300000, maxBuffer: 64 * 1024 * 1024 });
const sha1 = f => { try { return crypto.createHash('sha1').update(fs.readFileSync(f)).digest('hex'); } catch { return null; } };
const safeName = (n, used) => {
  let base = path.basename(String(n)).replace(/[<>:"|?*\x00-\x1f]/g, '_') || 'attachment';
  let out = base, i = 2;
  while (used.has(out.toLowerCase())) { const e = path.extname(base); out = `${path.basename(base, e)}-${i++}${e}`; }
  used.add(out.toLowerCase());
  return out;
};
const stamp = s => { const t = Math.max(0, Math.round(s)); return `${String(Math.floor(t / 60)).padStart(2, '0')}m${String(t % 60).padStart(2, '0')}s`; };

// 전사기 명령 — 템플릿 {in} {outdir}. 우선순위: o.transcribe(프로젝트 블록) > 환경 HARNESS_TRANSCRIBE > PATH 의 whisper(openai-whisper CLI).
function transcriber(o) {
  const t = (o && o.transcribe) || process.env.HARNESS_TRANSCRIBE;
  if (t) return { template: String(t), source: o && o.transcribe ? 'transcribe_command' : 'HARNESS_TRANSCRIBE' };
  try { const r = spawnSync('whisper', ['--help'], { encoding: 'utf8', windowsHide: true, timeout: 20000 }); if (r.status === 0) return { template: 'whisper "{in}" --model small --output_format txt --output_dir "{outdir}"', source: 'whisper' }; } catch { /* 없다 */ }
  // [2026-10-13] python 에 faster-whisper 가 있으면 하네스의 전사 스크립트를 쓴다(오프라인 · 설정 없이).
  for (const py of ['python', 'py', 'python3']) {
    try {
      const r = spawnSync(py, ['-c', 'import faster_whisper'], { windowsHide: true, timeout: 60000 });
      if (r.status === 0) return { template: `"${py}" "${path.join(__dirname, 'transcribe_fw.py')}" "{in}" "{outdir}"`, source: 'faster-whisper' };
    } catch { /* 그 이름의 python 이 없다 */ }
  }
  return null;
}
function transcribe(file, outDir, o) {
  const t = transcriber(o);
  if (!t) return { error: '전사기가 없다 — 프로젝트 블록에 transcribe_command 를 두거나(예: "whisper \\"{in}\\" --model small --output_format txt --output_dir \\"{outdir}\\"") 전사기를 설치하면 음성을 글로 읽는다' };
  fs.mkdirSync(outDir, { recursive: true });
  const cmd = t.template.replace(/\{in\}/g, file).replace(/\{outdir\}/g, outDir);
  const r = spawnSync(cmd, { shell: true, encoding: 'utf8', windowsHide: true, timeout: (o && o.transcribeTimeoutMs) || 30 * 60000, maxBuffer: 64 * 1024 * 1024 });
  const txt = (() => { try { return fs.readdirSync(outDir).filter(f => /\.txt$/i.test(f)).map(f => path.join(outDir, f))[0] || null; } catch { return null; } })();
  if (r.status !== 0 || !txt) return { error: `전사 실패(${t.source}, exit ${r.status}): ${String(r.stderr || r.error || '').trim().slice(0, 200)}` };
  return { transcript: txt };
}

function videoInfo(ffprobe, file) {
  const d = run(ffprobe, ['-v', 'error', '-show_entries', 'format=duration', '-of', 'default=nw=1:nk=1', file], 60000);
  const a = run(ffprobe, ['-v', 'error', '-select_streams', 'a', '-show_entries', 'stream=index', '-of', 'csv=p=0', file], 60000);
  return { duration: Number(String(d.stdout).trim()) || 0, hasAudio: !!String(a.stdout).trim() };
}

// files: 원본 경로 목록 → dir 에 준비. o = { maxFrames, transcribe, env }
function prepare(files, dir, o) {
  const opt = o || {};
  const maxFrames = Math.max(1, Math.min(48, Number(opt.maxFrames) || 12));
  const ffmpeg = tool('ffmpeg', opt.env), ffprobe = tool('ffprobe', opt.env);
  fs.mkdirSync(dir, { recursive: true });
  const used = new Set(), items = [];
  for (const src of files || []) {
    const name = safeName(src, used), kind = kindOf(src);
    const it = { name, src: path.resolve(src), kind, file: path.join(dir, name), sha1: null, frames: [], transcript: null, notes: [] };
    items.push(it);
    fs.copyFileSync(src, it.file);
    it.sha1 = sha1(it.file);
    const work = path.join(dir, `${name}.d`);
    if (kind === 'image' && !EXT.image.includes(path.extname(name).slice(1).toLowerCase())) {
      if (!ffmpeg) { it.notes.push('이 형식은 모델이 바로 열지 못한다 — ffmpeg 가 없어 png 로 바꾸지 못했다'); continue; }
      fs.mkdirSync(work, { recursive: true });
      const png = path.join(work, `${path.basename(name, path.extname(name))}.png`);
      const r = run(ffmpeg, ['-v', 'error', '-y', '-i', it.file, '-frames:v', '1', png]);
      if (r.status === 0 && fs.existsSync(png)) it.frames.push({ file: png, at: null }); else it.notes.push(`png 로 바꾸지 못했다: ${String(r.stderr).trim().slice(0, 160)}`);
    } else if (kind === 'video') {
      if (!ffmpeg || !ffprobe) { it.notes.push('ffmpeg 가 없어 영상을 장면 이미지 · 전사로 바꾸지 못했다 — 모델은 영상 파일을 직접 보지 못한다'); continue; }
      fs.mkdirSync(work, { recursive: true });
      const info = videoInfo(ffprobe, it.file);
      it.duration_s = Math.round(info.duration * 10) / 10;
      const n = info.duration > 0 ? Math.min(maxFrames, Math.max(1, Math.ceil(info.duration / 5))) : 1;
      for (let i = 0; i < n; i++) {
        const at = info.duration > 0 ? (info.duration * (i + 0.5)) / n : 0;
        const out = path.join(work, `frame-${String(i + 1).padStart(2, '0')}-${stamp(at)}.png`);
        const r = run(ffmpeg, ['-v', 'error', '-y', '-ss', at.toFixed(2), '-i', it.file, '-frames:v', '1', '-vf', "scale='min(1280,iw)':-2", out]);
        if (r.status === 0 && fs.existsSync(out)) it.frames.push({ file: out, at: Math.round(at * 10) / 10 });
      }
      if (!it.frames.length) it.notes.push('장면 이미지를 뽑지 못했다');
      if (info.hasAudio) {
        const wav = path.join(work, 'audio.wav');
        const r = run(ffmpeg, ['-v', 'error', '-y', '-i', it.file, '-vn', '-ac', '1', '-ar', '16000', wav], 30 * 60000);
        if (r.status === 0) { const t = transcribe(wav, path.join(work, 'transcript'), opt); if (t.transcript) it.transcript = t.transcript; else it.notes.push(`소리: ${t.error}`); }
        else it.notes.push('소리를 뽑지 못했다');
      }
    } else if (kind === 'audio') {
      const t = transcribe(it.file, path.join(work, 'transcript'), opt);
      if (t.transcript) it.transcript = t.transcript; else it.notes.push(t.error);
    } else if (kind === 'office') {
      it.notes.push('오피스 문서 — 모델이 바로 열지 못한다. 필요하면 python(python-docx · openpyxl 등)이나 문서 스킬로 텍스트를 뽑아 읽는다');
    } else if (kind === 'file') {
      it.notes.push('알 수 없는 형식 — 경로만 알린다');
    }
  }
  fs.writeFileSync(path.join(dir, 'INDEX.md'), indexText(items));
  return { dir, items, tools: { ffmpeg: !!ffmpeg, ffprobe: !!ffprobe, transcriber: (transcriber(opt) || {}).source || null } };
}

function indexText(items) {
  const L = ['# 첨부 (사용자가 함께 준 파일)', ''];
  for (const it of items) {
    L.push(`## ${it.name} — ${it.kind}`, `- 파일: ${it.file}`);
    if (it.duration_s != null) L.push(`- 길이: ${it.duration_s}초`);
    if (it.frames.length) L.push(`- ${it.kind === 'video' ? '장면 이미지' : '변환 이미지'}:`, ...it.frames.map(f => `  - ${f.file}${f.at != null ? ` (${f.at}초)` : ''}`));
    if (it.transcript) L.push(`- 전사: ${it.transcript}`);
    for (const n of it.notes) L.push(`- 참고: ${n}`);
    L.push('');
  }
  return L.join('\n');
}

// 첨부 경로 검증 — 없거나 폴더거나 너무 크면 이유(문자열), 괜찮으면 null.
function checkFile(f) {
  let st; try { st = fs.statSync(f); } catch { return `attachment not found: ${f}`; }
  if (!st.isFile()) return `attachment is not a file: ${f}`;
  if (st.size > MAX_BYTES) return `attachment is larger than 1 GB: ${f}`;
  return null;
}
// 모델이 이미지로 볼 파일들(원본 이미지 · 변환 이미지 · 장면 이미지) — Codex 의 -i 로도 넘긴다.
function imagesOf(items) {
  const out = [];
  for (const it of items || []) {
    if (it.kind === 'image' && EXT.image.includes(path.extname(it.name).slice(1).toLowerCase())) out.push(it.file);
    for (const f of it.frames || []) out.push(f.file);
  }
  return out;
}

module.exports = { EXT, kindOf, prepare, checkFile, imagesOf, transcriber, indexText, tool };
