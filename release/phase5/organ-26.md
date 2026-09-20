# Phase 5 proof — Organ 26: Emergency Stop Organ (full boundary hard-wiring)

**Status under re-read:** `green`
**Survives mechanical adversarial re-read:** `no`
**Evaluated tip:** `aea675025b2e8ade58db001d1960157865ff9e95`
**Generated:** 2026-09-20T19:40:52+00:00

## Mechanical failures (enforceable subset)

- **C12**: attestation is STALE: 1 of this organ's own production_entrypoints changed after cc8492f314eb -- aios/api/main.py. Re-verify at a current commit, or record the organ as yellow with the reason. An ancestor of HEAD is not the same as a current one.

## Written verdict keys that are not PASS/N/A

(none — written verdicts PASS/N/A)

## Notes

- Outside-machine / frozen spine / no Ollama / no Docker / browser-session / Phase 6
  residuals are never flipped green by this script.
- Green survival requires empty mechanical failures AND complete C1..C12 written verdicts.
