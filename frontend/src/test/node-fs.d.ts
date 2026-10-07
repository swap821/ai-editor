// Narrow, test-only declaration for the installed Node CSS-file reader.
// The browser app has no Node dependency; no @types/node install is needed.
declare module 'node:fs' {
  export function readFileSync(path: string, encoding: 'utf8'): string;
}
