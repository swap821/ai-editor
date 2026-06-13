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
    test: {
      environment: 'jsdom',
      globals: true,
      setupFiles: ['./src/test/setup.js'],
      css: false,
    },
  }
})
