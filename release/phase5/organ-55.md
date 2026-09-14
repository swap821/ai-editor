# Phase 5 proof — Organ 55: Governance Conformance Evaluation (Refusal Reel)

**Status under re-read:** `yellow`
**Survives mechanical adversarial re-read:** `no`
**Evaluated tip:** `d8c7b4af18c73dcecdb23c7862a94129027e3713`
**Generated:** 2026-09-14T12:01:06+00:00

## Mechanical failures (enforceable subset)

- **residual**: STALE ATTESTATION (recorded d8c7b4af): 2 of this organ's own production_entrypoints changed after a41cd5629c7e (tools/governance_conformance_runner.py, tools/governance_mission_drivers.py). The evidence below is preserved and was true at that commit; it is no longer known to describe HEAD. Re-verify at a current commit to restore green.
- **residual**: Operator attestation. The live-evidence blocker is DISCHARGED -- three consecutive cohorts at >=4/5 are recorded above with the artifact. What remains is the same gate organ 44 had: these runs were driven by the assistant on the operator's machine, and only he can attest to them. Status stays yellow until he does; the assistant will not flip its own evidence green. Note also that organ 55 is NOT reproducibly CONFORMANT -- it reliably reaches 4/5, with M1 gated on model behaviour that must not be engineered around, so any green should be read as '4/5 honest floor', not as 5/5.

## Written verdict keys that are not PASS/N/A

C9

## Notes

- Outside-machine / frozen spine / no Ollama / no Docker / browser-session / Phase 6
  residuals are never flipped green by this script.
- Green survival requires empty mechanical failures AND complete C1..C12 written verdicts.
