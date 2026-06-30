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

  // ── Content-Security-Policy (C18), MODE-AWARE ─────────────────────────────
  // The dev server MUST allow script 'unsafe-inline' — @vitejs/plugin-react
  // injects an inline React-refresh preamble. The production BUILD has no inline
  // scripts (the boot loader is the external /boot-loader.js), so the shipped CSP
  // drops 'unsafe-inline' entirely. 'wasm-unsafe-eval' is kept (WebGL/three may
  // compile WASM) — it permits WebAssembly only, NOT JS eval(). No 'unsafe-eval'
  // (troika runs main-thread, see troikaConfig.ts) and no blob: in script-src.
  // Fonts are self-hosted, so no CDN allowance. A too-strict `script-src 'self'`
  // once blocked all of this and silently killed the 3D scene.
  const isDev = mode !== 'production'
  const csp = [
    "default-src 'self'",
    isDev
      ? "script-src 'self' 'unsafe-inline' 'wasm-unsafe-eval'"
      : "script-src 'self' 'wasm-unsafe-eval'",
    "style-src 'self' 'unsafe-inline'",
    "connect-src 'self' ws://localhost:8000 wss://* http://localhost:8000 https://*",
    "img-src 'self' data: blob:",
    "font-src 'self' data:",
    "media-src 'self' blob:",
    "worker-src 'self' blob:",
    "object-src 'none'",
    "base-uri 'self'",
    "frame-ancestors 'none'",
  ].join('; ') + ';'
  const cspPlugin = {
    name: 'gagos-csp',
    transformIndexHtml() {
      return [{
        tag: 'meta',
        attrs: { 'http-equiv': 'Content-Security-Policy', content: csp },
        injectTo: 'head-prepend',
      }]
    },
  }

  return {
    plugins: [
      cspPlugin,
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
      // SECURITY: API token is NO LONGER baked into the bundle at build time.
      // The adapter uses httpOnly session cookies for operator continuity; a
      // token-protected non-loopback deployment must sit behind a trusted
      // same-origin/reverse-proxy auth boundary rather than exposing the bearer
      // token to browser JavaScript.
      // 'process.env.NEXT_PUBLIC_AIOS_TOKEN' is intentionally REMOVED —
      // embedding secrets in the frontend bundle exposes them to anyone who
      // views the source.
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
              { name: 'vendor-drei-postprocessing', test: /[\\/]node_modules[\\/](@react-three[\\/]drei|postprocessing|@react-three[\\/]postprocessing)[\\/]/ },
              { name: 'vendor-r3f', test: /[\\/]node_modules[\\/]@react-three[\\/]/ },
              { name: 'vendor-monaco', test: /[\\/]node_modules[\\/](@monaco-editor|monaco-editor)[\\/]/ },
              { name: 'vendor-react', test: /[\\/]node_modules[\\/](react|react-dom|scheduler)[\\/]/ },
              { name: 'vendor-motion', test: /[\\/]node_modules[\\/]motion[\\/]/ },
            ],
          },
        },
      },
      // HONEST FLOOR: three.js core ships as ONE monolithic ES module (~730 KB
      // minified, ~186 KB gzip) that no chunking strategy can split. Self-hosting
      // Monaco adds a ~4.2 MB vendor-monaco chunk and ~1–6.9 MB language worker
      // chunks; those are the new irreducible size floor. The limit is set just
      // above the largest worker so the build stays clean, while still flagging
      // any NEW chunk that grows past the Monaco worker floor. The original single
      // ~1.3 MB app chunk (over the 500 KB default) is eliminated.
      sourcemap: mode === 'production' ? false : true,
      chunkSizeWarningLimit: 7200,
    },
    test: {
      environment: 'jsdom',
      globals: true,
      setupFiles: ['./src/test/setup.js'],
      css: false,
    },
  }
})
