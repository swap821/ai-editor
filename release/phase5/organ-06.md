# Phase 5 proof — Organ 6: Edge Trust Boundary

**Status under re-read:** `yellow`
**Survives mechanical adversarial re-read:** `no`
**Evaluated tip:** `0a8dcbb0507c800a2f748c59dd63a18aec868f48`
**Generated:** 2026-09-13T05:32:06+00:00

## Mechanical failures (enforceable subset)

- **residual**: STALE ATTESTATION (recorded 1b4e1310): 1 of this organ's own production_entrypoints changed after 5d482164707c (aios/interfaces/http/edge_security.py). The evidence below is preserved and was true at that commit; it is no longer known to describe HEAD. Re-verify at a current commit to restore green.

## Written verdict keys that are not PASS/N/A

C10

## Notes

- Outside-machine / frozen spine / no Ollama / no Docker / browser-session / Phase 6
  residuals are never flipped green by this script.
- Green survival requires empty mechanical failures AND complete C1..C12 written verdicts.
