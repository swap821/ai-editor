import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { syncSuperbrain } from './sync-superbrain.mjs';

function fixture() {
  const root = mkdtempSync(join(tmpdir(), 'gagos-port-'));
  const product = join(root, 'frontend/src/superbrain');
  mkdirSync(product, { recursive: true });
  writeFileSync(join(product, 'index.ts'), "import './value';\r\nexport const live = true;\r\n");
  writeFileSync(join(product, 'value.ts'), 'export const value = 1;\r\n');
  writeFileSync(join(product, 'SuperbrainApp.jsx'), 'operator-owned shell');
  return { root, product, lab: join(root, 'GAG demo/gag-orchestrator/src') };
}

test('bootstrap and first port preserve accepted bytes and leave shell outside ownership', () => {
  const f = fixture();
  const before = readFileSync(join(f.product, 'index.ts'));
  syncSuperbrain(f.root, 'bootstrap');
  assert.deepEqual(readFileSync(join(f.lab, 'index.ts')), before);
  assert.equal(syncSuperbrain(f.root, 'port').changed.length, 0);
  assert.equal(readFileSync(join(f.product, 'SuperbrainApp.jsx'), 'utf8'), 'operator-owned shell');
});

test('product drift blocks every write, including an unrelated lab change', () => {
  const f = fixture();
  syncSuperbrain(f.root, 'bootstrap');
  writeFileSync(join(f.product, 'value.ts'), 'outside writer');
  writeFileSync(join(f.lab, 'index.ts'), 'export const modified = true;');
  assert.throws(() => syncSuperbrain(f.root, 'port'), /Product drift/);
  assert.match(readFileSync(join(f.product, 'index.ts'), 'utf8'), /live = true/);
});

test('missing imports are detected before any product writes', () => {
  const f = fixture();
  syncSuperbrain(f.root, 'bootstrap');
  writeFileSync(join(f.lab, 'index.ts'), "import './absent';");
  assert.throws(() => syncSuperbrain(f.root, 'port'), /Unresolved import/);
  assert.match(readFileSync(join(f.product, 'index.ts'), 'utf8'), /live = true/);
});

test('dry run is read-only, successful port is reversible from the lab', () => {
  const f = fixture();
  syncSuperbrain(f.root, 'bootstrap');
  const old = readFileSync(join(f.lab, 'value.ts'));
  writeFileSync(join(f.lab, 'value.ts'), 'export const value = 2;');
  assert.deepEqual(syncSuperbrain(f.root, 'check').changed, ['value.ts']);
  assert.match(readFileSync(join(f.product, 'value.ts'), 'utf8'), /= 1/);
  syncSuperbrain(f.root, 'port');
  assert.match(readFileSync(join(f.product, 'value.ts'), 'utf8'), /= 2/);
  writeFileSync(join(f.lab, 'value.ts'), old);
  syncSuperbrain(f.root, 'port');
  assert.deepEqual(readFileSync(join(f.product, 'value.ts')), old);
});

test('manifest path traversal and attempts to manage assets fail closed', () => {
  for (const path of ['../../outside.ts', 'brain.glb', 'SuperbrainApp.jsx']) {
    const f = fixture();
    syncSuperbrain(f.root, 'bootstrap');
    const manifest = join(f.root, 'frontend/superbrain-source.json');
    const data = JSON.parse(readFileSync(manifest, 'utf8'));
    data.files[path] = 'anything';
    writeFileSync(manifest, JSON.stringify(data));
    assert.throws(() => syncSuperbrain(f.root, 'port'), /Invalid managed path/);
  }
});
