# Phase 5 proof — Organ 3: Secret Scanner

**Status under re-read:** `green`
**Survives mechanical adversarial re-read:** `no`
**Evaluated tip:** `8c5cc29380dc492d964d2cf76399e37c7b37a38e`
**Generated:** 2026-09-13T10:53:05+00:00

## Mechanical failures (enforceable subset)

- **C12**: attestation is STALE: 1 of this FROZEN-SPINE organ's production_entrypoints changed after f3cb6122fb8d -- aios/security/secret_scanner.py. Only the Human Sovereign can clear this: re-run scripts/spine_release_attest.py at a current commit. An agent must not demote a signed row -- the signature covers status.
- **C10**: FROZEN-SPINE live evidence is STALE: it was gathered at b5485d3b128e, and 1 of this organ's own production_entrypoints changed after it -- aios/security/secret_scanner.py. Only the Human Sovereign can clear this: re-run the evidence and scripts/spine_release_attest.py at a current commit.

## Written verdict keys that are not PASS/N/A

(none — written verdicts PASS/N/A)

## Notes

- Outside-machine / frozen spine / no Ollama / no Docker / browser-session / Phase 6
  residuals are never flipped green by this script.
- Green survival requires empty mechanical failures AND complete C1..C12 written verdicts.
