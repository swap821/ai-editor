import { test } from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, mkdtempSync, mkdirSync, readFileSync, rmSync, statSync, symlinkSync, utimesSync, writeFileSync } from 'node:fs';
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

test('restore recreates a missing lab from accepted product bytes without changing the manifest', () => {
  const f = fixture();
  syncSuperbrain(f.root, 'bootstrap');
  const manifestPath = join(f.root, 'frontend/superbrain-source.json');
  const acceptedManifest = readFileSync(manifestPath);
  rmSync(join(f.root, 'GAG demo'), { recursive: true, force: true });

  const result = syncSuperbrain(f.root, 'restore');

  assert.equal(result.mode, 'restore');
  assert.deepEqual(result.restored, ['index.ts', 'value.ts']);
  assert.deepEqual(result.unchanged, []);
  assert.deepEqual(readFileSync(join(f.lab, 'index.ts')), Buffer.from("import './value';\r\nexport const live = true;\r\n"));
  assert.deepEqual(readFileSync(join(f.lab, 'value.ts')), Buffer.from('export const value = 1;\r\n'));
  assert.deepEqual(readFileSync(manifestPath), acceptedManifest);
  assert.equal(readFileSync(join(f.product, 'index.ts'), 'utf8'), "import './value';\r\nexport const live = true;\r\n");
});

test('restore fills missing files, preserves identical destinations, and is idempotent', () => {
  const f = fixture();
  syncSuperbrain(f.root, 'bootstrap');
  const manifestPath = join(f.root, 'frontend/superbrain-source.json');
  const acceptedManifest = readFileSync(manifestPath);
  const retainedPath = join(f.lab, 'value.ts');
  const retainedTime = new Date('2001-01-01T00:00:00.000Z');
  utimesSync(retainedPath, retainedTime, retainedTime);
  const retainedMtime = statSync(retainedPath).mtimeMs;
  rmSync(join(f.lab, 'index.ts'));

  const first = syncSuperbrain(f.root, 'restore');
  const second = syncSuperbrain(f.root, 'restore');

  assert.deepEqual(first.restored, ['index.ts']);
  assert.deepEqual(first.unchanged, ['value.ts']);
  assert.deepEqual(second.restored, []);
  assert.deepEqual(second.unchanged, ['index.ts', 'value.ts']);
  assert.equal(statSync(retainedPath).mtimeMs, retainedMtime);
  assert.deepEqual(readFileSync(manifestPath), acceptedManifest);
});

test('a differing destination aborts restore before any missing file is written', () => {
  const f = fixture();
  syncSuperbrain(f.root, 'bootstrap');
  const manifestPath = join(f.root, 'frontend/superbrain-source.json');
  const acceptedManifest = readFileSync(manifestPath);
  rmSync(join(f.lab, 'index.ts'));
  writeFileSync(join(f.lab, 'value.ts'), 'operator bytes must survive');

  assert.throws(() => syncSuperbrain(f.root, 'restore'), /Lab source conflict: value\.ts/);
  assert.equal(existsSync(join(f.lab, 'index.ts')), false);
  assert.equal(readFileSync(join(f.lab, 'value.ts'), 'utf8'), 'operator bytes must survive');
  assert.deepEqual(readFileSync(manifestPath), acceptedManifest);
});

test('product drift blocks restore before creating any lab destination', () => {
  const f = fixture();
  syncSuperbrain(f.root, 'bootstrap');
  rmSync(join(f.root, 'GAG demo'), { recursive: true, force: true });
  writeFileSync(join(f.product, 'value.ts'), 'outside writer changed accepted bytes');

  assert.throws(() => syncSuperbrain(f.root, 'restore'), /Product drift: value\.ts/);
  assert.equal(existsSync(join(f.root, 'GAG demo')), false);
});

test('invalid manifest paths and digests block restore before any destination is created', () => {
  for (const [path, digest, expected] of [
    ['../../outside.ts', 'a'.repeat(64), /Invalid managed path/],
    ['sub/./value.ts', 'a'.repeat(64), /Invalid managed path/],
    ['value.ts', 'not-a-sha256', /Invalid SHA-256 digest/],
  ]) {
    const f = fixture();
    syncSuperbrain(f.root, 'bootstrap');
    rmSync(join(f.root, 'GAG demo'), { recursive: true, force: true });
    const manifestPath = join(f.root, 'frontend/superbrain-source.json');
    const manifest = JSON.parse(readFileSync(manifestPath, 'utf8'));
    manifest.files[path] = digest;
    writeFileSync(manifestPath, JSON.stringify(manifest));

    assert.throws(() => syncSuperbrain(f.root, 'restore'), expected);
    assert.equal(existsSync(join(f.root, 'GAG demo')), false);
  }
});

test('restore rejects case-folded duplicates and file/directory manifest collisions', () => {
  for (const [extraPath, expected] of [
    ['Value.ts', /Case-insensitive manifest path collision/],
    ['value.ts/child.ts', /Manifest file\/directory path collision/],
  ]) {
    const f = fixture();
    syncSuperbrain(f.root, 'bootstrap');
    rmSync(join(f.root, 'GAG demo'), { recursive: true, force: true });
    const manifestPath = join(f.root, 'frontend/superbrain-source.json');
    const manifest = JSON.parse(readFileSync(manifestPath, 'utf8'));
    manifest.files[extraPath] = 'a'.repeat(64);
    writeFileSync(manifestPath, JSON.stringify(manifest));

    assert.throws(() => syncSuperbrain(f.root, 'restore'), expected);
    assert.equal(existsSync(join(f.root, 'GAG demo')), false);
  }
});

test('restore rejects symlink and junctions in every existing lab destination prefix', () => {
  const prefixes = [
    ['GAG demo'],
    ['GAG demo', 'gag-orchestrator'],
    ['GAG demo', 'gag-orchestrator', 'src'],
    ['GAG demo', 'gag-orchestrator', 'src', 'index.ts'],
  ];
  for (const segments of prefixes) {
    const f = fixture();
    syncSuperbrain(f.root, 'bootstrap');
    rmSync(join(f.root, 'GAG demo'), { recursive: true, force: true });
    const outside = join(f.root, 'outside');
    mkdirSync(outside);
    const marker = join(outside, 'marker.ts');
    writeFileSync(marker, 'outside bytes stay untouched');
    const link = join(f.root, ...segments);
    mkdirSync(join(link, '..'), { recursive: true });
    symlinkSync(outside, link, process.platform === 'win32' ? 'junction' : 'dir');

    assert.throws(() => syncSuperbrain(f.root, 'restore'), /symlink or junction/);
    assert.equal(readFileSync(marker, 'utf8'), 'outside bytes stay untouched');
  }
});
