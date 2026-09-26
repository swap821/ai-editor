/** Lab authoring -> product mirror. All validation precedes writes; assets and shell are excluded. */
import { createHash } from 'node:crypto';
import { existsSync, lstatSync, mkdirSync, readFileSync, readdirSync, realpathSync, writeFileSync } from 'node:fs';
import { dirname, extname, isAbsolute, join, relative, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import ts from 'typescript';

const extensions = ['.ts', '.tsx', '.js', '.jsx', '.css', '.json'];
const exactHash = (bytes) => createHash('sha256').update(bytes).digest('hex');
// Version 2 tolerates only Git's CRLF/LF checkout conversion.
const hash = (bytes) => createHash('sha256')
  .update(Buffer.from(bytes.toString('latin1').replace(/\r\n/g, '\n'), 'latin1'))
  .digest('hex');
const digestFor = (bytes, version) => (version === 1 ? exactHash(bytes) : hash(bytes));
const portable = (path) => path.split(sep).join('/');
const inside = (root, path) => {
  const fromRoot = relative(root, path);
  return fromRoot === '' || (!isAbsolute(fromRoot) && fromRoot !== '..' && !fromRoot.startsWith('..' + sep));
};
const managed = (path) => typeof path === 'string' && path.length > 0 && !isAbsolute(path)
  && !path.includes('\\') && path.split('/').every((part) => part && part !== '.' && part !== '..' && !part.includes(':'))
  && path !== 'SuperbrainApp.jsx' && extensions.includes(extname(path));

const lstatOrMissing = (path) => {
  try {
    return lstatSync(path);
  } catch (error) {
    if (error.code === 'ENOENT') return null;
    throw error;
  }
};

function inspectUnderRoot(root, segments, label, expectedType) {
  const base = realpathSync(root);
  let current = base;
  for (let index = 0; index < segments.length; index += 1) {
    current = join(current, segments[index]);
    const info = lstatOrMissing(current);
    if (!info) return { path: resolve(current, ...segments.slice(index + 1)), exists: false };
    const display = portable(relative(base, current));
    if (info.isSymbolicLink()) throw new Error(label + ' path contains a symlink or junction: ' + display);
    const canonical = realpathSync(current);
    if (!inside(base, canonical)) throw new Error(label + ' path escapes its root: ' + display);
    const final = index === segments.length - 1;
    if (!final && !info.isDirectory()) throw new Error(label + ' parent is not a directory: ' + display);
    if (final && expectedType === 'file' && !info.isFile()) throw new Error(label + ' is not a regular file: ' + display);
    if (final && expectedType === 'directory' && !info.isDirectory()) throw new Error(label + ' is not a directory: ' + display);
  }
  return { path: current, exists: true };
}

function ensureDirectoriesUnderRoot(root, segments, label) {
  const base = realpathSync(root);
  let current = base;
  for (const segment of segments) {
    current = join(current, segment);
    let info = lstatOrMissing(current);
    if (!info) {
      mkdirSync(current);
      info = lstatOrMissing(current);
    }
    const display = portable(relative(base, current));
    if (!info || info.isSymbolicLink()) throw new Error(label + ' path contains a symlink or junction: ' + display);
    if (!info.isDirectory()) throw new Error(label + ' parent is not a directory: ' + display);
    const canonical = realpathSync(current);
    if (!inside(base, canonical)) throw new Error(label + ' path escapes its root: ' + display);
  }
  return current;
}

function isSafeManifestPath(path) {
  if (typeof path !== 'string' || !managed(path) || path.includes(':') || /[<>"|?*\u0000-\u001f]/.test(path)) return false;
  return path.split('/').every((segment) => segment && segment !== '.' && segment !== '..'
    && !/[. ]$/.test(segment)
    && !/^(con|prn|aux|nul|conin\$|conout\$|com[1-9]|lpt[1-9])(?:\.|$)/i.test(segment));
}

function validateManifest(manifest) {
  if (!manifest || Array.isArray(manifest) || typeof manifest !== 'object'
    || ![1, 2].includes(manifest.version) || !manifest.files || Array.isArray(manifest.files)
    || typeof manifest.files !== 'object') {
    throw new Error('Invalid source manifest: unsupported shape or version.');
  }
  const paths = Object.keys(manifest.files).sort();
  const canonicalPaths = paths.map((path) => path.split('/').map((segment) => segment.normalize('NFC').toLowerCase()).join('/'));
  const pathSet = new Set(canonicalPaths);
  if (pathSet.size !== canonicalPaths.length) {
    const firstPathByCanonical = new Map();
    for (let index = 0; index < canonicalPaths.length; index += 1) {
      const canonical = canonicalPaths[index];
      if (firstPathByCanonical.has(canonical)) {
        throw new Error('Case-insensitive manifest path collision: ' + paths[index]);
      }
      firstPathByCanonical.set(canonical, paths[index]);
    }
  }
  for (let index = 0; index < paths.length; index += 1) {
    const path = paths[index];
    const canonical = canonicalPaths[index];
    if (!isSafeManifestPath(path)) throw new Error('Invalid managed path: ' + path);
    const parts = canonical.split('/');
    for (let end = 1; end < parts.length; end += 1) {
      if (pathSet.has(parts.slice(0, end).join('/'))) throw new Error('Manifest file/directory path collision: ' + path);
    }
    if (typeof manifest.files[path] !== 'string' || !/^[a-f0-9]{64}$/.test(manifest.files[path])) {
      throw new Error('Invalid SHA-256 digest in source manifest: ' + path);
    }
  }
  return paths;
}

function readManifest(manifestPath) {
  const entry = lstatSync(manifestPath);
  if (entry.isSymbolicLink() || !entry.isFile()) throw new Error('Source manifest must be a regular file.');
  let manifest;
  try {
    manifest = JSON.parse(readFileSync(manifestPath, 'utf8'));
  } catch (error) {
    throw new Error('Invalid source manifest: ' + error.message);
  }
  validateManifest(manifest);
  return manifest;
}

function restoreAcceptedSource(root) {
  const manifestFile = inspectUnderRoot(root, ['frontend', 'superbrain-source.json'], 'Manifest', 'file');
  if (!manifestFile.exists) throw new Error('Source manifest missing; accepted product source cannot be restored.');
  const manifest = readManifest(manifestFile.path);
  const paths = validateManifest(manifest);

  const productBytes = new Map();
  for (const path of paths) {
    const source = inspectUnderRoot(root, ['frontend', 'src', 'superbrain', ...path.split('/')], 'Product source', 'file');
    if (!source.exists) throw new Error('Product source missing: ' + path);
    const bytes = readFileSync(source.path);
    if (digestFor(bytes, manifest.version) !== manifest.files[path]) {
      throw new Error('Product drift: ' + path + '. Reconcile the outside edit in the lab before restoring.');
    }
    productBytes.set(path, bytes);
  }

  const destinationRoot = ['GAG demo', 'gag-orchestrator', 'src'];
  const restored = [];
  const unchanged = [];
  for (const path of paths) {
    const destination = inspectUnderRoot(root, [...destinationRoot, ...path.split('/')], 'Lab destination', 'file');
    if (!destination.exists) {
      restored.push(path);
      continue;
    }
    if (!readFileSync(destination.path).equals(productBytes.get(path))) {
      throw new Error('Lab source conflict: ' + path + '; existing bytes differ. No files were restored.');
    }
    unchanged.push(path);
  }

  for (const path of restored) {
    const pathSegments = [...destinationRoot, ...path.split('/')];
    const parent = ensureDirectoriesUnderRoot(root, pathSegments.slice(0, -1), 'Lab destination');
    const destination = join(parent, pathSegments.at(-1));
    try {
      writeFileSync(destination, productBytes.get(path), { flag: 'wx' });
    } catch (error) {
      if (error.code === 'EEXIST') throw new Error('Lab source conflict: ' + path + '; destination appeared during restore.');
      throw error;
    }
  }
  return { mode: 'restore', files: paths.length, restored, unchanged, changed: [] };
}

function list(root, current = root) {
  if (!existsSync(current)) return [];
  return readdirSync(current, { withFileTypes: true }).flatMap((entry) => {
    if (entry.isSymbolicLink()) throw new Error('Symlinks are not managed: ' + entry.name);
    const path = join(current, entry.name);
    return entry.isDirectory() ? list(root, path) : [portable(relative(root, path))];
  }).filter(managed).sort();
}

export function syncSuperbrain(root, mode) {
  if (!['bootstrap', 'restore', 'port', 'check'].includes(mode)) throw new Error('Use bootstrap, restore, check, or port.');
  root = realpathSync(resolve(root));
  const product = join(root, 'frontend/src/superbrain');
  const lab = join(root, 'GAG demo/gag-orchestrator/src');
  const manifestPath = join(root, 'frontend/superbrain-source.json');
  if (mode === 'restore') return restoreAcceptedSource(root);
  if (mode === 'bootstrap') {
    if (existsSync(manifestPath)) throw new Error('Already bootstrapped. Use check or port.');
    if (list(lab).length) throw new Error('Lab already contains source; reconcile it explicitly before bootstrap.');
    const files = Object.fromEntries(list(product).map((path) => [path, hash(readFileSync(join(product, path)))]));
    for (const path of Object.keys(files)) {
      mkdirSync(dirname(join(lab, path)), { recursive: true });
      writeFileSync(join(lab, path), readFileSync(join(product, path)));
    }
    writeFileSync(manifestPath, JSON.stringify({ version: 2, baseline: 'accepted product; source SHA-256 normalizes CRLF to LF', files }, null, 2) + '\n');
    return { mode, files: Object.keys(files).length, changed: [] };
  }
  const manifest = readManifest(manifestPath);
  const digestForManifest = (bytes) => digestFor(bytes, manifest.version);
  for (const [path, digest] of Object.entries(manifest.files)) {
    const source = inspectUnderRoot(root, ['frontend', 'src', 'superbrain', ...path.split('/')], 'Product source', 'file');
    if (!source.exists || digestForManifest(readFileSync(source.path)) !== digest) {
      throw new Error('Product drift: ' + path + '. Reconcile the outside edit in the lab before porting.');
    }
    const destination = inspectUnderRoot(root, ['GAG demo', 'gag-orchestrator', 'src', ...path.split('/')], 'Lab source', 'file');
    if (!destination.exists) throw new Error('Lab source missing: ' + path + '; deletion requires explicit migration.');
  }
  const paths = list(lab);
  const contents = new Map(paths.map((path) => [path, readFileSync(join(lab, path))]));
  const resolves = (target) => ['', ...extensions, ...extensions.map((ext) => '/index' + ext)].some((suffix) => {
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
      if (target && !resolves(target)) throw new Error('Unresolved import: ' + path + ' -> ' + name);
    }
  }
  const changed = paths.filter((path) => {
    const target = join(product, path);
    if (!(path in manifest.files) && existsSync(target)) throw new Error('Unmanaged product file collision: ' + path);
    return digestForManifest(contents.get(path)) !== manifest.files[path];
  });
  if (mode === 'port') {
    for (const path of changed) {
      mkdirSync(dirname(join(product, path)), { recursive: true });
      writeFileSync(join(product, path), contents.get(path));
    }
    manifest.version = 2;
    manifest.baseline = 'accepted product; source SHA-256 normalizes CRLF to LF';
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
