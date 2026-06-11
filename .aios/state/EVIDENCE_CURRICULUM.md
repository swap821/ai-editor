# Curriculum Evidence Run — 2026-06-11

First live exercise of the brain-growth loop: a human-reviewed curriculum run
through the REAL supervised chat loop (`POST /api/generate`) against local
Ollama (auto-routed, qwen2.5-coder:7b for these tasks), with verifier-backed
progression, skill promotion, and the Slice 1 (e773768) foraging reward
live-proven at the end. Operator approved the task set and the delegated
approval model before the run.

Raw record: `.aios/audit/curriculum-evidence-run.jsonl` (every frame, approval,
diff, rejection, and curriculum diff). Runtime truth: `data/aios_memory.db`.
Audit chain after the run: **valid, 182 entries, unbroken**
(`GET /api/v1/audit/verify`, head d0ce65b4…).

## Method

- Curriculum: `curriculum_seed.json` — skill `python-tdd-basics`, 2 levels x
  (2 training + 1 held-out), each task = create module -> create pytest test ->
  verify. Seeded via `POST /api/v1/development/curriculum` (never executes).
- Driver: `curriculum_evidence_driver.py` — sends each prompt VERBATIM as a
  chat turn, replays through approval tokens exactly like the UI, and acts as
  the operator's delegate with a hard fail-closed allowlist: only `.py` files
  directly inside `training_ground/`, only pytest-on-sandbox verify commands.
  Two out-of-allowlist actions were rejected live (`pip install pytest`, and a
  bare `pytest -q` before the allowlist was widened to permit it) — both
  rejections audited, both runs aborted fail-closed.
- Each attempt starts from a clean sandbox slate (task files deleted, logged);
  lesson transfer between attempts can therefore come ONLY from the product's
  own memory (mistake recall, semantic recall) or durable sandbox artifacts.
- Backend: venv uvicorn, `AIOS_INTERPRET_ALIGNMENT=false` (documented RAM
  lever; also removes ask-pause nondeterminism on fixed prompts). All other
  flags default.

## Outcome — the numbers

| Brain artifact | Before | After |
|---|---|---|
| curriculum_tasks | 0 | 6 — **all mastered** (both held-out gates passed) |
| procedural_skills | 0 | 10 (1 **verified**: id=10, 3/3 successes) |
| development_events | 6 | 78 (9 verified_success / 7 verified_failure / 52 paused / 10 unverified) |
| mistake_pool | 3 | 8 (incl. root-caused ModuleNotFound + PathNotFound lessons) |
| episodic_memory | 629 | 721 |
| semantic_memory | 40 | 52 |

Progression mechanics observed live: level 1 mastery flipped level 2 tasks
`locked -> available`; mastery required exactly the designed gate (2 training
passes + full coverage + held-out pass); mastered tasks stopped accumulating
evidence; the ambiguity/verbatim-match rules held.

Slice 1 live proof (`POST /api/v1/plan` on the proof goal): 3 calibrations with
`skill_adjustment = 0.2` — the SKILL_CONFIDENCE_BONUS_MAX cap binding — and
`skill_ids = [10]`. The pheromone trail laid by this run rewards matching
planner steps, capped below the human gate, exactly as committed in e773768.

## The growth story (the part that matters)

L1-T1 (`shout`) took 5 counted attempts. The failures were real and the system
learned through them:

1. The model mirrored the prompt's path into a package-style import
   (`from training_ground.text_utils import …`) which fails under the
   verifier's sandbox cwd; attempts 1–4 were verified_failure.
2. Within attempts the loop self-corrected (verify -> reflect -> fix -> PASS),
   and the reflection agent root-caused the failure correctly into the mistake
   pool ("unable to find the 'training_ground' module").
3. **L1-H1 (held-out, never seen) passed clean on the first try** — the model
   wrote the correct plain import immediately after the T1/T2 fail->fix cycles
   seeded memory. Same again later: L2-H1 passed on attempt 2 after a
   non-import test bug on attempt 1.
4. In L2-T1 the agent invented a durable environmental fix — creating
   `training_ground/__init__.py` so its natural import style works (stigmergy:
   the lesson embodied in the environment). The approved grant was dropped by
   replay mechanics (see gaps); the delegate applied the byte-identical
   approved content later, after verifying both import styles pass (7/7
   sandbox tests). L2-T2 then passed first-try.
5. Skill ecology: flail arcs remain `candidate` (e.g. 1 ok / 3 fail); only the
   clean 2-step arc accumulated 3/3 and was promoted `verified` — the
   promotion gate filtered messy workflows out, as designed.

## Product gaps found and fixed (each test-covered; suite 408 passed / 1 skipped, baseline 400/1)

