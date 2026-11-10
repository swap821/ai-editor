# DATA_OWNERSHIP

## Ownership Model

- **Operator owns all data.** The AI-OS is a steward, not a proprietor.
- **Local-first storage.** Canonical state lives on disk in `.aios/` and product memory stores.
- **Egress is opt-in.** Cloud providers may only be used when explicit policy allows it.
- **Audit trail belongs to the operator.** Logs are append-only and tamper-evident.

## Data Stores

| Store | Path | Owner | Persistence | Notes |
|-------|------|-------|-------------|-------|
| Builder notebook | `.aios/` | operator | durable | continuity + lessons + plans |
| Resume manifest | `.aios/state/RESUME.md` | operator | durable | live handoff state |
| Experiences | `.aios/memory/experiences.jsonl` | operator | durable | append-only |
| Mistakes | `.aios/memory/mistakes.jsonl` | operator | durable | append-only |
| Warnings | `.aios/memory/warnings.md` | operator | durable | loud patterns |
| Coordination | `.aios/state/coordination.db` | operator | local-only | agent lease control plane |
| Product memory | `aios/memory/` (runtime) | operator | durable | product memory engine |
| Config secrets | env vars only | operator | volatile | never persisted to disk |

## Egress Policy

- `AIOS_ROUTER_CLOUD_TASKS` controls which task classes may leave the machine.
- The runtime profile's `swarm_cloud_burst`, with the egress law, controls worker swarm egress (`AIOS_SWARM_CLOUD_BURST` retired 2026-11-10).
- `AIOS_CLOUD_MONTHLY_USD` bounds every metered cloud call; `<data>/cloud_spend/<UTC month>.jsonl` (owner `aios/core/cloud_spend.py`) records each call's tokens and estimated cost, no prompt or output.
- Default: some tasks may route to cloud; operator may set to `""` for local-only.

## Privacy Boundaries

- Session IDs in cookies: `HttpOnly`.
- API tokens: required for non-loopback or when `TRUST_PROXY_HEADERS` is enabled.
- Proxy headers: only parsed when explicitly trusted.
- Body-session fallback: exists today; restricted in Slice 1 for production-sensitive routes.
