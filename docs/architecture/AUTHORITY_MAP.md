# AUTHORITY_MAP

## Authority Principles

1. The **Policy Kernel** is the single authority over what can be done.
2. Every action has a **scope** (file path, command, network host, etc.).
3. Every action has a **zone**: GREEN (read/analyze), YELLOW (mutate), RED (dangerous).
4. No route, tool, or agent performs YELLOW/RED without kernel approval + audit.

## Current Authority Distribution

| Capability | Current Gate | Future Gate (Slice 2+) | Notes |
|------------|--------------|------------------------|-------|
| Read code/memory | `require_api_token` + route auth | Policy Kernel GREEN | mostly unchanged |
| Edit files | `actions.py` + `security/gateway.py` | Policy Kernel YELLOW | approval flow exists |
| Execute commands | `actions.py` + gateway + approval | Policy Kernel YELLOW/RED | subprocess currently |
| Network egress | config + router flags | Policy Kernel RED | cloud routing gated |
| Spawn workers | Worker Foundry admission (`aios/application/workers/foundry.py`) + emergency stop | unchanged | since 2026-11-09 the swarm's caste legs too (`swarm_foundry.py`); a swarm leg's cloud burst obeys the same egress law as the router; since 2026-11-10 GAGOS's workshop writers too (`workshop_foundry.py`), each batch's files claimed durably first |
| Secret handling | `secret_scanner.py` | frozen core | never weaken |
| Self-modification | `scope_lock.py` + frozen core | T4 RED + human review | §VIII process |
| A GAGOS proposal reaching master | its sandbox tests, then Claude Code's review, then the operator's merge | unchanged | since 2026-11-10 the council's Critique queen pre-screens each tested proposal; advisory, it grants and refuses nothing |
| A metered cloud call | `model_calls.observe` (every adapter) | unchanged | since 2026-11-10 refused once the month's recorded spend reaches `AIOS_CLOUD_MONTHLY_USD` (`aios/core/cloud_spend.py`) |

## Route Authority Matrix

| Route | Zone | Approval | Audit |
|-------|------|----------|-------|
| `GET /api/health` | GREEN | no | no |
| `POST /api/auth/session` | GREEN | no | yes |
| `POST /api/actions/approve` | YELLOW | yes | yes |
| `POST /api/actions/execute` | YELLOW/RED | yes | yes |
| `POST /api/actions/rollback` | YELLOW | yes | yes |
| `POST /api/council/deliberate` | GREEN/YELLOW | context | yes |

## Frozen Core (Tier T4)

Modules in `aios/security/` are frozen. Any change follows the full §VIII controlled-self-modification flow and is classified RED.

- `aios/security/gateway.py`
- `aios/security/scope_lock.py`
- `aios/security/secret_scanner.py`
- `aios/security/audit_logger.py`
- `aios/security/injection_shield.py`
