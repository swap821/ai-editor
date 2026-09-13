# Phase 5 proof — Organ 13: Isolated Executor Service (construction)

**Status under re-read:** `yellow`
**Survives mechanical adversarial re-read:** `no`
**Evaluated tip:** `8848c35fd512906566eda0cf5873a3c143e623f9`
**Generated:** 2026-09-13T14:35:49+00:00

## Mechanical failures (enforceable subset)

- **residual**: STALE LIVE EVIDENCE (recorded 8c5cc293): this organ's own production_entrypoint aios/executor_service.py changed after the evidence below was gathered at 5d482164707c -- the repair path's containment check was rewritten to canonicalise with realpath, and ten failure paths stopped reporting isolation_verified=True. The evidence is preserved and was true at that commit; it is no longer known to describe HEAD. Restoring green needs a Phase 4 live run at a current tip, not a re-stamped sha -- re-running the cited tests does not refresh a live proof.

## Written verdict keys that are not PASS/N/A

C10

## Notes

- Outside-machine / frozen spine / no Ollama / no Docker / browser-session / Phase 6
  residuals are never flipped green by this script.
- Green survival requires empty mechanical failures AND complete C1..C12 written verdicts.
