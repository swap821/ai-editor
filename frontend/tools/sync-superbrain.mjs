/** Lab authoring -> product mirror. All validation precedes writes; assets and shell are excluded. */
import { createHash } from 'node:crypto';
import { existsSync, lstatSync, mkdirSync, readFileSync, readdirSync, realpathSync, writeFileSync } from 'node:fs';
import { dirname, extname, isAbsolute, join, relative, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import ts from 'typescript';

const extensions = ['.ts', '.tsx', '.js', '.jsx', '.css', '.json'];
const hash = (bytes) => createHash('sha256').update(bytes).digest('hex');
const portable = (path) => path.split(sep).join('/');
const inside = (root, path) => path === root || path.startsWith(root + sep);
const managed = (path) => typeof path === 'string' && path.length > 0 && !isAbsolute(path)
  && !path.includes('\\') && path.split('/').every((part) => part && part !== '.' && part !== '..' && !part.includes(':'))
  && path !== 'SuperbrainApp.jsx' && extensions.includes(extname(path));

function readManifest(manifestPath) {
  const entry = lstatSync(manifestPath);
  if (entry.isSymbolicLink() || !entry.isFile()) throw new Error('Source manifest must be a regular file.');
  const manifest = JSON.parse(readFileSync(manifestPath, 'utf8'));
  if (manifest.version !== 1 || !manifest.files || typeof manifest.files !== 'object' || Array.isArray(manifest.files)) {
    throw new Error('Invalid source manifest: unsupported shape or version.');
  }
  for (const [path, digest] of Object.entries(manifest.files)) {
    if (!managed(path)) throw new Error(`Invalid managed path: ${path}`);
    if (typeof digest !== 'string' || !/^[a-f0-9]{64}$/.test(digest)) {
      throw new Error(`Invalid SHA-256 digest: ${path}`);
    }
  }
  return manifest;
}

function readAcceptedProductFile(product, path) {
  let current = product;
  const segments = path.split('/');
  for (const [index, segment] of segments.entries()) {
    current = join(current, segment);
    let info;
    try {
      info = lstatSync(current);
    } catch (error) {
      if (error.code === 'ENOENT') throw new Error(`Product drift: ${path}. Accepted source is missing.`);
      throw error;
    }
    if (info.isSymbolicLink()) throw new Error(`Product source symlink is not accepted: ${path}`);
    if (index < segments.length - 1 && !info.isDirectory()) {
      throw new Error(`Product drift: ${path}. A source directory is missing.`);
    }
    if (index === segments.length - 1 && !info.isFile()) {
      throw new Error(`Product drift: ${path}. Accepted source is not a regular file.`);
    }
  }
  return readFileSync(current);
}

function inspectLabFile(root, lab, path) {
  const segments = [...relative(root, lab).split(sep), ...path.split('/')];
  let current = root;
  let missing = false;
  for (const [index, segment] of segments.entries()) {
    current = join(current, segment);
    if (!inside(root, current)) throw new Error(`Destination escapes the worktree: ${path}`);
    if (missing) continue;
    let info;
    try {
      info = lstatSync(current);
    } catch (error) {
      if (error.code === 'ENOENT') {
        missing = true;
        continue;
      }
      throw error;
    }
    if (info.isSymbolicLink()) throw new Error(`Destination symlink is not allowed: ${current}`);
    if (index < segments.length - 1 && !info.isDirectory()) {
      throw new Error(`Destination path component is not a directory: ${current}`);
    }
    if (index === segments.length - 1) {
      if (!info.isFile()) throw new Error(`Destination is not a regular file: ${current}`);
      return { exists: true, path: current, bytes: readFileSync(current) };
    }
  }
  return { exists: false, path: current };
}

function createSafeParents(root, destination) {
  if (!inside(root, destination)) throw new Error(`Destination escapes the worktree: ${destination}`);
  const parent = dirname(destination);
  const segments = relative(root, parent).split(sep).filter(Boolean);
  let current = root;
  for (const segment of segments) {
    current = join(current, segment);
    try {
      const info = lstatSync(current);
      if (info.isSymbolicLink()) throw new Error(`Destination symlink is not allowed: ${current}`);
      if (!info.isDirectory()) throw new Error(`Destination path component is not a directory: ${current}`);
    } catch (error) {
      if (error.code !== 'ENOENT') throw error;
      mkdirSync(current);
      const info = lstatSync(current);
      if (info.isSymbolicLink() || !info.isDirectory()) {
        throw new Error(`Destination directory changed during restore: ${current}`);
      }
    }
  }
}

function restoreAuthoringSource(root, product, lab, manifest) {
  const files = [];
  for (const [path, digest] of Object.entries(manifest.files)) {
    const bytes = readAcceptedProductFile(product, path);
    if (hash(bytes) !== digest) throw new Error(`Product drift: ${path}. Reconcile the outside edit before restoring.`);
    files.push({ path, bytes });
  }

  const destinations = files.map(({ path, bytes }) => {
    const destination = inspectLabFile(root, lab, path);
    if (destination.exists && !destination.bytes.equals(bytes)) {
      throw new Error(`Restore conflict: lab file differs from accepted product bytes: ${path}`);
    }
    return { path, bytes, destination };
  });

  const restored = [];
  const unchanged = [];
  for (const { path, bytes, destination } of destinations) {
    if (destination.exists) {
      unchanged.push(path);
      continue;
    }
    createSafeParents(root, destination.path);
    try {
      writeFileSync(destination.path, bytes, { flag: 'wx' });
      restored.push(path);
    } catch (error) {
      if (error.code !== 'EEXIST') throw error;
      const current = inspectLabFile(root, lab, path);
      if (!current.exists || !current.bytes.equals(bytes)) {
        throw new Error(`Restore conflict: lab file appeared with different bytes: ${path}`);
      }
      unchanged.push(path);
    }
  }
  return { mode: 'restore', files: files.length, restored, unchanged };
}

function list(root, current = root) {
  if (!existsSync(current)) return [];
  return readdirSync(current, { withFileTypes: true }).flatMap((entry) => {
    if (entry.isSymbolicLink()) throw new Error(`Symlinks are not managed: ${entry.name}`);
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
  const manifest = readManifest(manifestPath);
  if (mode === 'restore') return restoreAuthoringSource(root, product, lab, manifest);
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
