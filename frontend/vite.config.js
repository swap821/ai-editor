import path from 'node:path'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
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
    // Next-ism shim so the lab files stay byte-identical: the adapter reads
    // this env at build time; same-origin default applies when unset.
    'process.env.NEXT_PUBLIC_AIOS_URL': JSON.stringify(
      process.env.NEXT_PUBLIC_AIOS_URL ?? null,
    ),
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.js'],
    css: false,
  },
})
