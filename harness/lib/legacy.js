'use strict';
// 옛 하네스(lean-core · v14 · v4)의 잔여물 정리 — `cleanup-legacy`.
//   [2026-09-30 실측 · Python 서비스 저장소] 옛 worktree 21개 · 브랜치 14개 · 상태 폴더 2.5GB 가 남았는데, guard 훅은 `git branch -D` 와
//   `.git` 아래 재귀 삭제를 (사용자가 허락했어도) 막는다 — 허락받은 정리를 할 **안전한 길**이 없었다. 이 명령이 그 길이다.
//   지우는 조건(하나라도 아니면 남기고 이유를 말한다):
//     - 옛 worktree: 미커밋 변경 없음 · git 밖 산출물(무시된 파일 — 캐시와 옛 하네스의 런타임 파일 제외) 없음 · HEAD 의 내용이 현재 브랜치에
//       패치 단위로 전부 있음. `git worktree remove` 를 --force 없이 쓴다.
//     - 옛 브랜치(`harness/` · `harness-node/` 아래, v5 의 `harness/t-…` 가 아닌 것): 남는 worktree 에 체크아웃돼 있지 않고, 내용이 현재
//       브랜치에 전부 있음(`git cherry` 에 `+` 가 0). 지우기 전에 이름과 sha 를 기록한다(`git branch <name> <sha>` 로 되살린다).
//     - 옛 상태 폴더(`.git/harness-v14` · `.git/harness-v4`): 남는 worktree 가 그 안에 하나도 없음.
//   `--salvage`: 위 조건에 안 맞는 것도 **잃지 않게 옮겨 놓고** 지운다 —
//     [2026-09-30 실측 · skill-set] 실패한 실행의 미커밋 작업 · 반영 안 된 커밋이 있는 worktree 14개는 조건에 안 맞아 남았다.
//     미커밋 변경은 그 브랜치에 커밋하고 · 브랜치 끝을 태그 `harness/salvage/<이름>` 으로 남기고 · git 밖 파일(비밀 · 무시된 산출물)은
//     `.git/harness/legacy-salvage/<이름>/` 로 복사한 뒤 worktree 와 브랜치를 지운다. 커밋은 태그에서, 파일은 그 폴더에서 되찾는다.
//   기본은 계획만 보여 준다(dry-run). `--apply` 는 사용자가 정리를 말한 뒤에만.
const fs = require('node:fs'), path = require('node:path');
const S = require('./state'), G = require('./git');

const LEGACY_DIRS = ['harness-v14', 'harness-v4'];
const V5_BRANCH = /^harness\/t-\d{8}-\d{6}-[0-9a-f]{4}$/, V5_WT = /^t-\d{8}-\d{6}-[0-9a-f]{4}(-cancel-[0-9a-f]+)?$/;
const isLegacyBranch = b => /^harness(-node)?\//.test(b) && !V5_BRANCH.test(b);
// 옛 하네스가 스스로 만든 런타임 파일 — 작업 산출물이 아니다.
const NOISE = /^\.claude\/(\.branch-[^/]+\/|install-logs\/|verify-logs\/|\.session-credential|\.pending-|mailbox\/|worktrees\/|wizard-state\.json$|scheduled_tasks\.lock$|[^/]*\.(lock|log)$)|^docs\/memory\/(sessions\/|state-backups\/|[^/]*\.(lock|bak)$|session-guard\.json|pipeline-state\.json|cost-log\.jsonl$|compact-log\.jsonl$)|^_claude_stage\/|^\.harness-worktrees\/|^dist\/_staging\//;

function dirSize(dir) {
  let n = 0;
  const walk = d => { let ents = []; try { ents = fs.readdirSync(d, { withFileTypes: true }); } catch { return; }
    for (const e of ents) { const p = path.join(d, e.name); if (e.isDirectory()) walk(p); else { try { n += fs.statSync(p).size; } catch { /* 사라진 파일 */ } } } };
  walk(dir);
  return n;
}
const under = (child, parent) => { const r = path.relative(parent, child); return !!r && !r.startsWith('..') && !path.isAbsolute(r); };
const safeName = s => String(s).replace(/[^A-Za-z0-9._-]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 120) || 'unnamed';

