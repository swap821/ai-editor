# Phase 5 proof — Organ 40: Isolated Workspace and Executor (live proof)

**Status under re-read:** `yellow`
**Survives mechanical adversarial re-read:** `no`
**Evaluated tip:** `b5e11386ca3569fa6d56e0ca480d3883c712977b`
**Generated:** 2026-09-02T08:37:34+00:00

## Mechanical failures (enforceable subset)

- **residual**: Phase 4 absolute residual: held back from wave 4 (2026-09-01). Its C3/C4/C5 referents are in place and resolve, but C7 cannot be proven on a machine without Docker: this organ's ONLY integration suite is tests/test_executor_integration.py, which gates on AIOS_EXECUTOR_INTEGRATION and skips all four tests locally, so the gate correctly reports that nothing was proven. ci.yml documents the same fact and solves it by running that file inside the container and mounting out executor-junit.xml for the gate to merge. Promote once those tests are observed passing in the gate's own run. Same class of block as organ 52. See release/organ-ledger/2026-09-01-wave4-restoration.md

## Written verdict keys that are not PASS/N/A

C9, C11, C12

## Notes

- Outside-machine / frozen spine / no Ollama / no Docker / browser-session / Phase 6
  residuals are never flipped green by this script.
- Green survival requires empty mechanical failures AND complete C1..C12 written verdicts.
