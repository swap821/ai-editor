# Daily reflexes, 2026-10-30: earned on more real modules, and still serving after a restart

The operator ran these himself, against his daily backend on :8000, which `tools/daily_backend.py up` (#558) had started on master `f6206755`. Every turn was bound to his work checkout `work/ai-editor` (at `cd5faf54`). Auto routing was local only, and the sandbox image was `aios-verify:83b20d9b8dbd`.

Each record is redacted: the operator's principal id is removed, nothing else changed, and the record carries the sha256 of its original. The script he ran is stored byte for byte as `prove_daily_reflexes.py.txt`; its versions are explained below.

## What was proven

| Record | What it shows | Result |
|---|---|---|
| `1_serve_gateway_after_restart.json` | The gateway reflex (playbook 17, earned 2026-10-29) still serves after the daily backend was restarted by the tool. One request: the reflex served it, the verify passed STRONG, no approval was asked, there were **zero model calls**, and the replay count went up by one. Before the turn, `daily_backend.py check` predicted it ready. | 8 of 8 PASS |
| `2_earn_failover.json` | A new reflex on a second real module, `tests/test_failover.py` (21 tests of `aios/core/failover.py`). It was learned on the live path, made review-ready, activated by him (signed), compiled into playbook 18, and served its request with **zero model calls**. | 12 of 12 PASS |
| `3_earn_privacy_filter.json` | The same for a third real module, `tests/test_privacy_filter.py` (58 tests of `aios/core/privacy_filter.py`), compiled into playbook 19. | 12 of 12 PASS |

Afterwards `tools/daily_backend.py check` reported 3 of 11 reflexes ready: playbooks 17, 18 and 19. The other 8 were learned under other scopes or never activated, and each is reported with its reason.

## What went wrong on the way (`stopped/`)

**1. The local model repeated a passing verify, and the loop guard stopped the turn.**
- Of 14 model-answered turns, **5 ended this way (36%)**.
- In each one, the verify of exactly the requested command passed STRONG, the model (`qwen2.5-coder:7b`) called the identical verify again, then a third time, and the agent-loop guard stopped the turn. The guard was correct.
- A turn that ends in an error earns the arc being learned nothing, so the operator had to run more turns.

**2. A defect, found because of 1.** The library still recorded each looping turn's tool sequence ("verify; verify") as a *successful* two-step arc.
- `arc-c46f6a5f…` (privacy filter) reached **review-ready** this way: 3 successes, 0 failures, every one from a turn the system itself stopped as a malfunction.
- `arc-40135bd8…` (failover) has 2.
- Neither was activated, and nothing becomes a reflex without the operator's activation, so no harm was done. But learning a procedure from a stopped turn is wrong. The fix is a separate PR.

**3. A bug in the script, which cost the operator three approvals** (`stopped/failover_b_wrong_arc_tracked.json`).
- `the_skill()` matched any procedure that *contained* the command, so it followed the two-step by-product instead of the arc being earned.
- It kept asking for turns after the real arc (`arc-79e8afb5…`) was already review-ready, after the first turn of that run.

## The script's versions

The committed bytes are the **last** version (sha256 `bfc828f1…`). It produced records 2 and 3, and the stopped privacy records. The two earlier versions differed only in the following:
- **The first version** produced record 1 and `stopped/failover_a_loop_after_2.json`. It reported any stopped turn as "did not end in a STRONG verified pass", which was misleading for a turn that passed and then looped.
- **The second version** produced `stopped/failover_b_wrong_arc_tracked.json`. It said what actually stopped the turn, but `the_skill()` still matched by "contains".
- **The last version** matches exactly the one-step procedure.

The serve-only path, which produced record 1, is the same in all three versions.
