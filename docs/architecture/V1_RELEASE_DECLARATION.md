# GAGOS v1 release declaration

The repository now exposes an evidence-backed declaration through:

```text
gagos v1-check
gagos v1-check --json
gagos v1-check --strict
```

The command reports the gates that are present in the checked-out source and
the gates that are unavailable in the current runtime. `--strict` exits
non-zero until every blocking gate is green. It never substitutes a synthetic
metric or a model claim for an operator, capability, executor, verification,
rollback, Cortex, mirror, memory, or emergency-control invariant.

The declaration is intentionally not a production-ready claim merely because
the source compiles. In this checkout the strict declaration remains blocked
when Docker is unavailable and when the required durable identity/capability
layers are not present. The Human Sovereign is the only authority allowed to
resolve those blockers.

Emergency stop is a separate durable latch in
`aios/application/governance/emergency_stop.py`. It persists before invoking
its five hooks, leaves the latch engaged if a hook fails, and requires a new
privileged authentication event to clear.
