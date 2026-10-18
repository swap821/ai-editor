# Proposal: a `clerical` cloud-egress class, for the cloud clerk only when needed

> **APPLIED 2026-10-18** as proposed (one name added to `_VALID_ROUTER_TASKS`; in
> no default). The cloud-clerk escalation it describes is NOT built. Record:
> `release/section-viii/2026-10-18-scope-b-and-clerical-egress.md`. The text below
> is the proposal as written on 2026-10-12.

**Status: Propose. It awaits the operator's Human Review → Approve.**
- Written 2026-10-12 by the coding agent.
- `aios/security/limits.py` is frozen (AGENTS.md §VIII). The agent cannot apply
  this; only the operator can.
- Nothing here takes effect by itself. It only makes an opt-in *possible*.

## What the operator asked for

On 2026-10-12 the operator asked for three roles:
- **the local clerk** as the main clerk, always first;
- **a powerful cloud clerk,** "only when needed high quality … to honestly help
  main local clerk";
- **several cloud models as teachers.**

## Observe

**Clerk work is never allowed to leave the machine today.**
- What may leave is the set of router task classes in `aios/security/limits.py`:
  `_VALID_ROUTER_TASKS = {coding, reasoning, research, vision, long_context}`.
- The operator chooses from that set with `AIOS_ROUTER_CLOUD_TASKS`, which he
  sets in his own environment; `.env` is ignored for guardrails.
- `build_constitution()` takes the same value, so the constitution and the
  router agree (the one law).
- No class names clerical work, so clerk work can never be cloud-eligible.
  That is correct for today.

**The clerk's "frontier escalation" does not run anything.**
`LocalWorkforceService.run_advisory_job` returns `rejected — "Dispatched to
frontier_escalation"`. No cloud model ever does the job.

## Propose

Add one class name to the frozen set:

```diff
 _VALID_ROUTER_TASKS: Final[frozenset[str]] = frozenset(
-    {"coding", "reasoning", "research", "vision", "long_context"}
+    {"coding", "reasoning", "research", "vision", "long_context", "clerical"}
 )
```

**Effect when applied: none, until the operator opts in.**
- `ROUTER_CLOUD_TASKS` still defaults to empty.
- The operator's current setting, `reasoning,coding`, does not include it.
- To allow it, the operator adds `clerical` to his own environment variable
  (for example `reasoning,coding,clerical`).
- A typo is still dropped rather than accepted.

## How the cloud clerk would use it (product code, not frozen; built separately)

It is used only when needed, and always after the local clerk:
1. **Only for weak job profiles:** profiles the clerk benchmark measures as
   weak for the local clerk (`tools/clerk_benchmark.py`). It is a named
   per-profile list, not "everything".
2. **Only after a failure:** when the local clerk's answer fails validation on
   a specific job.
3. **Only when the constitution allows it:** every escalation first checks
   `constitution.allows("clerical")`. Refused means the job stays rejected, as
   today.
4. **Safeguards on every call:**
   - it sends the job's `redacted_payload`;
   - it passes the Bedrock privacy filter;
   - it is recorded in the model-call ledger.

**Teaching and judging need none of this.** They run on synthetic jobs (the
clerk benchmark, practice), so no operator data is sent.

## Alternatives considered

- **Keep the clerk local-only.** The cloud model then teaches and judges on
  synthetic jobs only. This works today without this proposal; what is lost is
  live high-quality help on the operator's real jobs.
- **Send clerk escalations under the `reasoning` class.** Rejected: the egress
  would be mislabelled, and clerk data would leave the machine under a name
  that says something else. That defeats the point of the per-class ceiling.

## Test plan (when applied)

1. **The class is opt-in.** `_env_router_tasks("X", ())` with `X=clerical` gives
   `("clerical",)`, and the default stays `()`.
2. **The existing guardrail tests are unchanged.**
   `tests/test_guardrails_ignore_dotenv.py` still passes: `clerical` in `.env`
   still does nothing.
3. **Every existing egress test still passes.** The new class appears in no
   default, so nothing that is local today becomes cloud-eligible.
4. **The frozen-core check records the change.** `scripts/check_frozen_core.py`
   sees the edit as an operator-approved change, and that approval is what this
   document records.

## Risks

- **Clerk jobs carry operator content:** logs, tickets, records. With the
  class enabled, the escalated ones leave the machine.
- **Mitigations:**
  - it is off by default;
  - it covers only the named weak profiles;
  - the payload is redacted, privacy-filtered and recorded in the ledger;
  - it is revocable by removing `clerical` from the environment variable.
