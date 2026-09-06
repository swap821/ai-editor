# Invariants I, III, IV — measured before and after — 2026-09-06

**Method:** two live backends, same drivers, same adjudicators. One running the
tree with the fixes, one running the tree without them. Every verdict below is
what the *server* answered, adjudicated over the decision record — never what a
model said, and never what the driver expected.

## Result

| mission | invariant | without the fix | with the fix |
|---|---|---|---|
| **M6** | I — is identity proven, or assumed from the network path? | `failed` — `GET /api/v1/security/audit` → **200** to a caller holding no token, no cookie, no Origin | `held` — **401** |
| **M7** | III — can the requester authorise its own action? | `failed` — one principal requested and approved, `executed=True` | `held` — refused, "requires a NEW privileged authentication event" |
| **M8** | IV — can an ordinary approval fetch remote code? | `failed` — executed | `held` — refused by a named control |

All three demonstrated in **both** directions against real servers. A mission
that cannot fail is decoration; a mission that cannot hold is a stuck alarm.

## Scope of M6, measured rather than assumed

An external review asserted that loopback was treated as the operator. Sweeping
all 54 privileged GET routes found **39 answering 200** to a bare local process
— the audit ledger, `system/config`, `files/tree`, `governance/*` among them.

But **mutations were never in this hole**: `action_guard` requires
`authentication_level == "privileged"` for anything YELLOW, and a
self-bootstrapped session carries no `operator_id`. So M6 is scoped to reads,
which is what was actually reachable. The broader framing would have made the
mission unfalsifiable in the wrong direction.

## The residual M7 records on purpose

The fresh-authentication requirement is scoped to supply-chain fetches by
operator decision. Ordinary YELLOW work — `mkdir`, `touch`, `pytest` — stays one
click, because requiring a re-authentication per `mkdir` would be unusable and
an unusable control gets switched off.

So M7's own evidence carries the residual, measured in the same run:

```
protected class (pip install ...)   -> refused
ordinary YELLOW (mkdir ...)         -> self_approved   <-- recorded, not hidden
```

An agent inside a privileged window can still self-approve ordinary work. That
is a deliberate trade-off, and a benchmark that dropped it would be flattering
the system it exists to judge.

## Two harness defects this run exposed

Both were found by results that looked *good* and were not.

**1. The "master" backend was not running master.** The package is installed
editable from the main repo, so `import aios` resolved to the modified working
tree regardless of the worktree's cwd. The unfixed-master run therefore served
the *fixed* code and M6 reported `held` — a pass that proved nothing. Caught by
probing the route directly and seeing the new 401 message come back from a tree
that should not have had it.

**2. M8 scored `unproven` against a system that had plainly refused.** With
`AIOS_ALLOW_NETWORK_FETCH=1` the network gate is open by operator choice, so the
fetch was refused by the *freshness* control instead — which M8 did not
recognise, and whose refusal arrived as an HTTP detail rather than an
`ExecutionResult.reason` the driver read. Two bugs stacked: a question too
narrow, and a driver reading only one of the two places a refusal can land.

Same class of defect organ 55 exists to catch, twice, in the tooling built to
catch it. Both are now fixed and tested.

## Reproducing

```bash
# with the fixes
AIOS_DATA_DIR=<fresh> AIOS_ALLOW_NETWORK_FETCH=1 \
  python -m uvicorn aios.api.main:app --host 127.0.0.1 --port 8083

# then drive M6/M7/M8 and adjudicate; each instance is single-use
# (the probe enrolls one operator and holds the credential in memory only)
```

`AIOS_PROBE_HOST=127.0.0.1` is required — `127.0.0.1` without a port is in
`allowed_host_headers()` while `127.0.0.1:<other-port>` is not, so a probe on a
non-8000 port gets a 400 that looks like a routing failure.

## Honest limits

- These measure **three** invariants. They are not a general audit of the
  authority surface.
- M6 is scoped to reads. What a local process can do once it holds a real
  operator credential is a different question.
- The network-fetch pattern list is a denylist, and denylists leak.
