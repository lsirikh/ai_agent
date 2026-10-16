#!/usr/bin/env node
'use strict';
// hooks/session-end.js — SessionEnd(Claude · Codex 둘 다 이 이벤트가 있다): 안전망.
//   이 세션이 기록한 파일 중 아직 미커밋인 것을 그 파일만 자동 커밋한다: `wip(session <sid8>): auto-commit at session end`.
//   다른 세션·사람의 변경은 절대 커밋하지 않는다. 비밀 파일은 커밋하지 않고 세션 파일에 남긴다.
//   남은 것이 없으면 세션 파일을 지운다(주인 없는 변경 분류는 status 가 한다). 남았으면 ended_at 을 적고 둔다.
//   시간 예산이 짧다(Claude 기본 1.5초 — 설치기가 timeout 을 늘린다 · Codex 최대 3초). 커밋 한 번이면 충분하다.
const C = require('./_common');

function main() {
  let input = null;
  try {
    const r = C.readStdinJson();
    if (!r.input) { if (r.error !== 'empty stdin') C.logError('session-end', r.error); return; }
    input = r.input;
    const sid = input.session_id;
    if (!sid) return;
    const cwd = typeof input.cwd === 'string' && input.cwd ? input.cwd : process.cwd();
    const info = C.repoInfo(cwd);
    if (!info || C.isHarnessWorktree(info.root)) return;
    const sess = C.loadSession(info.common, sid);
    if (!sess || !sess.files || !sess.files.length) return;
    const runtime = C.detectRuntime(input);
    const { mine, secrets } = C.uncommittedOf(info.root, sess.files);
    const now = new Date().toISOString();
    let res = { ok: true, sha: null };
    if (mine.length) {
      res = C.commitFiles(info.root, mine, `wip(session ${C.sid8(sid)}): auto-commit at session end`);
      if (!res.ok) C.logError('session-end', new Error(res.error), cwd);
    }
    C.updateSession(info.common, sid, runtime, s => {
      if (res.ok && !secrets.length) return null;           // 깨끗하게 끝났다 — 기록을 지운다
      s.ended_at = now;
      s.end_reason = input.reason || null;
      if (res.sha) s.last_commit = { sha: res.sha, files: mine, at: now, by: 'session-end' };
      if (!res.ok) s.commit_error = { error: res.error, files: mine, at: now };
      if (secrets.length) s.secrets_left = secrets;
      return s;
    });
  } catch (e) {
    C.logError('session-end', e, input && input.cwd);
  }
}

if (require.main === module) { main(); process.exitCode = 0; }
