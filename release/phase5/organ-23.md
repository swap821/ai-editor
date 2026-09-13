# Phase 5 proof — Organ 23: Release Conformance Organ

**Status under re-read:** `yellow`
**Survives mechanical adversarial re-read:** `no`
**Evaluated tip:** `506c05d2d8b3aa5e090517c0feebefa52416b199`
**Generated:** 2026-09-13T11:42:29+00:00

## Mechanical failures (enforceable subset)

- **residual**: STALE ATTESTATION (recorded 1b4e1310): 1 of this organ's own production_entrypoints changed after abf7346def48 (tests/test_organ_release_conformance.py). The evidence below is preserved and was true at that commit; it is no longer known to describe HEAD. Re-verify at a current commit to restore green.

## Written verdict keys that are not PASS/N/A

C10

## Notes

- Outside-machine / frozen spine / no Ollama / no Docker / browser-session / Phase 6
  residuals are never flipped green by this script.
- Green survival requires empty mechanical failures AND complete C1..C12 written verdicts.
