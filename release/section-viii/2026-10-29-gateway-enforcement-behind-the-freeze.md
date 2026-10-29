# §VIII authorization: the one-gateway switch behind the freeze

**Authorized by the operator in-session on 2026-10-29.**
- PR #552 listed as still open: "The off switch, `AIOS_GATEWAY_ENFORCE=0`, sits
  outside the frozen security code. Moving it behind the freeze would be a
  proposal for you to make." He answered: "Honestly fix this".
- The `limits.py` edit was applied. Writing this record was then denied by the
  session's safety classifier, and the agent stopped and asked. He chose
  "I'll allow it".

## Frozen paths changed under this authorization

- `aios/security/limits.py`

Named verbatim because `scripts/check_frozen_core.py` requires it.

## Observe

PR #552 made `aios/core/model_calls.py` refuse a production model call that
passed no Organ 32 entrance, before it leaves (docs/ONE_GATEWAY.md,
"2026-10-29"). Three values decide whether that happens:

| Value | What it governs |
| --- | --- |
| `AIOS_GATEWAY_ENFORCE` | whether refusing is on at all |
| the unjudged sites, `tools/` and `tests/` | whose calls are a measurement tool's own, never judged or refused |
| the exempt programs, `tools/` and `scripts/` | whose own process does not refuse unless asked |

All three were defined outside the freeze: the switch in `aios/config.py`, the
two lists in `aios/core/model_calls.py`. So an agent with ordinary edit rights
could make "every model call through the one gateway" false again without
ceremony, by changing the switch's default or by adding `aios/` to either
list.

That is the exact gap `aios/security/limits.py` was created to close for
`SCOPE_ROOTS` and `ROUTER_CLOUD_TASKS`
(`release/section-viii/2026-08-31-guardrail-limits-authorization.md`).
Whether a model call may leave without passing the gateway decides what may
leave the machine. It belongs with them.

## Analyse

- **The switch:** a tri-state in `limits.py`.
  - Unset means refuse everywhere except in an exempt program's own process.
  - A clear yes means refuse there too. A clear no means record only.
  - **An unrecognised value is unset, never "off"**, as `_env_int` already fails
    to its default: a typo must not turn a guard off.
- **The two lists:** `GATEWAY_UNJUDGED_SITES` and `GATEWAY_EXEMPT_PROGRAMS`.
- **`aios/config.py` only re-exports the three**, as it does every guardrail.
  `tests/test_guardrail_limits.py` now pins them, so a re-inlining fails.
- **The adversarial re-read of organ 32, in the same change**, found that the
  rule "a call from `tools/` is a tool's own" looked only at the innermost
  frame.
  - So production code could pass a call off as a tool's by reaching the model
    through a `tools/` helper.
  - No live path did this. The only production import from `tools/` is a data
    class, `GovernanceObservation`.
  - Now a call is production if ANY frame on its stack is, read in full and not
    cut at the 12 frames a record keeps.
  - The same re-read found that `<frozen runpy>`-style pseudo-filenames resolved
    as repo frames. They are now no frame at all.
- **Not moved:** the code that applies the values, `observe()` raising
  `UngatedModelCall`, stays in `aios/core/model_calls.py`. That matches every
  other guardrail, whose consumers are not frozen either. It is pinned by
  `tests/test_gateway_enforcement.py`.

## Test

- **`tests/test_guardrail_limits.py`:**
  - the three names are in `GUARDRAILS`, so each must be defined in `limits.py`
    and only re-exported by config;
  - `test_the_gateway_switch_turns_off_only_on_a_clear_no` covers unset, yes,
    no, and the typos `O` and `disable`, both of which stay on.
- **`tests/test_gateway_enforcement.py`:**
  - `test_the_switch_and_its_exemptions_are_defined_behind_the_freeze`;
  - `test_a_call_cannot_be_laundered_through_a_tools_helper`: production frame,
    then a `tools/` frame, then the adapter, and the call is refused;
  - the existing refusal and exemption tests, now on the frozen values.

## Verify

- `python scripts/check_frozen_core.py --base origin/master` names
  `aios/security/limits.py` as authorized by this record.
- The full backend suite runs with refusing on (it is the default in pytest).
- **Boot attestation:** this changes the spine's Merkle hash. The first boot
  after it logs `TAMPERED` once against the previous entry, then `valid`. This
  record is why.
- **Organs 1-5:** `limits.py` is not an entrypoint of any organ, so their
  evidence and the operator's spine-release signature are untouched.
