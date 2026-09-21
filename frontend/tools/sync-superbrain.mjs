/** Lab authoring -> product mirror. All validation precedes writes; assets and shell are excluded. */
import { createHash } from 'node:crypto';
import { existsSync, mkdirSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { dirname, extname, isAbsolute, join, relative, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import ts from 'typescript';

const extensions = ['.ts', '.tsx', '.js', '.jsx', '.css', '.json'];
const hash = (bytes) => createHash('sha256').update(bytes).digest('hex');
const portable = (path) => path.split(sep).join('/');
const inside = (root, path) => path === root || path.startsWith(root + sep);
const managed = (path) => !isAbsolute(path) && !path.includes('\\') && !path.split('/').includes('..')
  && path !== 'SuperbrainApp.jsx' && extensions.includes(extname(path));

function list(root, current = root) {
  if (!existsSync(current)) return [];
  return readdirSync(current, { withFileTypes: true }).flatMap((entry) => {
    if (entry.isSymbolicLink()) throw new Error(`Symlinks are not managed: ${entry.name}`);
    const path = join(current, entry.name);
    return entry.isDirectory() ? list(root, path) : [portable(relative(root, path))];
  }).filter(managed).sort();
}

export function syncSuperbrain(root, mode) {
  if (!['bootstrap', 'port', 'check'].includes(mode)) throw new Error('Use bootstrap, check, or port.');
  root = resolve(root);
  const product = join(root, 'frontend/src/superbrain');
  const lab = join(root, 'GAG demo/gag-orchestrator/src');
  const manifestPath = join(root, 'frontend/superbrain-source.json');
  if (mode === 'bootstrap') {
    if (existsSync(manifestPath)) throw new Error('Already bootstrapped. Use check or port.');
    if (list(lab).length) throw new Error('Lab already contains source; reconcile it explicitly before bootstrap.');
    const files = Object.fromEntries(list(product).map((path) => [path, hash(readFileSync(join(product, path)))]));
    for (const path of Object.keys(files)) {
      mkdirSync(dirname(join(lab, path)), { recursive: true });
      writeFileSync(join(lab, path), readFileSync(join(product, path)));
    }
    writeFileSync(manifestPath, JSON.stringify({ version: 1, baseline: 'accepted product; see implementation ledger', files }, null, 2) + '\n');
    return { mode, files: Object.keys(files).length, changed: [] };
  }
  const manifest = JSON.parse(readFileSync(manifestPath, 'utf8'));
  if (manifest.version !== 1 || !manifest.files || typeof manifest.files !== 'object') throw new Error('Unsupported source manifest');
  for (const [path, digest] of Object.entries(manifest.files)) {
    if (!managed(path)) throw new Error(`Invalid managed path: ${path}`);
    if (!existsSync(join(product, path)) || hash(readFileSync(join(product, path))) !== digest) {
      throw new Error(`Product drift: ${path}. Reconcile the outside edit in the lab before porting.`);
    }
    if (!existsSync(join(lab, path))) throw new Error(`Lab source missing: ${path}; deletion requires explicit migration.`);
  }
  const paths = list(lab);
  const contents = new Map(paths.map((path) => [path, readFileSync(join(lab, path))]));
  // Parse actual language imports, including dynamic imports and type-only imports.
  // Check relative/alias imports against the proposed complete product tree.
  const resolves = (target) => ['', ...extensions, ...extensions.map((ext) => `/index${ext}`)].some((suffix) => {
    const candidate = resolve(target + suffix);
    if (inside(product, candidate)) {
      const local = portable(relative(product, candidate));
      return contents.has(local) || (local === 'SuperbrainApp.jsx' && existsSync(candidate));
    }
    return inside(join(root, 'frontend'), candidate) && existsSync(candidate);
  });
  for (const [path, bytes] of contents) {
    if (!/\.[jt]sx?$/.test(path)) continue;
    for (const entry of ts.preProcessFile(bytes.toString('utf8'), true, true).importedFiles) {
      const name = entry.fileName;
      const target = name.startsWith('@/') ? join(product, name.slice(2))
        : name.startsWith('.') ? resolve(dirname(join(product, path)), name) : null;
      if (target && !resolves(target)) throw new Error(`Unresolved import: ${path} -> ${name}`);
    }
  }
  const changed = paths.filter((path) => {
    const target = join(product, path);
    if (!(path in manifest.files) && existsSync(target)) throw new Error(`Unmanaged product file collision: ${path}`);
    return hash(contents.get(path)) !== manifest.files[path];
  });
  if (mode === 'port') {
    for (const path of changed) {
      mkdirSync(dirname(join(product, path)), { recursive: true });
      writeFileSync(join(product, path), contents.get(path));
    }
    manifest.files = Object.fromEntries(paths.map((path) => [path, hash(contents.get(path))]));
    writeFileSync(manifestPath, JSON.stringify(manifest, null, 2) + '\n');
  }
  return { mode, files: paths.length, changed };
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    const result = syncSuperbrain(resolve(dirname(fileURLToPath(import.meta.url)), '../..'), process.argv[2] ?? 'check');
    process.stdout.write(JSON.stringify(result, null, 2) + '\n');
  } catch (error) {
    process.stderr.write(error.message + '\n');
    process.exitCode = 1;
  }
}
