# Phase 5 proof — Organ 3: Secret Scanner

**Status under re-read:** `yellow`
**Survives mechanical adversarial re-read:** `no`
**Evaluated tip:** `14856c23e08b8b745c0d4ec4406f401d92fc05f0`
**Generated:** 2026-08-02T15:02:46+00:00

## Mechanical failures (enforceable subset)

- **residual**: frozen spine — section VIII controlled release, completed by an AUTHORIZED HUMAN, is required before green. Enforced in code by organ_ledger.FROZEN_SECURITY_ORGAN_IDS, not merely recorded here. Live read-only probe evidence IS now attached at the tip below; the sole outstanding item is the human approval, which is not delegable to the agent that produced the evidence.
- **residual**: C4: N/A-BY-DESIGN — aios/security/secret_scanner.py::SecretScannerAuthority.scan_and_redact

## Written verdict keys that are not PASS/N/A

C9

## Notes

- Outside-machine / frozen spine / no Ollama / no Docker / browser-session / Phase 6
  residuals are never flipped green by this script.
- Green survival requires empty mechanical failures AND complete C1..C12 written verdicts.
