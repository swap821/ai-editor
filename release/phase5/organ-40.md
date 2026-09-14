# Phase 5 proof — Organ 40: Isolated Workspace and Executor (live proof)

**Status under re-read:** `yellow`
**Survives mechanical adversarial re-read:** `no`
**Evaluated tip:** `d8194dd981596bd86c7682d6684a29c9b0014c2d`
**Generated:** 2026-09-14T02:24:20+00:00

## Mechanical failures (enforceable subset)

- **residual**: STALE ATTESTATION (recorded 1b4e1310): 3 of this organ's own production_entrypoints changed after 14856c23e08b (aios/api/routes/mirror.py, aios/application/governance/runtime_proof.py, aios/application/read_models/executor_projections.py). The evidence below is preserved and was true at that commit; it is no longer known to describe HEAD. Re-verify at a current commit to restore green.

## Written verdict keys that are not PASS/N/A

C8, C9, C11, C12

## Notes

- Outside-machine / frozen spine / no Ollama / no Docker / browser-session / Phase 6
  residuals are never flipped green by this script.
- Green survival requires empty mechanical failures AND complete C1..C12 written verdicts.
