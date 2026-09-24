import { test } from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, mkdtempSync, mkdirSync, readFileSync, readdirSync, rmSync, symlinkSync, writeFileSync } from 'node:fs';
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

test('restore recreates a missing lab from accepted product bytes and preserves the manifest', () => {
  const f = fixture();
  syncSuperbrain(f.root, 'bootstrap');
  const manifestPath = join(f.root, 'frontend/superbrain-source.json');
  const manifestBefore = readFileSync(manifestPath);
  const accepted = new Map(['index.ts', 'value.ts'].map((path) => [path, readFileSync(join(f.product, path))]));
  rmSync(join(f.root, 'GAG demo'), { recursive: true, force: true });

  const result = syncSuperbrain(f.root, 'restore');

  assert.deepEqual(result, {
    mode: 'restore',
    files: 2,
    restored: ['index.ts', 'value.ts'],
    unchanged: [],
  });
  for (const [path, bytes] of accepted) {
    assert.deepEqual(readFileSync(join(f.lab, path)), bytes);
  }
  assert.deepEqual(readFileSync(manifestPath), manifestBefore);
  assert.deepEqual(syncSuperbrain(f.root, 'check').changed, []);
});

test('restore leaves matching files untouched, reports them, and safely fills a partial rerun', () => {
  const f = fixture();
  syncSuperbrain(f.root, 'bootstrap');
  const manifestPath = join(f.root, 'frontend/superbrain-source.json');
  const manifestBefore = readFileSync(manifestPath);
  const existing = readFileSync(join(f.lab, 'index.ts'));
  rmSync(join(f.lab, 'value.ts'));

  assert.deepEqual(syncSuperbrain(f.root, 'restore'), {
    mode: 'restore',
    files: 2,
    restored: ['value.ts'],
    unchanged: ['index.ts'],
  });
  assert.deepEqual(readFileSync(join(f.lab, 'index.ts')), existing);
  assert.deepEqual(syncSuperbrain(f.root, 'restore'), {
    mode: 'restore',
    files: 2,
    restored: [],
    unchanged: ['index.ts', 'value.ts'],
  });
  assert.deepEqual(readFileSync(manifestPath), manifestBefore);
  assert.deepEqual(syncSuperbrain(f.root, 'check').changed, []);
});

test('restore reports a conflicting destination before restoring any other missing file', () => {
  const f = fixture();
  syncSuperbrain(f.root, 'bootstrap');
  const conflict = Buffer.from('operator-authored bytes');
  writeFileSync(join(f.lab, 'value.ts'), conflict);
  rmSync(join(f.lab, 'index.ts'));

  assert.throws(() => syncSuperbrain(f.root, 'restore'), /conflict/i);
  assert.deepEqual(readFileSync(join(f.lab, 'value.ts')), conflict);
  assert.equal(existsSync(join(f.lab, 'index.ts')), false);
});

test('restore rejects product drift before restoring any missing file', () => {
  const f = fixture();
  syncSuperbrain(f.root, 'bootstrap');
  writeFileSync(join(f.product, 'value.ts'), 'outside product edit');
  rmSync(join(f.lab, 'value.ts'));

  assert.throws(() => syncSuperbrain(f.root, 'restore'), /Product drift/);
  assert.equal(existsSync(join(f.lab, 'value.ts')), false);
});

test('restore rejects malformed manifests and invalid SHA-256 digests before writes', () => {
  for (const invalid of [
    (manifest) => { manifest.files = []; },
    (manifest) => { manifest.files['value.ts'] = 'not-a-digest'; },
  ]) {
    const f = fixture();
    syncSuperbrain(f.root, 'bootstrap');
    const manifestPath = join(f.root, 'frontend/superbrain-source.json');
    const manifest = JSON.parse(readFileSync(manifestPath, 'utf8'));
    invalid(manifest);
    writeFileSync(manifestPath, JSON.stringify(manifest));
    rmSync(join(f.lab, 'value.ts'));

    assert.throws(() => syncSuperbrain(f.root, 'restore'), /Invalid source manifest|Invalid SHA-256/);
    assert.equal(existsSync(join(f.lab, 'value.ts')), false);
  }
});

