import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import { defineConfig, globalIgnores } from 'eslint/config'
import tsParser from '@typescript-eslint/parser'
import tsPlugin from '@typescript-eslint/eslint-plugin'

export default defineConfig([
  globalIgnores(['dist', 'coverage']),

  // ── Plain JS / JSX ─────────────────────────────────────────────────────────
  {
    files: ['**/*.{js,jsx}'],
    extends: [
      js.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      globals: { ...globals.browser, ...globals.node },
      parserOptions: { ecmaFeatures: { jsx: true } },
    },
    rules: {
      // Downgrade to warn so legacy files don't block CI while being cleaned up
      'no-unused-vars': ['warn', { argsIgnorePattern: '^_', varsIgnorePattern: '^_' }],
      // Official react-hooks rule (not "custom" — it ships in eslint-plugin-react-hooks
      // and catches non-local derived data / derived-event / external-sync bugs, not just
      // async-fetch-then-setState). Kept as 'warn' (not blocking) but NOT disabled: a
      // blanket 'off' was tried 2026-07-09 and reverted after a per-site audit found it
      // hides a real bug class this rule exists to catch, even though today's sites are fine.
      'react-hooks/set-state-in-effect': 'warn',
      'react-refresh/only-export-components': ['warn', { allowConstantExport: true }],
      // rules-of-hooks stays error — calling hooks conditionally is always wrong
      'react-hooks/rules-of-hooks': 'error',
    },
  },

  // ── TypeScript / TSX ────────────────────────────────────────────────────────
  {
    files: ['**/*.{ts,tsx}'],
    plugins: {
      '@typescript-eslint': tsPlugin,
      'react-hooks': reactHooks,
      'react-refresh': reactRefresh,
    },
    languageOptions: {
      parser: tsParser,
      globals: { ...globals.browser, ...globals.node },
      parserOptions: {
        ecmaFeatures: { jsx: true },
        // Project-less type-aware rules are skipped; use tsconfig only for
        // language features. Full type-aware rules can be enabled later by
        // pointing project: './tsconfig.json'.
      },
    },
    rules: {
      ...tsPlugin.configs.recommended.rules,
      // Keep these as warn while historical code is being cleaned up
      '@typescript-eslint/no-unused-vars': ['warn', { argsIgnorePattern: '^_', varsIgnorePattern: '^_' }],
      '@typescript-eslint/no-explicit-any': 'warn',
      // React hooks rules for tsx files
      'react-hooks/rules-of-hooks': 'error',
      'react-hooks/exhaustive-deps': 'warn',
      'react-refresh/only-export-components': ['warn', { allowConstantExport: true }],
      // Same as JS config — kept as 'warn', not disabled (see JS block comment).
      'react-hooks/set-state-in-effect': 'warn',
    },
  },
])
