import { readFileSync } from 'node:fs';

// Read actual CSS: Vitest's css:false deliberately stubs CSS module imports,
// including ?raw. Keep Node I/O in this test utility, out of production code.
export function readLivingMirrorStylesheet() {
  return readFileSync('src/livingMirror/livingMirror.css', 'utf8');
}