1. `tool_agent._extract_text_tool_calls`: local models emit tool calls as
   prose in three shapes the rescue missed — multiple fenced JSON blocks,
   `parameters`-keyed args (llama3.1), and bare back-to-back unfenced JSON
   objects. Now recovers the FIRST allowlisted call per message (one-call-at-
   a-time protocol preserved).
2. `tool_agent._create_file`: not replay-tolerant — the resumable approval
   flow re-runs the whole turn, and the re-issued create of an already-landed
   file dead-ended the loop. Byte-identical content is now a no-op success.
3. `executor._default_runner`: on Windows, CreateProcess resolves a bare
   `python` from the parent exe's directory (the BASE interpreter under a venv
   launcher) and the writable sandbox cwd BEFORE the child PATH — so the venv
   prepend in `_sanitise_env` was silently ignored (and a sandbox-planted
   binary could shadow the interpreter: latent security hole). Bare names now
   resolve through the sanitised PATH via `shutil.which`.
4. Turn outcome classification (`main.py`): was FAIL-dominant — a turn that
   failed, self-corrected, and ended `[VERIFY PASS]` still counted as
   verified_failure, making any task that needs the loop's own verify->fix
   design unmasterable. **Operator decision 2026-06-11: last evidence wins**
   (final verdict = turn outcome). Follow-up noted in code: make it per-target.

## Honest limitations

- Approvals were operator-delegated to the driver's allowlist, not human-
  clicked per action (operator explicitly approved this model; every grant +
  diff is in the audit log). One UI-equivalent manual run would strengthen the
  claim.
- One model family exercised (auto -> qwen2.5-coder:7b; llama3.1:8b tried once
  pre-fix). The alignment interpreter was off for the run.
- The first L1-T1 curriculum success required the classification change —
  under strict FAIL-dominance this model class cannot master even level 1.
  That negative result stands on its own and is preserved in the log.
- Skill signatures fragment across arc shapes (goal+steps hash); reinforcement
  needed identical clean arcs. Trail consolidation across near-identical arcs
  is an open design question.
- `record_matching` failures stay silent in the chat loop (only the driver's
  post-turn poll catches them); the driver's "no increment" warning also fires
  cosmetically on mastered tasks.
- Replay mechanics can drop an approved-but-not-re-issued grant (the
  `__init__.py` case): grants only apply when the model re-calls the tool on
  the replayed turn. Follow-up: pre-apply granted writes on resume, or surface
  dropped grants.

## Reproduce / inspect

- State: `.venv\Scripts\python curriculum_evidence_driver.py status`
- Curriculum API: `GET /api/v1/development/curriculum` · skills:
  `GET /api/v1/development/skills` · metrics: `GET /api/v1/development/metrics`
- Planner proof: `.venv\Scripts\python curriculum_evidence_driver.py plan-proof`
- Full frame log: `.aios/audit/curriculum-evidence-run.jsonl`

---

# Trail Mechanics — same day, second slice (2026-06-11 evening)

Stigmergy completion slices 1-3 (reinforcement-on-reuse, negative pheromone,
trail consolidation), designed by a 3-lens judge panel (ant-fidelity /
evidence-integrity / minimal-diff; the evidence-integrity design won with
grafts — the judge empirically falsified the run-length-collapse rule against
this DB before any code was written) and live-proven immediately after:

- **Migration on the live DB**: predicted no-op, observed no-op — all 10 rows
  backfilled with `signature_v2`, zero merges, id=10 still verified 3/0,
  every count byte-identical. (Backup at `data/backup-pre-trail-mechanics/`.)
- **Negative pheromone, live**: a novel echo_utils prompt recalled trail
  id=10; the turn flailed (verify-before-create) and ended verified_failure →
  id=10 took `reuse_failure_count=1`; direct counts and verified status
  untouched. The flail arc was honestly recorded as candidate id=11 (0/1).
- **Reinforcement-on-reuse, live**: the retry succeeded cleanly →
  id=10 `reuse_success_count=1`; the novel clean arc minted candidate id=12.
- **Planner unchanged**: plan-proof still returns skill_adjustment=0.2 (cap
  binding), skill_ids=[10].

Mechanics (all env-tunable, see config.py): trail identity is now the
arc-level `signature_v2` (goal tokens + argument-stripped tool sequence) so
redaction noise reinforces ONE trail; ranking strength becomes
`min(1.0, success_rate * freshness * reuse_factor)` where `reuse_factor` is a
saturating, asymmetric (~7:1 failure:success), floored multiplier from reuse
counters; reuse failures never refresh the evaporation clock; 3 net reuse
failures quarantine a verified trail (recovery = fresh direct verified
success); promotion stays direct-evidence-only and the 0.2 planner cap and
0.72 human gate are byte-identical. Suite: **423 passed, 1 skipped**
(15 new behavioral tests incl. old-schema migration fixtures).

Known follow-ups: per-target outcome classification, dropped-grant replay
fix, quarantine watermark if rank-thrashing is observed, lambda tuning.