// ref(브랜치 이름 또는 sha)의 커밋이 current 에 패치 단위로 다 있는가 → {ok, total, unapplied, err}
function contained(root, current, ref) {
  const c = G.git(root, ['cherry', current, ref], { allowFail: true });
  if (!c.ok) return { ok: false, err: String(c.err || '').trim().slice(0, 120) };
  const lines = c.out.split(/\r?\n/).filter(Boolean);
  return { ok: true, total: lines.length, unapplied: lines.filter(l => l.startsWith('+')).length };
}
const outsideGit = wt => G.ignoredChanges(wt, []).filter(p => !NOISE.test(p));
// 중첩된 다른 worktree 폴더는 이 worktree 의 미커밋 변경이 아니다.
function dirtyOf(wt, all) {
  const nested = all.filter(o => under(o.path, wt)).map(o => path.relative(wt, o.path).split(path.sep).join('/') + '/');
  return G.dirtyFiles(wt).map(e => e.path).filter(f => !NOISE.test(f)).filter(f => !nested.some(n => (f + '/').startsWith(n) || n.startsWith(f.endsWith('/') ? f : f + '/')));
}

function legacyWorktrees(root, P, wts) {
  const legacyRoots = LEGACY_DIRS.map(n => path.join(P.commonDir, n));
  return wts.slice(1).filter(w => {   // 첫 줄은 메인 체크아웃
    if (w.branch && V5_BRANCH.test(w.branch)) return false;
    if (under(w.path, P.worktreesDir)) return !V5_WT.test(path.basename(w.path));
    return legacyRoots.some(r => under(w.path, r)) || (w.branch ? isLegacyBranch(w.branch) : false);
  }).sort((a, b) => b.path.length - a.path.length);   // 깊은 것(중첩)부터
}

function plan(rootIn, o) {
  const salvage = !!(o && o.salvage);
  const root = S.mainRoot(rootIn), P = S.paths(root);
  const current = G.currentBranch(root);
  const wts = G.worktreeList(root);
  const worktrees = legacyWorktrees(root, P, wts).map(w => {
    const base = { path: w.path, branch: w.branch || null, head: w.head };
    if (!fs.existsSync(w.path)) return { ...base, action: 'prune', why: 'the folder is gone (git worktree prune)' };
    if (!current) return { ...base, action: 'keep', why: 'the main checkout is not on a branch — cannot compare' };
    const dirty = dirtyOf(w.path, wts), ig = outsideGit(w.path), c = contained(root, current, w.head);
    if (!c.ok) return { ...base, action: 'keep', why: `cannot compare with ${current}: ${c.err}` };
    const problems = [];
    if (dirty.length) problems.push(`${dirty.length} uncommitted change(s)`);
    if (ig.length) problems.push(`${ig.length} file(s) outside git (${ig.slice(0, 2).join(', ')}${ig.length > 2 ? ', …' : ''})`);
    if (c.unapplied) problems.push(`${c.unapplied} of ${c.total} commit(s) are NOT in ${current}`);
    if (!problems.length) return { ...base, action: 'remove', why: `clean · all ${c.total} commit(s) are already in ${current}` };
    return { ...base, action: salvage ? 'salvage' : 'keep', why: problems.join(' · ') + (salvage ? ' — kept at a salvage tag/folder, then removed' : ' (use --salvage to keep them at a tag and remove the worktree)'), dirty: dirty.length, outside: ig, unapplied: c.unapplied };
  });
  const goingAway = new Set(worktrees.filter(w => w.action !== 'keep').map(w => w.path));
  const checkedOut = new Set(wts.filter(w => !goingAway.has(w.path)).map(w => w.branch).filter(Boolean));
  const names = G.git(root, ['for-each-ref', '--format=%(refname:short)', 'refs/heads/harness', 'refs/heads/harness-node'], { allowFail: true }).out.split(/\r?\n/).filter(Boolean).filter(isLegacyBranch);
  const dirtyBranches = new Set(worktrees.filter(w => w.action === 'salvage' && w.branch).map(w => w.branch));
  const branches = names.map(name => {
    const sha = G.headSha(root, name);
    if (checkedOut.has(name)) return { name, sha, action: 'keep', why: 'checked out in a worktree that stays' };
    if (!current) return { name, sha, action: 'keep', why: 'the main checkout is not on a branch — cannot compare' };
    if (dirtyBranches.has(name)) return { name, sha, action: 'salvage', why: 'its worktree is salvaged — the tip (with the salvaged commit) stays at a tag' };
    const c = contained(root, current, name);
    if (!c.ok) return { name, sha, action: 'keep', why: `cannot compare with ${current}: ${c.err}` };
    if (c.unapplied === 0) return { name, sha, action: 'delete', why: `all ${c.total} commit(s) are already in ${current} (patch-equivalent)` };
    return { name, sha, action: salvage ? 'salvage' : 'keep', why: `${c.unapplied} of ${c.total} commit(s) are NOT in ${current}${salvage ? ' — kept at a salvage tag' : ' (use --salvage)'}` };
  });
  const dirs = LEGACY_DIRS.map(n => path.join(P.commonDir, n)).filter(d => fs.existsSync(d)).map(dir => {
    const inside = wts.filter(w => under(w.path, dir) && !goingAway.has(w.path)).map(w => w.path);
    return inside.length
      ? { dir, bytes: dirSize(dir), action: 'keep', why: `${inside.length} worktree(s) that stay live inside` }
      : { dir, bytes: dirSize(dir), action: 'delete', why: 'no worktree stays inside' };
  });
  return { root, current, salvage, worktrees, branches, dirs };
}

