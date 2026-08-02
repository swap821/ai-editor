# Phase 5 proof — Organ 2: Scope Lock

**Status under re-read:** `yellow`
**Survives mechanical adversarial re-read:** `no`
**Evaluated tip:** `5c64cd54ca528121935c010f151ea0e2219ce95c`
**Generated:** 2026-08-02T10:02:56+00:00

## Mechanical failures (enforceable subset)

- **residual**: frozen spine — section VIII controlled release required before green/live claim
- **residual**: C4: N/A-BY-DESIGN — aios/security/scope_lock.py::ScopeLockAuthority.is_path_in_scope

## Written verdict keys that are not PASS/N/A

C9

## Notes

- Outside-machine / frozen spine / no Ollama / no Docker / browser-session / Phase 6
  residuals are never flipped green by this script.
- Green survival requires empty mechanical failures AND complete C1..C12 written verdicts.
