# Phase 5 proof — Organ 30: Communication and Human-State Interpreter

**Status under re-read:** `green`
**Survives mechanical adversarial re-read:** `no`
**Evaluated tip:** `aea675025b2e8ade58db001d1960157865ff9e95`
**Generated:** 2026-09-20T19:40:53+00:00

## Mechanical failures (enforceable subset)

- **C7**: integration_tests not executed here (needs vitest): frontend/src/superbrain/lib/aiosAdapter.humanState.test.ts -- pass --frontend-junit or --allow-unexecuted-frontend
- **C7**: integration_tests not executed here (needs vitest): frontend/src/workbench/GagosChrome.voice.test.tsx -- pass --frontend-junit or --allow-unexecuted-frontend
- **C12**: attestation is STALE: 1 of this organ's own production_entrypoints changed after cc8492f314eb -- aios/api/main.py. Re-verify at a current commit, or record the organ as yellow with the reason. An ancestor of HEAD is not the same as a current one.

## Written verdict keys that are not PASS/N/A

C8

## Notes

- Outside-machine / frozen spine / no Ollama / no Docker / browser-session / Phase 6
  residuals are never flipped green by this script.
- Green survival requires empty mechanical failures AND complete C1..C12 written verdicts.
