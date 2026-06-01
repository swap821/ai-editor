// scopeLock.js
// Path canonicalization + scope-root enforcement.
// Prevents directory-escape attacks (../../etc/passwd, absolute paths, symlinks)
// by resolving every path to an absolute, real path before comparing it against
// the declared session scope root. Fail-closed: anything that cannot be proven
// in-scope is treated as out-of-scope.

import path from 'path';
import fs from 'fs';

// The scope root is the only directory tree the agent may touch.
// Defaults to the current working directory (the project workspace).
let SCOPE_ROOT = process.env.AIOS_SCOPE_ROOT
  ? path.resolve(process.env.AIOS_SCOPE_ROOT)
  : process.cwd();

export function setScopeRoot(dir) {
  SCOPE_ROOT = path.resolve(dir);
  return SCOPE_ROOT;
}

export function getScopeRoot() {
  return SCOPE_ROOT;
}

/**
 * Resolve a candidate path to its real absolute location, following symlinks
 * where they already exist, and check whether it stays inside the scope root.
 * @param {string} candidate - raw path the agent wants to touch
 * @returns {{ inScope: boolean, resolved: string, reason: string }}
 */
export function isPathInScope(candidate) {
  try {
    if (!candidate || typeof candidate !== 'string') {
      return { inScope: false, resolved: '', reason: 'Empty or invalid path.' };
    }

    // Resolve relative components (./, ../) against the scope root.
    let resolved = path.resolve(SCOPE_ROOT, candidate);

    // Follow symlinks on whatever prefix of the path already exists, so a
    // symlink pointing outside the root cannot be used to escape.
    let probe = resolved;
    while (probe && probe !== path.dirname(probe)) {
      if (fs.existsSync(probe)) {
        resolved = path.resolve(fs.realpathSync(probe), path.relative(probe, resolved));
        break;
      }
      probe = path.dirname(probe);
    }

    const root = SCOPE_ROOT.endsWith(path.sep) ? SCOPE_ROOT : SCOPE_ROOT + path.sep;
    const inScope = resolved === SCOPE_ROOT || resolved.startsWith(root);

    return {
      inScope,
      resolved,
      reason: inScope
        ? 'Path within declared scope.'
        : `Path '${resolved}' escapes scope root '${SCOPE_ROOT}'.`,
    };
  } catch (e) {
    // Fail-closed: any resolution error means we cannot prove safety.
    return { inScope: false, resolved: '', reason: `Path resolution failed: ${e.message}` };
  }
}

// Heuristic: pull path-like tokens out of a shell command and check each one.
// Catches obvious traversal even when we are not handed a clean filepath arg.
const PATH_TOKEN = /(?:[a-zA-Z]:\\|\.{1,2}[\\/]|[\\/])[^\s"';|&]*/g;

export function commandStaysInScope(command) {
  if (!command) return { inScope: false, offending: null, reason: 'Empty command.' };
  const tokens = command.match(PATH_TOKEN) || [];
  for (const tok of tokens) {
    // Ignore pure flags like "/s" or "-rf"; require a path-ish shape.
    if (tok.length < 3) continue;
    const check = isPathInScope(tok);
    if (!check.inScope) {
      return { inScope: false, offending: tok, reason: check.reason };
    }
  }
  return { inScope: true, offending: null, reason: 'All paths within scope.' };
}
