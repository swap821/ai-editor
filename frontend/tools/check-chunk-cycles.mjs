#!/usr/bin/env node
// Fails when the production build's JavaScript chunks import each other in a
// cycle. 2026-11-15: the built face loaded vendor-drei-postprocessing and the
// SuperbrainReactiveEffects chunk, each importing the other; drei's classes
// extended three-stdlib classes rolldown had placed in the app chunk, still
// undefined while the cycle evaluated ("Class extends value undefined"), and
// the face showed "Visual organism unavailable" with no 3D body. The build
// passed, and nothing ran what it built. Usage: node tools/check-chunk-cycles.mjs [dist]
import { readdirSync, readFileSync } from 'node:fs';
import { join, resolve } from 'node:path';

const assets = join(resolve(process.argv[2] ?? 'dist'), 'assets');
const chunks = readdirSync(assets).filter((name) => name.endsWith('.js'));
// Static imports only (`import ... from "./x.js"` and bare `import "./x.js"`):
// a dynamic import() is evaluated later and cannot leave a binding undefined.
const STATIC = /(?:\bfrom\s*|\bimport\s*)["']\.\/([^"']+\.js)["']/g;
const edges = new Map(
  chunks.map((name) => {
    const text = readFileSync(join(assets, name), 'utf8');
    return [name, [...new Set([...text.matchAll(STATIC)].map((m) => m[1]))].filter((to) => to !== name)];
  }),
);

const cycles = [];
const state = new Map(); // undefined = unvisited, 1 = on the path, 2 = done
const path = [];
function visit(name) {
  state.set(name, 1);
  path.push(name);
  for (const to of edges.get(name) ?? []) {
    if (state.get(to) === 1) cycles.push([...path.slice(path.indexOf(to)), to]);
    else if (!state.get(to)) visit(to);
  }
  path.pop();
  state.set(name, 2);
}
for (const name of chunks) if (!state.get(name)) visit(name);

if (cycles.length) {
  console.error(`${cycles.length} import cycle(s) between built chunks:`);
  for (const cycle of cycles) console.error(`  ${cycle.join(' -> ')}`);
  process.exit(1);
}
console.log(`${chunks.length} built chunks, no import cycle between them`);
