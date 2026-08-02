# Phase 5 proof — Organ 33: Model Registry and Capability Passport

**Status under re-read:** `yellow`
**Survives mechanical adversarial re-read:** `no`
**Evaluated tip:** `5b74ffb24b3b3820676e7f8bc6e1bc06466456e0`
**Generated:** 2026-08-02T11:05:02+00:00

## Mechanical failures (enforceable subset)

- **residual**: no Ollama — live local-model / passport qualification evidence needs live Ollama in CI or self-hosted runner
- **residual**: C4: N/A-BY-DESIGN — passport fields are not a journal; aios/security/audit_logger.py::AuditLoggerAuthority and aios/application/local_workforce/provenance.py::ClerkProvenanceAuthority own the integrity chain

## Written verdict keys that are not PASS/N/A

C9, C11, C12

## Notes

- Outside-machine / frozen spine / no Ollama / no Docker / browser-session / Phase 6
  residuals are never flipped green by this script.
- Green survival requires empty mechanical failures AND complete C1..C12 written verdicts.
