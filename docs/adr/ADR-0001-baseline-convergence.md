# ADR-0001: Adopt GAGOS Sovereign Intelligence AI-OS V1.0 Baseline

**Status:** Accepted  
**Date:** 2026-07-12  
**Context:** The Master Convergence Directive supersedes the previous roadmap. It mandates 8 slices to transform the repository into a local-first sovereign agentic OS.

## Decision

Adopt the Master Convergence Directive as the authoritative roadmap. Freeze code changes until a verified baseline is established. Produce:
- `docs/architecture/NORTH_STAR_V1.md`
- `docs/architecture/CURRENT_RUNTIME_MAP.md`
- `docs/architecture/SUBSYSTEM_REGISTRY.md`
- `docs/architecture/AUTHORITY_MAP.md`
- `docs/architecture/DATA_OWNERSHIP.md`
- `.aios/state/PRODUCTION_CONVERGENCE_LEDGER.md`
- Updated `.aios/state/RESUME.md`

## Consequences

- All slices are gated by operator go before YELLOW code changes.
- The frozen security core (`aios/security/`) remains RED and follows §VIII.
- Future ADRs will be added under `docs/adr/` per slice.
