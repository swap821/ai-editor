# Phase 5 proof — Organ 40: Isolated Workspace and Executor (live proof)

**Status under re-read:** `yellow`
**Survives mechanical adversarial re-read:** `no`
**Evaluated tip:** `3207c375707626e95f1fece092e84936b6032f04`
**Generated:** 2026-09-14T08:55:47+00:00

## Mechanical failures (enforceable subset)

- **residual**: STALE ATTESTATION (recorded 3207c375): 5 of this organ's own production_entrypoints changed after db0441144db9 (aios/api/routes/mirror.py, aios/application/executor/service.py, aios/application/governance/runtime_proof.py, aios/application/read_models/executor_projections.py, frontend/src/workbench/SovereignStatePanel.jsx). The evidence below is preserved and was true at that commit; it is no longer known to describe HEAD. Re-verify at a current commit to restore green.

## Written verdict keys that are not PASS/N/A

C8, C9, C11, C12

## Notes

- Outside-machine / frozen spine / no Ollama / no Docker / browser-session / Phase 6
  residuals are never flipped green by this script.
- Green survival requires empty mechanical failures AND complete C1..C12 written verdicts.
