# Phase 5 proof — Organ 33: Model Registry and Capability Passport

**Status under re-read:** `yellow`
**Survives mechanical adversarial re-read:** `no`
**Evaluated tip:** `0295141c1969be1f70ced5de144fd7c83edb46fc`
**Generated:** 2026-08-01T16:40:02+00:00

## Mechanical failures (enforceable subset)

- **residual**: no Ollama — live local-model / passport qualification evidence needs live Ollama in CI or self-hosted runner
- **residual**: C4: N/A-BY-DESIGN — passport fields are not a journal; aios/security/audit_logger.py::AuditLoggerAuthority and aios/application/local_workforce/provenance.py::ClerkProvenanceAuthority own the integrity chain

## Written verdict keys that are not PASS/N/A

C9, C11, C12

## Notes

- Outside-machine / frozen spine / no Ollama / no Docker / browser-session / Phase 6
  residuals are never flipped green by this script.
- Green survival requires empty mechanical failures AND complete C1..C12 written verdicts.