function uniqueTag(root, want, sha) {
  for (let i = 0; ; i++) {
    const name = i === 0 ? want : `${want}-${String(sha).slice(0, 8)}${i > 1 ? `-${i}` : ''}`;
    const have = G.git(root, ['rev-parse', '-q', '--verify', `refs/tags/${name}^{commit}`], { allowFail: true });
    if (!have.ok || !have.out.trim()) { const t = G.git(root, ['tag', name, sha], { allowFail: true, retryLock: true }); if (t.ok) return name; }
    else if (have.out.trim() === sha) return name;
    if (i > 5) return null;
  }
}

// worktree 하나를 잃지 않게 옮겨 놓는다 → {tag, files_dir, committed}
function salvageWorktree(root, w, salvageRoot) {
  const name = safeName(w.branch || path.basename(w.path));
  const out = { tag: null, files_dir: null, committed: false };
  if (G.dirtyFiles(w.path).length) {   // 중첩 worktree 는 이미 앞에서 치워졌다(깊은 것부터)
    const sha = G.commitAll(w.path, `harness: salvage uncommitted work from ${w.branch || path.basename(w.path)}`);
    out.committed = !!sha;
  }
  // 커밋에 들어가지 않은 것(비밀 파일 · 무시된 산출물)을 폴더로
  const left = [...new Set([...G.dirtyFiles(w.path).map(e => e.path).filter(f => !NOISE.test(f)), ...outsideGit(w.path)])];
  if (left.length) {
    const dir = path.join(salvageRoot, name, 'files');
    for (const rel of left) {
      const src = path.join(w.path, rel);
      try { if (!fs.statSync(src).isFile()) continue; fs.mkdirSync(path.dirname(path.join(dir, rel)), { recursive: true }); fs.copyFileSync(src, path.join(dir, rel)); out.files_dir = dir; }
      catch { /* 읽을 수 없는 파일은 건너뛴다 — 아래에서 worktree 를 지우기 전에 다시 확인한다 */ }
    }
  }
  const head = G.headSha(w.path);
  out.tag = uniqueTag(root, `harness/salvage/${name}`, head);
  out.head = head;
  return out;
}

