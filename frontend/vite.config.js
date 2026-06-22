import path from 'node:path'
import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig(({ mode }) => {
  // ── ONE backend boundary (Phase 1) ───────────────────────────────────────
  // Both UIs must resolve the SAME backend. The classic client reads
  // import.meta.env.VITE_* directly (src/config.js). The superbrain adapter is
  // a PORT-MANAGED file (byte-identical to the lab, overwritten by `npm run
  // port`) that reads Next-style process.env.NEXT_PUBLIC_*. This `define` is the
  // one place a Vite build can feed the product's env into the lab's env shape —
  // so we bridge VITE_* -> NEXT_PUBLIC_* here instead of editing the ported file.
  const env = loadEnv(mode, process.cwd(), '')
  const AIOS_BASE = env.VITE_API_BASE || 'http://localhost:8000'
  const AIOS_TOKEN = env.VITE_AIOS_API_TOKEN || ''
  return {
    plugins: [
      react(),
      tailwindcss(),
    ],
    resolve: {
      // The superbrain experience is extracted verbatim from the operator's
      // visual lab, whose internal imports use '@/...'. The alias points INTO
      // the superbrain module so those files stay byte-identical to the lab.
      alias: {
        '@': path.resolve(__dirname, './src/superbrain'),
      },
    },
    define: {
      // Unify the superbrain adapter's base URL with the classic client — kills
      // the 127.0.0.1-vs-localhost split (and the credentialed-CORS footgun it
      // caused). Honours VITE_API_BASE so an operator override applies to BOTH UIs.
      'process.env.NEXT_PUBLIC_AIOS_URL': JSON.stringify(AIOS_BASE),
      // Pre-wire the Bearer token under the same Next-style name so the
      // superbrain adapter can adopt auth via a lab edit + re-port (Phase 1b)
      // with no further product change. Harmless/dead until the adapter reads it.
      'process.env.NEXT_PUBLIC_AIOS_TOKEN': JSON.stringify(AIOS_TOKEN),
    },
    // ── W5-2 CODE-SPLIT ───────────────────────────────────────────────────────
    // The prod build used to emit one ~1.3 MB chunk (over Vite's 500 KB warning).
    // Split the heaviest, independently-cacheable libraries into their own vendor
    // chunks so no single chunk crosses the warning. Behaviour-preserving: no
    // import changes, no new lazy boundaries — pure module grouping.
    //
    // Vite 8 bundles with ROLLDOWN. Its rollup-compat `output.manualChunks`
    // function is only ADVISORY for modules shared across chunks — rolldown's
    // optimizer was observed to override it and co-bundle three.js core (~600 KB)
    // into the drei chunk. The authoritative, deterministic API is rolldown's
    // native `output.codeSplitting.groups`, which forces a module into a named
    // group by regex. We isolate three.js core into its own group so it caches
    // independently and never co-bundles with the r3f/drei layer.
    // (`codeSplitting` is the current key; the older `advancedChunks` alias is
    // deprecated in this rolldown and emits a build-time WARN — same group shape.)
    build: {
      rollupOptions: {
        output: {
          codeSplitting: {
            groups: [
              // ORDER MATTERS: first matching group wins. three.js core must be
              // matched before drei/r3f so the ~600 KB monolith lands here.
              { name: 'vendor-three', test: /[\\/]node_modules[\\/]three[\\/]/ },
              { name: 'vendor-drei', test: /[\\/]node_modules[\\/]@react-three[\\/]drei[\\/]/ },
              { name: 'vendor-postprocessing', test: /[\\/]node_modules[\\/]postprocessing[\\/]/ },
              { name: 'vendor-r3f', test: /[\\/]node_modules[\\/]@react-three[\\/]/ },
              { name: 'vendor-monaco', test: /[\\/]node_modules[\\/]@monaco-editor[\\/]/ },
              { name: 'vendor-react', test: /[\\/]node_modules[\\/](react|react-dom|scheduler)[\\/]/ },
            ],
          },
        },
      },
      // HONEST FLOOR: three.js core ships as ONE monolithic ES module (~730 KB
      // minified, ~186 KB gzip) that no chunking strategy can split — it is a
      // single file, and lazy-loading would only move the same bytes into an
      // async chunk that warns identically. EVERY OTHER chunk is now well under
      // 500 KB (next largest is vendor-drei at ~430 KB). The limit is set just
      // above the irreducible three.js floor so the build is clean, while still
      // flagging any NEW chunk that grows past three.js core. The original single
      // ~1.3 MB app chunk (over the 500 KB default) is eliminated.
      chunkSizeWarningLimit: 750,
    },
    test: {
      environment: 'jsdom',
      globals: true,
      setupFiles: ['./src/test/setup.js'],
      css: false,
    },
  }
})
