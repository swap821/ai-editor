# Phase 5 proof — Organ 52: Observability and Health Organ

**Status under re-read:** `yellow`
**Survives mechanical adversarial re-read:** `no`
**Evaluated tip:** `b5e11386ca3569fa6d56e0ca480d3883c712977b`
**Generated:** 2026-09-02T08:37:35+00:00

## Mechanical failures (enforceable subset)

- **residual**: Phase 4 absolute residual: held back from wave 1 (2026-09-01). Its C3/C4/C5 referents are in place and resolve, but C10's existing evidence row cites an executor-integration node that needs a real Docker daemon, which the machine preparing this wave did not have. CI's release-authority job does run it and merges the resulting JUnit into the same gate invocation, so this is expected to clear there -- but promoting an organ whose own phase 5 artifact records 'survives mechanical adversarial re-read: no' would ship an inconsistency. Promote once that node is observed passing in the gate's own run. See release/organ-ledger/2026-09-01-wave1-restoration.md

## Written verdict keys that are not PASS/N/A

C10

## Notes

- Outside-machine / frozen spine / no Ollama / no Docker / browser-session / Phase 6
  residuals are never flipped green by this script.
- Green survival requires empty mechanical failures AND complete C1..C12 written verdicts.