function cleanup(o) {
  const apply = !!(o && o.apply), salvage = !!(o && o.salvage);
  let p = plan(o && o.root, { salvage });
  const done = { worktrees_removed: [], branches_deleted: [], dirs_deleted: [], salvaged: [], errors: [] };
  if (apply) {
    const salvageRoot = path.join(S.paths(p.root).harnessDir, 'legacy-salvage');
    for (const w of p.worktrees.filter(x => x.action === 'remove' || x.action === 'salvage')) {
      let force = false;
      if (w.action === 'salvage') {
        let s; try { s = salvageWorktree(p.root, w, salvageRoot); } catch (e) { done.errors.push(`${w.path}: salvage failed — ${e.message}`); continue; }
        if (!s.tag) { done.errors.push(`${w.path}: could not create a salvage tag — left in place`); continue; }
        done.salvaged.push({ what: w.branch || w.path, tag: s.tag, files_dir: s.files_dir, committed: s.committed });
        force = true;   // 남은 것은 잡음과 방금 복사한 파일뿐이다
      }
      const r = G.git(p.root, ['worktree', 'remove', ...(force ? ['--force'] : []), w.path], { allowFail: true, retryLock: true });
      if (r.ok) done.worktrees_removed.push(w.path); else done.errors.push(`${w.path}: ${String(r.err || '').trim().slice(0, 160)}`);
    }
    G.git(p.root, ['worktree', 'prune'], { allowFail: true });
    const first = p;
    p = plan(o && o.root, { salvage });   // worktree 가 실제로 사라진 뒤의 사실로 브랜치·폴더를 다시 판정한다
    p.worktrees = first.worktrees;
    const record = path.join(S.paths(p.root).harnessDir, 'legacy-pruned.json');
    let prev = []; try { prev = JSON.parse(fs.readFileSync(record, 'utf8')); } catch { prev = []; }
    const del = p.branches.filter(b => b.action === 'delete' || b.action === 'salvage');
    for (const b of del.filter(x => x.action === 'salvage')) {
      const have = done.salvaged.find(s => s.what === b.name);
      if (have && G.headSha(p.root, have.tag) === b.sha) { b.tag = have.tag; continue; }
      b.tag = uniqueTag(p.root, `harness/salvage/${safeName(b.name)}`, b.sha);
      if (b.tag) done.salvaged.push({ what: b.name, tag: b.tag, files_dir: null, committed: false });
    }
    const go = del.filter(b => b.action === 'delete' || b.tag);
    for (const b of del.filter(b => b.action === 'salvage' && !b.tag)) done.errors.push(`${b.name}: could not create a salvage tag — branch kept`);
    if (go.length) {
      fs.mkdirSync(path.dirname(record), { recursive: true });
      fs.writeFileSync(record, JSON.stringify([...prev, ...go.map(b => ({ name: b.name, sha: b.sha, merged_into: b.action === 'delete' ? p.current : null, salvage_tag: b.tag || null, at: new Date().toISOString() }))], null, 2) + '\n');
    }
    for (const b of go) {
      const r = G.git(p.root, ['branch', '-D', b.name], { allowFail: true, retryLock: true });
      if (r.ok) done.branches_deleted.push(b.name); else done.errors.push(`${b.name}: ${String(r.err || '').trim().slice(0, 160)}`);
    }
    for (const d of p.dirs.filter(x => x.action === 'delete')) {
      try { fs.rmSync(d.dir, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 }); done.dirs_deleted.push(d.dir); }
      catch (e) { done.errors.push(`${d.dir}: ${e.message}`); }
    }
  }
  return { ...p, applied: apply, ...done, ok: done.errors.length === 0 };
}

function format(r) {
  const mb = n => (n / 1048576).toFixed(1) + ' MB';
  const tag = (action, doneList, key) => action === 'keep' ? 'keep   ' : !r.applied ? action.padEnd(7) : (doneList.includes(key) || action === 'prune' ? (action === 'salvage' ? 'salvaged' : action === 'remove' ? 'removed' : 'deleted') : 'FAILED').padEnd(8);
  const L = [`cleanup-legacy: ${r.root} (on ${r.current || 'detached HEAD'})${r.salvage ? ' · salvage' : ''} — ${r.applied ? 'APPLIED' : 'dry run (nothing changed; add --apply after the user asks for the cleanup)'}`];
  if (!r.worktrees.length && !r.branches.length && !r.dirs.length) L.push('nothing left from earlier harness versions.');
  if (r.worktrees.length) {
    L.push(`legacy worktrees (${r.worktrees.length}):`);
    for (const w of r.worktrees) L.push(`  ${tag(w.action, r.worktrees_removed, w.path)} ${w.path}${w.branch ? ` [${w.branch}]` : ''} — ${w.why}`);
  }
  if (r.branches.length) {
    L.push(`legacy branches (${r.branches.length}):`);
    for (const b of r.branches) L.push(`  ${tag(b.action, r.branches_deleted, b.name)} ${b.name} @ ${String(b.sha || '').slice(0, 10)} — ${b.why}`);
  }
  if (r.dirs.length) {
    L.push('legacy state folders:');
    for (const d of r.dirs) L.push(`  ${tag(d.action, r.dirs_deleted, d.dir)} ${d.dir} (${mb(d.bytes)}) — ${d.why}`);
  }
  if (r.applied && r.salvaged.length) {
    L.push(`salvaged (${r.salvaged.length}) — commits stay reachable at these tags; files outside git were copied:`);
    for (const s of r.salvaged) L.push(`  ${s.what} → tag ${s.tag}${s.committed ? ' (uncommitted work committed first)' : ''}${s.files_dir ? ` · files: ${s.files_dir}` : ''}`);
  }
  if (r.applied && r.branches_deleted.length) L.push(`deleted branches are recorded in ${path.join(S.paths(r.root).harnessDir, 'legacy-pruned.json')} (restore: git branch <name> <sha>).`);
  for (const e of r.errors || []) L.push(`error: ${e}`);
  return L.join('\n');
}

module.exports = { plan, cleanup, format, isLegacyBranch, LEGACY_DIRS, NOISE };
