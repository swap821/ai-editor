# The last thirteen — 53 green / 1 yellow

**Date:** 2026-09-02
**Result: 41 green / 13 yellow → 53 green / 1 yellow.**

The thirteen organs left after four restoration waves were the ones that were
*not* citation work. Each needed something different, and two of them turned out
to be real defects the ledger had been concealing behind prose.

Only **organ 44** remains yellow. It is not agent-reachable.

## What each organ actually needed

| Work | Organs |
| --- | --- |
| Gate could not express the proof | 20, 48, 49, 51 |
| Untested production behaviour — new tests | 13, 14, 54 |
| N/A was true; the stated *reason* was fabricated | 6, 34 |
| Production code — genuine defects | 12, 53 |
| A Docker-capable run | 40, 52 |
| Operator-only | 44 |

## The security defect: organ 53

The API-token rotation row — `current_token_digest` / `previous_token_digest` —
**is** the credential material gating the entire API surface, and it was stored
as a bare `INSERT ... ON CONFLICT DO UPDATE` with no integrity of any kind.
Anyone able to write that SQLite file could install the digest of a token they
held and authenticate as the operator, **with nothing able to detect it**. The
rotation route does write an audit entry, but it records only *that* a rotation
happened, does not bind the resulting digest, and is bypassed entirely by editing
the file directly.

Every row is now stamped with HMAC-SHA256 over its own contents, keyed from
`AIOS_API_TOKEN_ROTATION_KEY`, which lives only in the environment (AGENTS.md
§VII.4). Verified on every read.

**The failure posture is deliberate and asymmetric.** An unverifiable row —
tampered, unstamped, or unkeyed — is treated as *no rotation state*: rotated
tokens stop authenticating, and `config.API_TOKEN` is untouched. Refusing
everything instead would let an attacker lock the operator out of their own API
by corrupting one file. As built, tampering can only ever **remove** access,
never grant it. `test_tampering_removes_access_but_never_grants_it` pins that.

**Mutation-checked:** with HMAC verification disabled,
`test_a_directly_rewritten_digest_does_not_authenticate` fails — the forged
token gets in. That is the vulnerability demonstrated and the fix demonstrated to
close it.

Two operational consequences: rotated tokens now require the key to be set (≥32
chars) or they stop authenticating — `config.API_TOKEN` is unaffected, so this
cannot lock anyone out; and pre-existing rows carry a NULL tag and are refused as
unverifiable, because trusting them would leave every existing deployment exactly
as forgeable as before.

## The wiring defect: organ 12

`WorkerFoundryAuthority` has always accepted a `bus=`, `_set_state` has always
appended a `CanonicalEvent` to it, and `CouncilOrchestrator` has always passed one
in production. `aios/api/deps.py::get_worker_foundry` did not — so the
FastAPI-facing singleton silently dropped every worker admission and lifecycle
transition on restart while a parallel production path kept them. One organ, two
production paths, one durable.

N/A-BY-DESIGN would have recorded that inconsistency as a design decision. The
seam is now wired, and mutation-checked: remove the argument and the test fails.

## The gate could not express four organs' proofs

Organs 20, 48, 49 and 51 were **unciteable by construction**. Their tests are
vitest `it('...')` with human-readable names — every one contains spaces — and
the referent pattern admitted only `[\w\[\]\-]+` after `::`.

The failure mode was worse than rejection: it **silently truncated**. Citing
`…livingMirrorRegistry.test.ts::rejects malformed known events…` matched the path,
captured only `rejects`, passed the "a referent is named" check, and then failed
execution-matching against a test nobody wrote.

Two mechanically-linked changes in `scripts/verify_organ_twelve_conditions.py`:

* the pattern now also accepts a quoted name, with the alternation **inside**
  group 2 — three call sites unpack 2-tuples and a third group would turn each
  into `ValueError: too many values to unpack`. A `_proof_citations()` helper
  unquotes at every site so the loop bodies are untouched.
* `_proof_ran_and_passed` now also matches on the final `" > "` segment. vitest
  folds enclosing `describe` blocks into the JUnit name, so a citation naming the
  leaf could never match exactly. Segment matching keeps the existing
  sibling-safety: the cited name must equal the whole final segment.