test('restore rejects invalid manifest paths before creating missing destinations', () => {
  const f = fixture();
  syncSuperbrain(f.root, 'bootstrap');
  const manifestPath = join(f.root, 'frontend/superbrain-source.json');
  const manifest = JSON.parse(readFileSync(manifestPath, 'utf8'));
  manifest.files['../outside.ts'] = '0'.repeat(64);
  writeFileSync(manifestPath, JSON.stringify(manifest));
  rmSync(join(f.lab, 'value.ts'));

  assert.throws(() => syncSuperbrain(f.root, 'restore'), /Invalid managed path/);
  assert.equal(existsSync(join(f.lab, 'value.ts')), false);
});

test('restore rejects escaping symlinks at every existing lab directory prefix', (t) => {
  for (const linkedSegment of ['GAG demo', 'gag-orchestrator', 'src']) {
    const f = fixture();
    syncSuperbrain(f.root, 'bootstrap');
    rmSync(join(f.root, 'GAG demo'), { recursive: true, force: true });
    const outside = join(f.root, `outside-${linkedSegment.replaceAll(' ', '-')}`);
    mkdirSync(outside);
    let parent = f.root;
    for (const segment of ['GAG demo', 'gag-orchestrator', 'src']) {
      const destination = join(parent, segment);
      if (segment === linkedSegment) {
        try {
          symlinkSync(outside, destination, process.platform === 'win32' ? 'junction' : 'dir');
        } catch (error) {
          if (['EPERM', 'EACCES', 'ENOTSUP'].includes(error.code)) {
            t.skip(`directory symlinks are unavailable: ${error.code}`);
            return;
          }
          throw error;
        }
        break;
      }
      mkdirSync(destination);
      parent = destination;
    }

    assert.throws(() => syncSuperbrain(f.root, 'restore'), /symlink/i);
    assert.deepEqual(readdirSync(outside).sort(), []);
  }
});

test('restore rejects an escaping symlink in a manifest-owned nested destination path', (t) => {
  const f = fixture();
  mkdirSync(join(f.product, 'nested'));
  writeFileSync(join(f.product, 'nested/extra.ts'), 'export const nested = true;');
  syncSuperbrain(f.root, 'bootstrap');
  rmSync(join(f.root, 'GAG demo'), { recursive: true, force: true });
  mkdirSync(f.lab, { recursive: true });
  const outside = join(f.root, 'outside-nested');
  mkdirSync(outside);
  try {
    symlinkSync(outside, join(f.lab, 'nested'), 'junction');
  } catch (error) {
    if (['EPERM', 'EACCES', 'ENOTSUP'].includes(error.code)) {
      t.skip(`directory symlinks are unavailable: ${error.code}`);
      return;
    }
    throw error;
  }

  assert.throws(() => syncSuperbrain(f.root, 'restore'), /symlink/i);
  assert.deepEqual(readdirSync(outside), []);
});

test('restore refuses a final-destination junction without changing its outside target', (t) => {
  const f = fixture();
  syncSuperbrain(f.root, 'bootstrap');
  rmSync(join(f.root, 'GAG demo'), { recursive: true, force: true });
  mkdirSync(f.lab, { recursive: true });
  const outsideDirectory = join(f.root, 'outside-directory');
  mkdirSync(outsideDirectory);
  const outside = join(outsideDirectory, 'outside.ts');
  const original = Buffer.from('outside data');
  writeFileSync(outside, original);
  try {
    symlinkSync(outsideDirectory, join(f.lab, 'index.ts'), 'junction');
  } catch (error) {
    if (['EPERM', 'EACCES', 'ENOTSUP'].includes(error.code)) {
      t.skip(`directory junctions are unavailable: ${error.code}`);
      return;
    }
    throw error;
  }

  assert.throws(() => syncSuperbrain(f.root, 'restore'), /symlink/i);
  assert.deepEqual(readFileSync(outside), original);
  assert.equal(existsSync(join(f.lab, 'value.ts')), false);
});
