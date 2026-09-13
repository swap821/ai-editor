# Phase 5 proof — Organ 5: Prompt Injection Shield

**Status under re-read:** `green`
**Survives mechanical adversarial re-read:** `no`
**Evaluated tip:** `506c05d2d8b3aa5e090517c0feebefa52416b199`
**Generated:** 2026-09-13T11:42:28+00:00

## Mechanical failures (enforceable subset)

- **C12**: attestation is STALE: 1 of this FROZEN-SPINE organ's production_entrypoints changed after f3cb6122fb8d -- aios/security/injection_shield.py. Only the Human Sovereign can clear this: re-run scripts/spine_release_attest.py at a current commit. An agent must not demote a signed row -- the signature covers status.
- **C10**: FROZEN-SPINE live evidence is STALE: it was gathered at b5485d3b128e, and 1 of this organ's own production_entrypoints changed after it -- aios/security/injection_shield.py. Only the Human Sovereign can clear this: re-run the evidence and scripts/spine_release_attest.py at a current commit.

## Written verdict keys that are not PASS/N/A

(none — written verdicts PASS/N/A)

## Notes

- Outside-machine / frozen spine / no Ollama / no Docker / browser-session / Phase 6
  residuals are never flipped green by this script.
- Green survival requires empty mechanical failures AND complete C1..C12 written verdicts.