**This does not lower the bar**, and the suite proves it: an *unquoted* spaced
citation still truncates and is still refused, a failing vitest case still vetoes
its citation, and a longer sibling still cannot launder one.

## Two organs whose prose was false, not merely thin

* **Organ 6** — its C4 claimed reliance on "audit + token-rotation stores".
  `edge_security.py` never imports the audit logger, and organ 53's row had no
  chain to rely on. `EdgeTrustAuthority` has no `__init__` and zero `self.x =`
  assignments, so N/A is genuinely true — but the claim was withdrawn and
  re-anchored to the class itself rather than restated.
* **Organ 34** — genuinely in-memory, and its own module docstring says so
  ("not a new durability promise this slice doesn't back"). N/A is honest here.

## Three pieces of new test authoring

* **Organ 54** — `verify_backup` re-hashes every archive member and raises on a
  mismatch; nothing exercised it. The test rebuilds the archive with altered bytes
  while keeping the **original manifest**, so the manifest still lists the old
  digest — tampering the way an attacker must, rather than editing both sides and
  checking that two attacker-controlled values agree.
* **Organ 13** — `execute_registered_operation_in_service` verifies digests and
  refuses before mutating, and no test called it. A **twin** in
  `aios/application/executor/service.py` with the same op-id and argv shape but
  different semantics is what the existing tests exercised, which is why this
  looked covered.
* **Organ 14** — `for_mission()` promises the lease "including after restart" via
  an on-disk fallback, but short-circuits on its in-memory cache, so every
  existing test answered from the cache and the glob never ran. A second
  authority over the same root is the restart.

All three mutation-checked in both directions.

## Organs 40 and 52 — run, not inferred

Deferred three times for want of a Docker daemon. Docker Desktop was installed
all along; the daemon simply was not running. Started it, and both suites pass
locally: `tests/test_executor_integration.py` 4 passed,
`tests/test_container_containment_integration.py` 4 passed.

Four environment obstacles, none of them product defects, all worth recording
because they will recur on this machine:

1. MSYS rewrote `-e AIOS_EXECUTOR_WORKSPACE_ROOT=/workspace/jobs` into
   `C:/Program Files/Git/workspace/jobs` — fixed with `MSYS_NO_PATHCONV=1`.
2. MSYS also rewrites **exported environment variables** when launching native
   Windows Python, so `AIOS_EXECUTOR_REMOTE_WORKSPACE_ROOT` was mangled the same
   way. Fixed by setting it from PowerShell instead.
3. The executor runs as `nobody` and could not reach the mounted Docker socket.
   Docker Desktop's socket is `root:root` mode 660, so `--group-add 0` is the
   local equivalent of compose's `AIOS_DOCKER_SOCKET_GID`.
4. The workspace must be bind-mounted with a Windows-style source while the
   in-container root stays POSIX.

## Verification

```
$ python -m aios.launcher organ-check --strict
GAGOS organ ledger: 53/54 green (CONFORMANT)
  no ledger violations

$ python scripts/verify_organ_contracts.py
no contract violations -- ledger and manifest are self-consistent

$ python scripts/verify_organ_twelve_conditions.py --enforce-condition-proofs \
    --frontend-junit frontend/vitest-junit.xml     # with live executor + Docker
running 131 referenced test file(s) for C6/C7/C9 ...
merged 116 file result(s) from frontend\vitest-junit.xml
test outcomes: 247 file(s), 3498 passed, 0 failed
C3/C4/C5 greens without a mechanical proof: 0
green mechanical failures: 0
```

Note this run needed **no** `--allow-unexecuted-frontend`: the frontend suites
were genuinely executed and merged, rather than excused.

## What remains: organ 44

Golden Mission and Endurance Evaluation needs a cohort run against a live cloud
model, and 4 of its 5 evidence rows are `OPERATOR-ATTESTED` — the operator's own
observation, which no agent can supply. Under the narrowed flag definition its
`requires_live_evidence` is honestly **true**, so it stays yellow rather than
being talked into green.

Organs 1, 4 and 5 remain green on the operator's signed spine attestation rather
than on evidence current at this commit. Re-attesting is operator-only
(`spine_release_attest.py sign` refuses on non-TTY stdout and needs a key that
must never enter an agent context). **The count that rests purely on
mechanically re-executed evidence is therefore 50, not 53.**
