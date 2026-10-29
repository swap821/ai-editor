# Phase 5 proof — Organ 40: Isolated Workspace and Executor (live proof)

**Status under re-read:** `yellow`
**Survives mechanical adversarial re-read:** `no`
**Evaluated tip:** `9408fd03e2697d5142c05d9ef993aa92337343ff`
**Generated:** 2026-10-29T05:20:56+00:00

## Mechanical failures (enforceable subset)

- **residual**: Evidence currency (6ff5410b2b39): UI entrypoint frontend/src/workbench/SovereignStatePanel.jsx changed by this PR. The Phase 4 live run at cc8492f314eb that proved this organ no longer claims it (organ 40 is absent from the current runner's proof set), so the evidence cannot be refreshed by re-running it. Re-earn via the executor live path at a current tip to restore green.

## Written verdict keys that are not PASS/N/A

C8

## Notes

- Outside-machine / frozen spine / no Ollama / no Docker / browser-session / Phase 6
  residuals are never flipped green by this script.
- Green survival requires empty mechanical failures AND complete C1..C12 written verdicts.
