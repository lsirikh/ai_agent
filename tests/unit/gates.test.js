// tests/unit/gates.test.js — _gates.js 단위 테스트 (FR-21)
// 실행: node tests/unit/gates.test.js

const assert = require('assert');
const gates = require('../../.claude/hooks/_gates');

let passed = 0, failed = 0;
function test(name, fn) {
  try { fn(); passed++; console.log(`  ✅ ${name}`); }
  catch (e) { failed++; console.log(`  ❌ ${name}: ${e.message}`); }
}

console.log('\n── canTransitionTo ──');
test('dev→test (C) allowed', () => { assert(gates.canTransitionTo('dev', 'test', 'C').allowed); });
test('test→dev (C, no reason) blocked', () => { assert(!gates.canTransitionTo('test', 'dev', 'C').allowed); });
test('test→dev (C, reason) allowed', () => { assert(gates.canTransitionTo('test', 'dev', 'C', { reason: 'fix' }).allowed); });
test('test→dev is backward', () => { assert(gates.canTransitionTo('test', 'dev', 'C', { reason: 'fix' }).isBackward); });
test('complete→analysis allowed', () => { assert(gates.canTransitionTo('complete', 'analysis', 'C', { reason: 'new' }).allowed); });
test('dev→prd blocked (not in whitelist)', () => { assert(!gates.canTransitionTo('dev', 'prd', 'C').allowed); });
test('analysis→complete (A) allowed', () => { assert(gates.canTransitionTo('analysis', 'complete', 'A').allowed); });
test('analysis→dev (A) blocked (not in route)', () => { assert(!gates.canTransitionTo('analysis', 'dev', 'A').allowed); });
test('analysis→prd (B) blocked (not in route)', () => { assert(!gates.canTransitionTo('analysis', 'prd', 'B').allowed); });
test('analysis→dev (B) allowed', () => { assert(gates.canTransitionTo('analysis', 'dev', 'B').allowed); });
test('invalid phase blocked', () => { assert(!gates.canTransitionTo('dev', 'invalid', 'C').allowed); });
test('invalid track blocked', () => { assert(!gates.canTransitionTo('dev', 'test', 'X').allowed); });
test('skip forward blocked', () => { assert(!gates.canTransitionTo('analysis', 'dev', 'C').allowed); });
test('skip forward with force', () => { assert(gates.canTransitionTo('analysis', 'dev', 'C', { force: true }).allowed); });
test('same phase blocked', () => { assert(!gates.canTransitionTo('dev', 'dev', 'C').allowed); });

console.log('\n── isBlockingBashCommand ──');
test('rm -rf / always blocked', () => { assert(gates.isBlockingBashCommand('rm -rf /', 'setup').blocked); });
test('dd to src/ blocked in setup', () => { assert(gates.isBlockingBashCommand('dd if=a of=src/x', 'setup').blocked); });
test('dd to src/ allowed in dev', () => { assert(!gates.isBlockingBashCommand('dd if=a of=src/x', 'dev').blocked); });
test('sed -i src/ blocked in plan', () => { assert(gates.isBlockingBashCommand('sed -i "s/a/b/" src/file.js', 'plan').blocked); });
test('python -c write blocked', () => { assert(gates.isBlockingBashCommand('python -c "open(\'src/f\',\'w\').write(\'x\')"', 'setup').blocked); });
test('go build blocked in prd', () => { assert(gates.isBlockingBashCommand('go build ./cmd/...', 'prd', ['cmd/']).blocked); });
test('variable expansion with src/ path blocked', () => { assert(gates.isBlockingBashCommand('echo $VAR > src/file.js', 'setup').blocked); });
test('cat src/ (no write) not blocked', () => { assert(!gates.isBlockingBashCommand('cat src/file.js', 'setup').blocked); });
test('git log allowed', () => { assert(!gates.isBlockingBashCommand('git log --oneline', 'setup').blocked); });
test('empty command allowed', () => { assert(!gates.isBlockingBashCommand('', 'setup').blocked); });

console.log('\n── matchesFeedbackTrigger ──');
const rule1 = { active: true, trigger: { phase: 'complete', tool: 'Write', target: 'src/' } };
test('matching rule', () => { assert(gates.matchesFeedbackTrigger(rule1, { phase: 'complete', tool: 'Write', path: 'src/file.js' })); });
test('wrong phase', () => { assert(!gates.matchesFeedbackTrigger(rule1, { phase: 'dev', tool: 'Write', path: 'src/file.js' })); });
test('wrong tool', () => { assert(!gates.matchesFeedbackTrigger(rule1, { phase: 'complete', tool: 'Bash', path: 'src/file.js' })); });
test('wrong path', () => { assert(!gates.matchesFeedbackTrigger(rule1, { phase: 'complete', tool: 'Write', path: 'docs/file.md' })); });
test('wildcard phase', () => {
  const r = { active: true, trigger: { phase: '*', tool: '*', target: null } };
  assert(gates.matchesFeedbackTrigger(r, { phase: 'dev', tool: 'Bash', path: '' }));
});
test('pipe-separated phase', () => {
  const r = { active: true, trigger: { phase: 'dev|test', tool: '*', target: null } };
  assert(gates.matchesFeedbackTrigger(r, { phase: 'test', tool: 'Write', path: '' }));
});
test('inactive rule', () => { assert(!gates.matchesFeedbackTrigger({ active: false, trigger: { phase: '*' } }, { phase: 'dev' })); });

console.log(`\n══ 결과: ${passed} passed, ${failed} failed ══`);
if (failed > 0) process.exit(1);
