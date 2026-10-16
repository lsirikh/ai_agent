#!/usr/bin/env node
'use strict';
// hooks/stop.js — Stop: 이 세션이 고친 파일이 커밋되지 않은 채 끝나지 않게 한다(설계 §0.4 · §7).
//   대상 = 세션 파일(track.js 가 기록)의 경로 ∩ `git status --porcelain -z` 의 미커밋 경로. 다른 세션·사람의 변경은 보지 않는다.
//   (셸로 고친 파일은 기록되지 않는다 — 스냅샷 대조는 하지 않는다: 같은 체크아웃의 다른 세션·편집기 변경과 구별할 수 없다.)
//
//   Claude: 남은 파일이 있으면 {"decision":"block","reason":…} — 턴을 이어 가며 모델이 그 파일만 커밋한다.
//           한 번만 막는다. 이어 간 턴 뒤에도 남아 있으면(권한 프롬프트에 막혔거나 모델이 못 했으면) 훅이 직접 그 파일만 커밋하고 통과시킨다.
//           [2026-09-29 실측] -p 세션에서 모델의 `git commit` 이 승인 대기에 걸려 커밋하지 못했다 — 막기만 하면 커밋 없이 끝난다.
//   Codex : 샌드박스가 .git 쓰기를 막아 모델이 커밋할 수 없다 → 막지 않고 훅이 직접 그 파일만 커밋한다.
//   비밀 파일(.env* · *.pem · *.key · id_rsa*)은 절대 커밋하지 않는다 — Claude 에는 이유에 따로 적고, Codex 에서는 세션 파일에 남긴다.
const C = require('./_common');

const MAX_BLOCKS = 1;

function firstLine(text) {
  const line = String(text || '').split(/\r?\n/).map(s => s.trim()).find(Boolean) || '';
  const clean = line.replace(/^[#>*\-\s`]+/, '').replace(/\s+/g, ' ').trim();
  return clean.length > 72 ? clean.slice(0, 69) + '...' : clean;
}

// [2026-09-29 실측] 마지막 말을 메시지로 쓰면 "커밋이 승인 대기로 막혀…" 같은 불평이 이력에 남았다 — 파일 목록으로 쓴다.
function filesSummary(files) {
  const head = files.slice(0, 3).join(', ');
  return `update ${head}${files.length > 3 ? ` (+${files.length - 3} more)` : ''}`;
}

function blockReason(mine, secrets) {
  let r = `${C.listForReason(mine)} — 이 세션이 고친 파일이 커밋되지 않았습니다. 이 파일들만 스테이징해 의미 있는 메시지로 커밋하고 끝내세요(다른 변경은 건드리지 마세요).`;
  r += ` 예: \`git add -- <파일들>\` 후 \`git commit -m "<무엇을 왜>" -- <파일들>\`.`;
  if (secrets.length) r += ` 비밀 파일로 보이는 ${C.listForReason(secrets, 10)} 은(는) 커밋하지 마세요.`;
  return r;
}

function main() {
  let input = null;
  try {
    const r = C.readStdinJson();
    if (!r.input) { if (r.error !== 'empty stdin') C.logError('stop', r.error); return; }
    input = r.input;
    const sid = input.session_id;
    if (!sid) return;
    const cwd = typeof input.cwd === 'string' && input.cwd ? input.cwd : process.cwd();
    const info = C.repoInfo(cwd);
    if (!info || C.isHarnessWorktree(info.root)) return;
    const sess = C.loadSession(info.common, sid);
    if (!sess || !sess.files || !sess.files.length) return;
    const runtime = C.detectRuntime(input);
    // [2026-09-30 실측 · 이 저장소에서 v5 를 쓰다가] 백그라운드 서브에이전트가 아직 파일을 고치는 중인데 Stop 이 발화해
    //   "그 파일들을 커밋하라" 고 막았다 — 그대로 커밋하면 반쯤 된 작업이 들어가고, 한 번 더 멈추면 훅이 대신 커밋한다.
    //   백그라운드 작업이 남아 있으면 막지도 커밋하지도 않는다(그 작업이 끝난 뒤의 Stop 이 처리한다).
    if (Array.isArray(input.background_tasks) && input.background_tasks.some(t => !t || !/^(completed|done|failed|killed|stopped)$/i.test(String(t.status || '')))) return;
    const { mine, secrets } = C.uncommittedOf(info.root, sess.files);
    const now = new Date().toISOString();

    if (runtime === 'codex') {
      if (!mine.length) {
        if (secrets.length) C.updateSession(info.common, sid, runtime, s => { s.secrets_left = secrets; return s; });
        return;
      }
      const msg = `wip(codex ${C.sid8(sid)}): ${filesSummary(mine)}`;
      const res = C.commitFiles(info.root, mine, msg);
      C.updateSession(info.common, sid, runtime, s => {
        if (res.ok) { s.last_commit = { sha: res.sha, files: mine, at: now, by: 'stop' }; delete s.commit_error; }
        else s.commit_error = { error: res.error, files: mine, at: now };
        if (secrets.length) s.secrets_left = secrets; else delete s.secrets_left;
        return s;
      });
      if (!res.ok) C.logError('stop', new Error(res.error), cwd);
      return;
    }

    // Claude
    if (!mine.length) {
      if (sess.stop_blocks) C.updateSession(info.common, sid, runtime, s => { s.stop_blocks = 0; return s; });
      return;
    }
    const prior = input.stop_hook_active === true ? (Number(sess.stop_blocks) || 0) : 0;
    if (prior >= MAX_BLOCKS) {
      const res = C.commitFiles(info.root, mine, `wip(session ${C.sid8(sid)}): ${filesSummary(mine)}`);
      C.updateSession(info.common, sid, runtime, s => {
        s.stop_blocks = 0;
        if (res.ok) { s.last_commit = { sha: res.sha, files: mine, at: now, by: 'stop-fallback' }; delete s.commit_error; }
        else { s.stop_gave_up = { at: now, files: mine }; s.commit_error = { error: res.error, files: mine, at: now }; }
        return s;
      });
      if (!res.ok) C.logError('stop', new Error(res.error), cwd);
      return;
    }
    C.updateSession(info.common, sid, runtime, s => { s.stop_blocks = prior + 1; return s; });
    process.stdout.write(JSON.stringify({ decision: 'block', reason: blockReason(mine, secrets) }) + '\n');
  } catch (e) {
    C.logError('stop', e, input && input.cwd);
  }
}

if (require.main === module) { main(); process.exitCode = 0; }
module.exports = { firstLine, blockReason, filesSummary };
