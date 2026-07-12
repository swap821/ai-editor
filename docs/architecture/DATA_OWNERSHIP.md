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
- `AIOS_SWARM_CLOUD_BURST` controls worker swarm egress.
- Default: some tasks may route to cloud; operator may set to `""` for local-only.

## Privacy Boundaries

- Session IDs in cookies: `HttpOnly`.
- API tokens: required for non-loopback or when `TRUST_PROXY_HEADERS` is enabled.
- Proxy headers: only parsed when explicitly trusted.
- Body-session fallback: exists today; restricted in Slice 1 for production-sensitive routes.
