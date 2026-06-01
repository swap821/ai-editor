import { test } from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';
import { setScopeRoot, isPathInScope, commandStaysInScope } from '../scopeLock.js';

setScopeRoot(process.cwd());

test('a file inside the workspace is in scope', () => {
  assert.equal(isPathInScope('server.js').inScope, true);
  assert.equal(isPathInScope('./tests/scope.test.js').inScope, true);
});

test('relative traversal escapes scope', () => {
  assert.equal(isPathInScope('../../../etc/passwd').inScope, false);
});

test('absolute path outside scope is rejected', () => {
  const outside = process.platform === 'win32' ? 'C:\\Windows\\System32' : '/etc/passwd';
  assert.equal(isPathInScope(outside).inScope, false);
});

test('commandStaysInScope flags traversal token', () => {
  const r = commandStaysInScope('Get-Content ../../secret.txt');
  assert.equal(r.inScope, false);
  assert.ok(r.offending);
});

test('commandStaysInScope allows in-scope paths', () => {
  assert.equal(commandStaysInScope('Get-Content ./database.js').inScope, true);
});
