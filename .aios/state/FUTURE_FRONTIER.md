# FUTURE_FRONTIER.md — The North Star

> **Authored by the chief synthesizer, 2026-06-13.** Closing document of a futurist
> advisory: a lead CALIBRE assessment + eight specialist lenses, synthesized into one
> honest north star. This is the **multi-year vision above `PLAN.md`** — it does NOT
> replace it. `PLAN.md` (2026-06-13) is the single source of truth for *what is next*
> (Tier 0 hygiene → Tier 1 the three gaps → Tier 2 surplus maturation). This document
> answers a different question: *what makes this genuinely first-of-its-kind, and what
> are the futuristic moves that put it "in prime" after the grind.*
>
> **Invariants honored throughout (a proposal that violates one is a non-starter, and
> is named as such):** (1) evidence-over-model is absolute; (2) RED is ALWAYS refused,
> even after human approval; (3) supervised — human authority is never removed, only the
> gated GREEN surface widens via earned, revocable, RED-un-earnable autonomy; (4)
> local-first / single-operator / privacy by default; (5) the audit chain + frozen
> security core are sacrosanct; (6) the superbrain UI is polished by micro-detailing,
> **never** redesigned (FIDELITY IS SACRED).
>
> **Honesty standard:** the operator's bar — pursue the frontier, report at ~90%, never
> oversell. Every move below grounds in a *real* seed already in this tree (named with
> its file), is rated for feasibility, and carries its honest risk.

---

## 1. Executive thesis — the first-of-its-kind claim

This system creates a category: the **evidence-locked supervised personal AI-OS** — a
weak local model *proposes*, but deterministic, tested, SHA-256 hash-chain-audited
machinery *decides*, and that single invariant ("trust the evidence, not the model") is
carried without compromise through security, cognition, memory, learning,
self-modification, autonomy, **and** the interface. What is genuinely novel is the fusion
of three things that almost never appear together in one running system: (a) a
**fail-closed deterministic cage the LLM cannot reason past** — an allowlist GREEN
surface, RED-by-default, RED refused *even after the operator's own one-click approval*
(`aios/core/executor.py:436-443`); (b) an **earned, revocable, RED-un-earnable autonomy
bridge** graduated by the *same verifier-evidence pheromone math* the system uses to learn
skills, not by model confidence (`aios/core/autonomy.py`); and (c) a **living-mind 3D
interface that is a faithful real-data read-out of that cage** — a face that cannot lie
because it is wired to the same SSE frames the backend emits and goes honestly dormant
when there is no data (`frontend/src/superbrain/lib/cognitionBus.ts`,
`aiosAdapter.test.ts`, `soundEngine.test.ts`). The honest moat is **not** intelligence and
**not** features — it is the *finished discipline*: the evidence-locked, fail-closed,
audited, structurally-un-self-approving core is the unglamorous part almost no team ever
completes, and it is already built and under behavior-level test (512 passing, 90% line
coverage of `aios/`). The seed is real, not aspirational.

---

## 2. The calibre we are building on — what is genuinely world-class today

So that the vision is grounded and not fantasy, here is what is *verified in source* and
under test right now:

- **A fail-closed deterministic kernel.** GREEN is an *allowlist* (`gateway.py:138-141`,
  host-mode GREEN = `echo`/`pwd` only); empty input, unknown command, or ANY internal
  exception → RED (`gateway.py:296-297, 348-350`, proven by
  `test_fail_closed_on_internal_exception`). Safe-by-default is *structural*, not a
  blocklist an attacker enumerates around.
- **A redact-before-hash, cross-process audit ledger.** SHA-256 chain, genesis = 64
  zeros, O(n) verify with precise `broken_at` + linkage-vs-tamper distinction
  (`audit_logger.py:115-270`); redacting payload *before* hashing is the non-obvious
  insight that lets no-secret-persistence and chain-validity coexist; a `threading.Lock` +
  `BEGIN IMMEDIATE` extends the critical section across worker processes (4×20 concurrent
  appends → one valid 80-entry chain, `test_concurrent_appends_keep_one_valid_chain`).
- **The RED-un-grantable floor.** Human approval re-classifies and is refused at RED
  ("Human approval cannot authorise a RED action", `executor.py:436-443`,
  `test_execute_approved_still_refuses_red`) — stricter than the blueprint's own
  typed-token override. Human authority is a *widening-only* surface, never a bypass of
  the hard floor.
- **Structural no-self-approval in self-modification.** `SelfApplyEngine`: snapshot → `git
  apply --check` → audit-before-write (no ledger entry → no write) → single-file-confined
  apply → an *independent* two-snapshot byte-comparison → gated verify → auto-rollback.
  There is deliberately **no agent `apply` tool**; applying is reachable only from a human
  HTTP endpoint, approver≠proposer (`self_apply.py:13-18`).
- **The stigmergic learning layer** (most mature subsystem). Asymmetric saturating
  pheromone (one failure ≈ seven successes, constants `0.70805`/`1.04252` pinned by test);
  DIRECT verifier evidence is the *only* path to "verified" (REUSE/co-occurrence can rank
  but can never launder a candidate into trusted); promotion gates ≥3 verified successes
  AND ≥0.8 rate; `db._migrate` SUPERSEDES rather than DELETEs irreplaceable verifier
  evidence (`memory/skills.py`).
- **The earned-autonomy bridge** — the same pheromone math applied to the autonomy
  surface: YELLOW-only, off by default (`AIOS_EARNED_AUTONOMY=False`, `config.py:177`),
  RED-un-earnable, keyed by secret-redacted action SHAPE inside gateway scope, one verified
  failure resets the streak instantly, every auto-grant its own audit-chain entry under
  actor `earned-autonomy` (`aios/core/autonomy.py`).
- **Test discipline that proves contracts, not mocks.** 90% live line coverage of `aios/`,
  512 passing across three suites, the "real gateway, fake runner" pattern (fakes only the
  non-deterministic edges — LLM chat, shell spawn, embedder), negative-path-dominant
  (self_apply: 18 tests, ~15 refusal/rollback).
- **An interface bound to real frames with enforced honest dormancy.** `cognitionBus.ts`
  (~67-line module-singleton pub/sub) makes six subsystems read as one organism; the
  approval "hold" is one product thesis rendered across breath, color, time-dilation,
  camera, and a suspended chord; no trails → no stars, link down → LINK OFFLINE not faked
  activity.

**Honest read on readiness (from the calibre, unflinching):** this is a coherent,
frontier-grade *engineering* foundation proven at the level of its contracts — but it is
not yet a frontier *AI system*, and the gates are **intelligence and isolation, not
architecture.** Three documented edges: (1) the 7–8B local-model ceiling (planning is
advisory, `_calibrate` is a no-op on a cold DB, castes are "architecture proven /
7B-limited", curriculum matching is exact-prompt-string); (2) the autonomous surface is
near-zero *by design* (GREEN allowlist is two patterns); (3) strong OS isolation is opt-in
(the hardened `DockerRunner` is real, but the default host backend is candidly "not an OS
isolation boundary"). **None of these are defects** — they are the deliberate, documented
edges of a supervised OS. The mechanism layer was built to receive a better brain; it does
not yet have one. The frontier is three moves away (better brain, default-strong isolation,
widened earned autonomy), and the system is architected to receive all three.

---

## 3. The frontier, by theme

Each theme states the **north star**, then the **concrete moves** — deduplicated across the
eight specialists, each tagged `[near 0-3mo]` / `[mid 3-12mo]` / `[far 12mo+]` and grounded
in a named existing seed. Every move respects all six invariants; where one *touches* an
invariant boundary, that is called out.

### 3.1 Cognitive architecture — *deliberation per unit of evidence*

**North star:** turn "trust the evidence, not the model" from a *defensive floor* into an
*active reasoning engine* — fold deliberate search and self-consistency into the act loop
as **proposers feeding the same verifier-judge**, so the cage that today adjudicates safety
also adjudicates *thinking*. The upgrade is not a smarter model; it is *more deliberation
per unit of evidence*, all of which the existing cage already scores.

- **Self-consistency-by-verification** `[near 0-3mo]` — for `propose_fixes` (T2) and
  edit/create, generate N=3 candidate diffs, apply each to an isolated temp copy (reusing
  `SelfApplyEngine`'s two-snapshot `_expected_after` machinery), run sibling-pytest on
  *each* via the gated `Verifier`, keep only passers (choose by minimal-diff/lowest
  complexity); on zero-pass report UNVERIFIED honestly. The "vote" is an authoritative exit
  code, not a majority of model opinions. *Grounds:* `_auto_verify` already force-runs
  sibling pytest after a write (`tool_agent.py`); self_apply already verifies+rolls-back
  one candidate. *Risk:* N× pytest cost on a laptop; early-exit on first passer; the
  election is only as good as the sibling test (same ceiling the system already accepts).
- **Verifier-judged tree search** `[mid 3-12mo]` — promote the advisory `Planner` into a
  real System-2 step *between* `model.chat` and `_dispatch` (`tool_agent.py:667-711`):
  sample K=2–3 candidate next-actions, score each by a *deterministic* function
  (`confidence_filter` + `skills.relevant_verified` match + a cheap dry-run: `git apply
  --check`, `gateway.classify` zone, `_expected_after` byte-diff) and pick the branch —
  but **nothing executes until the chosen branch passes the same gateway→approval→verifier
  path**; selection only re-orders *proposals*, YELLOW still pauses. *Grounds:* `Planner`
  is fully built with verified-evidence calibration (`planner.py:147`) but advisory-only.
  *Risk:* K-sampling multiplies local-model latency on a shared GPU; a weak 7B emits
  near-identical branches, so this is genuinely model-gated — *a tree search over a model
  that can only think of one branch is theater* until a 14B+ brain lands.
- **An evidence-derived sandbox world-model (predictive cache, NOT a simulator)** `[mid
  3-12mo]` — a learned predictor over the action→outcome pairs already recorded (zone,
  verify PASS/FAIL, files touched, skill arc) that re-ranks/prunes branches before paying
  for pytest and warns "this edit class has a 0.2 verified-pass rate." It is **advisory**:
  it may prune the search frontier but **the chosen action always gets a real verifier
  verdict before it is trusted.** *Grounds:* `development.relevant_success_rate`
  (`development.py:73`), `skills.trail_map` per-arc verified rate — the pheromone economy
  *is* a primitive world-model already. *Risk / hard invariant:* must fail-OPEN to "no
  prediction, run the verifier" on a cold DB; the instant anyone uses its prediction to
  *skip* a verifier run to save time, the evidence-over-model invariant is violated — so
  its honest framing is "a cache that prunes search," **never** "a model of the world."

### 3.2 Recursive self-improvement — *bounded, verifiable, revocable*

**North star:** turn the audit chain from a passive ledger into the *training set* for a
self-improvement flywheel — the system gets measurably better at the narrow things it has
already PROVEN, where every training label is a tamper-evident exit code, every promotion
is falsifiable on fresh held-out evidence, and the human + RED-block stay exactly where
they are. This is the rarest move the architecture is *uniquely* positioned to make,
because the gold dataset is already being minted every turn.

- **Self-curriculum mined from the audit chain** `[mid 3-12mo]` — an offline,
  operator-triggered job walks the audit ledger + verified skill trails and synthesizes new
  curriculum tasks from sequences already verified-passed N times (goal tokens +
  argument-stripped `skill_signature_v2`), whose held-out check is a *fresh* verifier run.
  Nothing masters without a fresh held-out pass — the existing gate is the safety.
  *Grounds:* `curriculum.py` already refuses anything not prefixed `[VERIFY PASS]`/`[VERIFY
  FAIL]` and masters only on training-passes + coverage + held-out pass; live-proven 6/6
  mastered (2026-06-11). *Risk:* the curriculum trigger is exact-prompt-string today, so
  mined tasks may not fire on organic chat until the semantic-recall layer (§3.4) lands;
  cap mined tasks to avoid unbounded growth.
- **The Evidence-Distillation Flywheel — local LoRA on the verifier-PASS corpus** `[far
  12mo+]` — an offline, operator-launched job exports an SFT/LoRA dataset of *only*
  audit-anchored verified-success traces (prompt → exact tool sequence that produced a
  `[VERIFY PASS]`, secrets already redacted by `scan_and_redact`), trains a small local
  adapter, and the adapter becomes the active proposer **only** if it masters the auto-mined
  self-curriculum at ≥ the incumbent's rate on *fresh held-out* runs; every distilled model
  is itself an audit entry recording the corpus head-hash it trained on; the prior tag is
  instant rollback. The model that *proposes* gets better; it never self-certifies — a
  deterministic held-out gate promotes it, and the cage still decides. *Grounds:* the chain
  is redact-before-hash so traces are already secret-free + tamper-evident; `record_outcome`
  keys verified labels strictly off the verifier; `curriculum.py` held-out gate is the
  ready-made promotion oracle; the Ollama provider + `model_selector` already swap models
  deterministically — "the mechanism built to receive a better brain" is exactly this
  socket. *Risk (highest-ambition, told straight):* the corpus is small and narrow
  (~2 weeks of mostly `training_ground/*`) — a naive day-one LoRA will likely overfit and
  may not beat a clean 14B base; honest near-term form is a *few-shot exemplar bank*, with
  real fine-tuning earned only after the corpus crosses a tested size/diversity threshold;
  LoRA-tight on 16GB; reward-hacking the verifier is the classic failure (mitigated by
  held-out-only promotion + verifier quorum, §3.3). **It never touches the security spine
  or RED; the proposer is advisory, so a degenerate adapter cannot escalate — worst case it
  proposes worse diffs the gate rejects.**

### 3.3 Verifiable trust & safety — *make the cage externally provable*

**North star:** turn "trust the evidence, not the model" from an *internal control-flow
invariant* into an *externally PROVABLE property* — so a third party who trusts neither the
model, the operator, nor the laptop can verify offline that an action was authorized,
bounded, and irreversible-only-as-approved. The proofs are ~80% already computed
(`verify_chain` yields the head hash, self_apply recomputes expected bytes independently,
every grant is its own audit entry); they are just not yet externalized.

- **Continuous adversarial red-team harness (the cage re-proves itself)** `[near 0-3mo]` —
  a standing, CI-gated suite whose job is to *try* to break the invariants and prove it
  cannot: prompt-injection corpora aiming a RED command through the loop, mutation/fuzz of
  the gateway classifier (does any RED mutation slip to GREEN?), forged/stale
  earned-autonomy signatures (does `execute_approved` still re-refuse?), tampered audit
  entries with forward-recomputed chains. Track an explicit "invariant coverage" metric:
  every named law gets one test that proves it holds AND one negative test that proves the
  guard is *non-vacuous* (generalize the self-validating golden harness). *Grounds:* the
  suite is already adversarial and negative-path-dominant; `test_execute_approved_still_
  refuses_red`, `test_fail_closed_on_internal_exception` are the seed templates. This is
  the work that lets the operator widen earned autonomy *with evidence instead of nerve*.
  *Dovetails with PLAN.md S5* (the `--cov-fail-under` gate + cross-suite runner). *Risk:*
  "we couldn't break it" ≠ "unbreakable" — frame as bounded evidence (which corpora, which
  mutation classes), reported at ~90% honesty; fuzzing may surface real RED-escapes
  (alarming-but-good to find — budget remediation).
- **External anchoring of the audit head (transparency-log roots)** `[near→mid 3-12mo]` —
  periodically notarize the chain head: wrap `head_hash` in a signed, monotonically-counted
  checkpoint (Ed25519 from an **off-tree** operator key, `entry_count`,
  `prev_checkpoint_hash`, wall-clock) and emit it append-only to a sink the laptop cannot
  rewrite (a second device, a git-pushed signed tag, an RFC-3161/OpenTimestamps anchor).
  Verify becomes two-stage: local O(n) walk PLUS "local head descends from the last
  witnessed checkpoint and counters never go backwards." This **directly kills the one
  named audit ceiling** — an attacker who recomputes the chain forward now produces a head
  that matches no external witness. *Grounds:* `verify_chain` already returns `head_hash`,
  redact-before-hash means checkpoints carry no secrets; PLAN.md watchlist names this
  exactly ("off-box notarization of the head hash is the fix if/when this matters enough to
  attack"). *Honest framing:* this is tamper-**evidence** and rollback-detection, NOT
  tamper-proof against a full-root attacker (the signing key must live off-tree, or
  anchoring buys nothing). Must stay local-first: offline append-only sink first, public
  timestamping strictly opt-in; additive over the existing chain, never altering the frozen
  write path. **Sequence it with the first real multi-party surface — premature today.**
- **Proof-carrying actions (machine-checkable certificates)** `[mid 3-12mo]` — emit a
  compact signed certificate alongside every consequential action that an *independent*
  verifier checks offline without re-running the LLM. For self-apply: `before-hash` +
  `diff-hash` + `after-hash`; the checker independently recomputes "expected after" from
  before+diff (self_apply already does this in an isolated temp dir) and asserts
  after==expected==on-disk. For an earned-autonomy grant: the action signature + the exact
  streak + the gateway zone re-derivation + the audit entry id; the checker re-evaluates the
  earning predicate purely from ledger data. The *certificate* — not the model's word — is
  the unit of trust; ship an offline `aios verify-action <id>` CLI as the canonical checker.
  *Grounds:* self_apply's two-snapshot byte-comparison is the checker ~80% built; every
  auto-grant is already a distinct audit entry. *Risk:* keep certificates as deterministic
  re-checkable predicates over already-redacted data — NOT a theorem prover; the checker
  must be the *same* code path as the enforcer (single-sourced, tested that a tampered
  certificate fails closed), or it gives false assurance.
- **Boot/runtime attestation — the cage proves it is the cage** `[near→mid 3-12mo]` — on
  startup, measure the frozen security core + key config (a Merkle hash over
  `aios/security/*`) and write it as the FIRST audit entry of every session; refuse to start
  (or run in a loud "UNATTESTED" mode that disables earned-autonomy and self-apply) if it
  doesn't match an operator-pinned baseline; surface the state in the superbrain shield like
  the TAMPER alarm (micro-detail only). *Grounds:* self_apply already hashes+compares bytes
  independently; `agent_coord.py:151-157` already hashes HEAD + diff + untracked bytes — the
  measurement primitive is built. *Risk:* the operator edits `aios/` constantly, so naive
  "refuse on any change" is unusable — the pin must be operator-re-baselined on intentional
  change (a witnessed human event), and DEGRADED-mode (disable autonomy/self-apply, stay
  supervised) must be the default reaction, not a hard halt. Software self-attestation
  raises the bar but is not unforgeable without a hardware root — claim it as
  tamper-evidence.
- **A declarative constitution above the gateway** `[mid 3-12mo, GATED]` — lift the
  currently-implicit, scattered invariants (GREEN allowlist, RED-un-grantable,
  RED-un-earnable, frozen-core) into one signed, versioned policy artifact whose hash is
  written to the chain on load, consulted by gateway/executor/autonomy/self-apply as the
  single source of the invariants, and **structurally un-self-amendable** (the agent's
  self-apply path is forbidden from editing the constitution or `aios/security/*`).
  *Grounds:* every invariant already exists as load-bearing code; self_apply already
  *re-derives* the zone from `target_path` rather than trusting a stored value — the exact
  "don't trust the recorded policy, re-evaluate it" discipline a constitution generalizes.
  ⚠️ **This touches the frozen security core — a non-starter unless it is strictly MORE
  restrictive than the code and the code remains the backstop.** It MUST fail closed (an
  unparseable/missing/hash-mismatched constitution → universal RED, mirroring
  `test_fail_closed_on_internal_exception`); it must never become the *sole* gate or a new
  bypass surface. Requires explicit operator go-ahead per PLAN.md operating rules. **This
  should not jump the queue ahead of the model ceiling and isolation work.**

### 3.4 Lifelong memory — *from accumulation to compounding*

**North star:** close the consolidation loop so the brain-growth loop *compounds* rather
than merely accumulates — the system forgets unverified noise *on principle*, recalls
proven procedures by *meaning* not vocabulary, and reasons over a traversable
evidence-gated world-model. The genuine novelty here is narrow and honest: not the
embedding tech (a standard MiniLM+FAISS stack thousands of RAG apps use), but the
**evidence-gated, hash-chain-audited GOVERNANCE of memory** — promotion, and now forgetting.

- **Semantic recall on the existing FAISS stack (close the two lexical seams)** `[near→mid;
  dovetails PLAN.md S1]` — route skill/lesson/curriculum recall through the SAME FAISS stack
  that already powers `semantic_memory` (currently pure-lexical token-set cosine), and run
  BM25 over a *union* of FAISS candidates AND a global lexical pass (closing the "BM25 only
  over the FAISS pool" seam). **The verified/unverified tiering stays exactly intact:
  semantic similarity may improve RECALL/RANKING only — it can NEVER launder a candidate
  into "verified."** *Grounds:* the FAISS stack, `IndexIDMap` crash-consistency, and hybrid
  `0.25·BM25 + 0.45·FAISS + 0.30·decay` retrieval are built and tested for semantic memory;
  PLAN.md S1 scopes this as ~3–4 days. *Risk:* cold-start embedder load is a known latency
  hotspot (keep the empty-index short-circuit + warm-up); a new test must pin "semantic
  recall can never promote to verified"; ship alongside eviction or it amplifies monotonic
  growth.
- **Evidence-Weighted Sleep — audited consolidation + forgetting** `[near→mid; dovetails
  PLAN.md S4]` — the missing *eviction* half: an out-of-band (operator-triggered, never the
  request path) sweep that age-decays unverified chat below a floor, caps per-type rows
  (lowest strength = recency×reuse×verification-tier loses first), enforces the working-
  memory TTL the docstring promises but never applies, and runs a reflection pass over
  recent verified failures to synthesize higher-order lessons (each of which must itself
  pass the existing evidence gates). **Verified lessons/facts/skill-trails are NEVER
  evicted** — exactly as `db._migrate` SUPERSEDES rather than DELETEs irreplaceable verifier
  evidence. Each eviction batch is one audit entry under a new actor `sleep-consolidation`,
  with a dry-run/preview mode before it evicts anything. *Grounds:* `MemoryConsolidator`
  already does evidence-gated promotion; PLAN.md S4 names this debt. *Risk (the one
  enhancement that can make the system DUMBER):* a TTL bug that evicts a verified trail
  silently lowers intelligence with no error — hard invariant: only compact UNVERIFIED chat
  and SUPERSEDE stale semantic rows; audit-log + dry-run every decision; lower-priority than
  it looks, and must be reversible before it touches anything.
- **A traversable, evidence-gated knowledge graph (close G2 the right way)** `[mid 3-12mo;
  dovetails PLAN.md G2]` — promote the flat `facts.py` triple store into deterministic
  k-hop traversal via a recursive SQL CTE (object becomes next subject), in SQLite, no Neo4j
  at single-operator scale — keeping the contradiction-aware, human-approved, secret-redacted
  write path EXACTLY as-is. Surface the neighborhood as a "VERIFIED GRAPH CONTEXT" block with
  per-edge provenance. *Grounds:* `facts.py` (contradiction detection, supersede-on-reconcile)
  + `consolidation.promote_fact` (every edge enters only via human approval) are the seed;
  PLAN.md G2 explicitly prefers the SQLite recursive-CTE path before deciding if Neo4j earns
  its weight. *Honest deflation:* this is a real, reproducible knowledge graph where every
  edge is proven and every traversal deterministic — but it is **NOT a learned world-model;
  calling it one would be fantasy.** *Risk:* traversal must stay READ-ONLY (writes remain on
  the approved path); bound hop-depth to avoid amplifying a stale-but-active edge.
- **Cross-session meta-skills (abstraction over verified episodes)** `[far 12mo+]` — when N
  distinct verified trails share an arc-structure (same `skill_signature_v2` across different
  goal vocabularies), synthesize a parameterized meta-skill gated by the SAME promotion rule
  (≥3 verified successes, ≥0.8 aggregate rate), demotable on a verified failure. The system
  stops re-learning the same procedure under every phrasing and learns the CATEGORY — the
  pheromone logic generalized one tier up, exactly as earned-autonomy generalized it to the
  autonomy surface. *Grounds:* `skill_signature_v2` already computes arc-level identity.
  *Risk:* abstraction quality is thin on a 7–8B model (the caste ceiling) — correctly
  far-horizon, genuinely needs a 14B+ brain to produce useful generalizations.

### 3.5 Breaking the model ceiling — *the body that grows its own brain*

**North star:** break the 7B ceiling **without surrendering local-first** — the audit chain
is not only a safety ledger, it is a *labeled, tamper-evident, secret-free gold dataset
nobody else in this category has*, and it is the seed of a self-distillation flywheel (see
§3.2) plus the near-term moves that make today's hardware punch a tier above its weight.

- **Quantization + model-rotation as a first-class, audited capability tier** `[near 0-3mo;
  dovetails PLAN.md S1]` — make local quantization (GGUF Q4/Q5/Q6, AWQ) and hot
  model-rotation an explicit dimension the router understands, so a 14B fits the 16GB
  envelope at a known quality/latency trade; record each model load as an audit entry so
  *which brain produced which action* is part of the tamper-evident record. *Grounds:*
  `model_selector` already parses size and has a TASK_FAST lane; the MEMORY note confirms
  the RAM upgrade (8→16GB) makes local viable; PLAN.md S1 frames this as "mostly an
  ops/model swap." *Risk:* quant degrades quality non-uniformly — the router must measure
  *tool-call reliability* per quantized tag, not assume bigger+quantized beats smaller+full;
  rotation is operator-paced, never on the hot per-turn path by default.
- **Capability-aware, evidence-calibrated routing + speculative decoding** `[near→mid
  3-12mo]` — replace the static `_TIERS` heuristic with a router that blends the heuristic
  prior with a *measured* per-model, per-task verified-success rate read from the
  development/skill tables (still deterministic, still no LLM in the path) — the audit chain
  tells the router which local model actually performs on THIS operator's THIS workload; and
  add a speculative-decoding mode where the resident 7B drafts and a heavier local 14B/MoE
  verifies tokens, cutting effective latency so the agentic loop routes to the stronger brain
  far more often. *Grounds:* `model_selector.select_model` is pure/side-effect-free by
  design; `planner._calibrate` already reads verified success-rate to adjust a number
  deterministically — the exact pattern to reuse; `require_tools` proves the router can
  encode hard capability gates. *Risk:* spec-decoding needs both models co-resident — real
  VRAM pressure on a laptop also driving the superbrain's heavy cortex shader; must degrade
  gracefully to single-model routing; a measured score must NEVER override `require_tools`
  (a model that can't tool-call stays excluded); cold-start to the heuristic prior so a fresh
  DB behaves exactly like today.

### 3.6 Human–AI symbiosis interface — *supervise a living mind, multimodally, without ever moving the gate*

**North star:** make the superbrain the first interface where a human *supervises* a living
machine mind multimodally — speaking directives, hearing it defer, glancing to *feel*
whether it is trustworthy right now, watching it auditably widen its own earned-but-revocable
autonomy — while **the single act of consent (the AUTHORIZE click redeeming a deterministic,
single-use capability token) stays the one thing no voice, no glance, and no prose can ever
fake.** Every channel proposes; only the gate decides. *All five moves are
micro-detailing/extension of channels that already exist and are already evidence-bound —
NONE is a redesign; FIDELITY IS SACRED governs every visible pixel: canon tag + goldens +
before/after screenshots in HIS browser before any visual change.*

- **The glanceable trust halo** `[near 0-3mo]` — one ambient, peripheral aura modulation
  whose color/calm IS the measured governance posture from REAL polled telemetry (link
  up/down, chainValid/TAMPER, intervention rate, earned-autonomy count): calm glow =
  supervised-healthy; amber freeze = waiting for you (already built); cold desaturation =
  LINK OFFLINE; slow red breathing = AUDIT CHAIN BROKEN (give the existing tritone a visual
  twin). *Grounds:* `AiosTelemetry` already carries `link`/`chainValid`/`interventionRate`/
  `quarantined`/`earnedAutonomy`; `metricsStore.ts` already zeroes idle drift when linkUp.
  *Risk:* must modulate the EXISTING aura/post-grade (no new HUD element = redesign risk);
  a "healthy green" when the probe is null is a decorative lie — render an honest neutral
  "unknown," never assert health it hasn't measured.
- **The ambient summon (evidence-locked attention economy)** `[near 0-3mo]` — push the
  already-semantic sound engine to a sparse continuous presence track: routine cognition
  stays whisper-quiet; the only two things that pierce the floor are exactly the two the
  operator must act on — a YELLOW `human_required` pause and a RED tamper — neither of which
  can be faked (the tritone only plays on a real `valid:false`, the sus-chord only on a real
  `human_required`, both tested). "Leave it running, it'll call you" — without loosening the
  gate. *Grounds:* `soundEngine.ts` already implements the limiter + ambient bed + tested
  honest events. *Risk:* sound is sovereign-silent until the operator's SOUND click — a
  summon must never auto-enable audio; the summon stays rare BY CONSTRUCTION (never expands
  to routine events).
- **Earned-autonomy provenance gesture / trust receipts** `[near→mid; reinforces PLAN.md
  earned-autonomy]` — make a YELLOW→autonomous graduation (and a revocation) a first-class,
  inspectable moment: a glanceable provenance card showing the redacted action SHAPE, the
  verified streak that earned it, the audit entry id under actor `earned-autonomy`, the
  fact that it is revocable + RED-un-earnable, and a one-click REVOKE; a `--why-autonomous
  <shape>` query prints the full evidence trail. The operator can watch the mind "grow up"
  and audit the proof in the same breath. *Grounds:* `AutonomySnapshot` polling + the
  `earned_autonomy` SSE frame + the `AUTONOMY ⚡N` pill are already wired to REAL ledger data.
  *Risk:* render REVOCATIONS as prominently as grants or it becomes autonomy propaganda;
  earned-autonomy is OFF by default, so on most installs this surface is honestly empty — it
  must render dormant, not fake grants; extend the existing HUD/terminal idiom, don't add a
  panel.
- **Multimodal informed consent on the diff** `[mid 3-12mo]` — deepen the approval recipe so
  the operator can *understand* a pending ask faster across modalities while the single gate
  stays untouched: Piper reads the ask aloud on a `human_required` pause; a *read-only*
  clarify sub-turn answers "what does this touch?" without resolving or expiring the
  single-use token; a glanceable inline risk read ("touches frozen-core / `aios/security`?").
  *Grounds:* `ApprovalPanel.tsx` already renders summary + diff + command and states "No
  prose can approve anything — only these two buttons"; self_apply re-derives the zone from
  `target_path` so a "touches frozen core" read is computable from real classification.
  *Risk (cardinal):* voice/glance must NEVER creep into CONSENT — only the button redeems the
  token; the clarify sub-turn must be read-only and must not consume/expire the
  session-bound, single-use capability.
- **Voice as a directive channel — Whisper-in / Piper-out** `[mid 3-12mo; dovetails PLAN.md
  G1, ranked last]` — close the 0% voice gap, *reframed*: STT feeds the same `/api/generate`
  turn the command bar drives; TTS narrates the SSE stream and announces a `human_required`
  pause aloud. The load-bearing rule, enforced in code: **voice can issue a directive but a
  spoken "yes" NEVER redeems an approval token — only the AUTHORIZE button does**; STT
  confidence below threshold = re-ask, never auto-execute; the gateway re-classifies every
  transcribed token (a mis-heard `rm -rf` still hits RED-by-default), and the operator must
  SEE the transcript before it streams. *Grounds:* the single backend boundary already maps
  every SSE frame to a bus event; PLAN.md G1 scopes Whisper/Piper as the real intended gap.
  *Risk:* Whisper+Piper is a real latency/RAM bet on a 16GB laptop sharing GPU with Ollama
  and may degrade the breath-paced presence — prototype the cost before committing; this is
  *last* of the three blueprint gaps for a reason.

### 3.7 Verifiable multi-agent — *the verifier-anchored handoff as the universal law of collaboration*

**North star:** make "trust the evidence, not the (other) model" the literal law of
agent-to-agent communication — every agent edge refuses to act on a peer's claim until it has
re-derived that claim from the sandbox + the verifier ledger. This system already *invented*
the primitive (hash-pinned, fail-closed-on-drift review, proven across the Claude+Codex
process boundary); the frontier is generalizing it to N minds. *Honest boundary: the
multi-agent surface is architecturally first-of-its-kind but operationally still
single-party and sequential today — every move here becomes a real multi-agent system only
when the model ceiling lifts and a genuine second party exists.*

- **Verifiable Agent-to-Agent Handoff (VA2A)** `[mid 3-12mo]` — lift the `agent_coord.py`
  review-handoff (tree_snapshot hashes HEAD + tracked diff + sorted untracked bytes;
  `record_verdict` fail-closes on post-handoff drift, forbids self-approval) into a reusable
  content-addressed envelope `{producer_id, content_hash, evidence_hash, prev_handoff_hash}`
  that EVERY edge uses — swarm worker→synthesizer, caste coder→reviewer, Codex→Claude. The
  consumer re-derives the content hash from disk before acting; acceptance is its own audit
  entry. Today the in-turn swarm/caste handoff trusts an appended assistant message; this
  makes it evidence-bound. *Grounds:* `agent_coord.py:143-157, 512-539`; the synthesizer/
  reviewer prompts already say "judge ONLY from verifier evidence" — VA2A makes that
  prompt-level intent a mechanical contract. *Risk:* a content-addressed envelope around thin
  7B evidence is rigor theater unless verifier coverage underneath is real — bind the
  envelope to authoritative exit codes, and refuse to emit an envelope for an UNVERIFIED
  Python-write-with-no-sibling-test.
- **Parallel heterogeneous-model swarm with per-leg evidence quorum** `[mid 3-12mo; gated on
  S1]` — `swarm.py` runs workers sequentially *by design* ("the swarm SHAPE is the
  contribution; a stronger/parallel runtime can dispatch the same legs concurrently").
  Dispatch the N independent legs concurrently across heterogeneous models (14B local coder
  for write-legs, fast 7B for triage, optionally a region-gated Bedrock leg for the
  synthesizer), each still over the SAME gated executor and mechanical tool subset; for
  high-stakes subtasks spawn 2–3 workers and accept the result only where their VERIFIER
  verdicts agree — a disagreement escalates to the human exactly like a YELLOW pause.
  *Grounds:* workers share no mutable state (stigmergy via sandbox + trail field); caste tool
  subsets are enforced mechanically at `tool_agent._dispatch`. *Risk:* a 16GB laptop cannot
  hold 3 concurrent 14B models — true parallelism is gated on the same RAM/model ceiling;
  make quorum opt-in for flagged subtasks; shared `MAX_REPLAYS`/`TURN_TIMEOUT` caps must
  become per-worker or they truncate a fan-out.
- **Cryptographic agent identity** `[mid 3-12mo]` — per-agent keypairs (operator-issued,
  local, offline) so every lease/heartbeat/handoff/verdict carries an Ed25519 signature over
  the canonical action + tree_snapshot; the control plane verifies before mutating state;
  "builder cannot approve their own handoff" becomes cryptographic, not string-equality on a
  self-reported name. *Grounds:* `agent_coord` trust decisions exist but rest on honor-system
  names. *Honest framing:* on one laptop this is identity *hygiene* — it becomes a security
  boundary only once a second machine / real remote agent joins AND it is paired with off-box
  anchoring (§3.3). Don't oversell it as enforcement on a single box.
- **Earned-autonomy as a trustless inter-colony skill/autonomy market** `[far 12mo+]` — make
  an earned signature a PORTABLE, verifiable credential: a colony exports a signed evidence
  bundle (streak + verifier verdicts + audit segment) that another colony can import **only
  after re-verifying locally** — it cannot trust the exporter's claimed streak; it
  re-earns, or accepts strictly on probation (local streak = 0). The "co-occurrence can never
  launder into verified" invariant, generalized across a population. *Grounds:* `autonomy.py`
  `_normalize`/signature (scope-bound, secret-redacted shape) + skill-trail DIRECT-evidence
  promotion. *Risk:* an imported grant that auto-grants without local re-verification would
  catastrophically violate evidence-over-model AND widen GREEN a human never authorized — the
  design MUST force import-to-probation, and RED stays un-earnable. Genuinely premature
  (there is ONE install today); design the bundle format now, ship trading only once a real
  second colony exists.

### 3.8 Category & positioning — *win the category by writing the rulebook*

**North star:** make the first-of-its-kind claim *legible and PROVABLE* — categories are
won by whoever writes the rulebook, and the moat here is a *finished discipline*, so the
highest-leverage positioning move is to make that discipline executable, reproducible, and
externally anchored on demand.

- **The Refusal Reel** `[near 0-3mo]` — a single `prove.py` driver (modeled on the existing
  fail-closed allowlist drivers) that runs a fixed adversarial script against the LIVE HTTP
  surface and emits a signed, re-diffable transcript + the superbrain rendering it live: (1)
  submit a RED command, watch the gateway refuse; (2) approve it via the real one-click
  endpoint, watch `execute_approved` STILL refuse it; (3) earn autonomy on a YELLOW shape,
  watch it auto-execute, inject ONE verified failure, watch the streak reset and the next
  identical action drop back to a human pause; (4) tamper one byte in a *copy* of the audit
  DB, watch `/api/v1/audit/verify` flip to TAMPER with the exact `broken_at` and the
  superbrain shield sound the tritone. The value is the inverse of every "safe agent" demo:
  what the system REFUSES *even when you tell it not to*, re-runnable by a skeptic against the
  same fail-closed code. *Grounds:* built entirely on shipped, tested seams + the existing
  evidence drivers. *Risk:* the tamper step writes to a *copy*, never the live ledger; reuse
  the single-sourced allowlist helpers; it proves the CONTRACTS, not real shell-quoting or
  container-flag behavior — say so.
- **The Cage Conformance Spec** `[near 0-3mo]` — author "The Evidence-Locked Supervised
  Agent: 7 invariants and their conformance tests," each stated as a falsifiable property
  citing the exact test that proves it (I1 fail-closed-everywhere →
  `test_fail_closed_on_internal_exception`; I2 approval-cannot-authorize-RED →
  `test_execute_approved_still_refuses_red`; I3 redact-before-hash →
  `test_secret_is_redacted_before_persistence`; I4 cross-process single valid chain →
  `test_concurrent_appends_keep_one_valid_chain`; I5 DIRECT-evidence-only promotion; I6
  earned/revocable/RED-un-earnable autonomy; I7 the interface cannot fake activity →
  `soundEngine`/`aiosAdapter` dormancy tests). Ship it as a versioned spec a third party
  could run their own system against. *Grounds:* every invariant is already test-pinned in a
  512-passing suite. *Risk:* pure positioning power only if honest — the spec MUST include the
  negative section (the skipped symlink test never runs on Windows; no test exercises a real
  subprocess/Docker/Ollama; the 3D scene has zero unit tests; the autonomous surface is tiny
  by design; isolation is opt-in). Its value is realized only alongside the Refusal Reel that
  makes it executable.

---

## 4. The single flywheel — the spine of the vision

One compounding loop ties every theme above together. Name it the

> ### **Evidence-Locked Self-Improvement Flywheel**

```
  verified outcomes  ──►  the audit-chain GOLD CORPUS  ──►  a better local brain
   (exit codes the          (tamper-evident,                 + better trails/recall
    cage forced)             secret-redacted,                 (distill on PASS-only;
        ▲                     verifier-labeled)                semantic recall)
        │                                                            │
        │                                                            ▼
   more verified  ◄──  a WIDER earned-autonomy surface  ◄──  more competent proposals
    outcomes            (graduated by the SAME pheromone        (System-2 deliberation,
                         evidence, RED-un-earnable,              verifier-quorum, swarm)
                         instantly revocable)
```

Every turn the system runs, the cage forces an authoritative PASS/FAIL exit code and the
chain notarizes it. That stream is **the rarest asset in local AI: a verifier-authoritative,
hash-chained, secret-free corpus nobody had to hand-label.** Today it is read only as a
safety record. The flywheel turns the moment it is *also* read as fuel:

1. **Verified outcomes → gold corpus** — already minted every turn (`audit_logger.py`,
   `record_outcome`).
2. **Gold corpus → a better brain + better trails** — self-distillation (§3.2) trains a
   local LoRA on PASS-only traces, gated by a held-out curriculum bake-off; semantic recall
   (§3.4) surfaces proven procedures by meaning; consolidation forgets unverified noise.
3. **Better brain → more competent proposals** — verifier-judged deliberation, quorum,
   and a parallel heterogeneous swarm (§3.1, §3.7) propose better candidates.
4. **More competent proposals → wider earned autonomy** — proven shapes graduate to GREEN
   by the SAME verifier evidence (§3.2 self-curriculum, the earned-autonomy bridge), with
   shadow-grant probation if added.
5. **Wider autonomy → more verified outcomes** — a wider (still bounded, still
   human-floored) surface produces more verified traces, feeding step 1 again.

**Why this is the spine and not just one move:** it is the only loop where *every link is
evidence-locked*. A hallucinated success never produced a `[VERIFY PASS]` entry, so it can
never enter the corpus, never train the brain, never widen autonomy. The flywheel
*structurally cannot* launder model confidence into capability — which is exactly the
invariant the whole system is built on, now expressed as a growth engine. **Honest
caveat: it turns SLOWLY at first** — the corpus is small and the autonomous surface is
near-zero by design, so the early gains are narrow and may plateau on a 7B base. The
flywheel's strength is also its bound: it can only ever learn what the verifier can
authoritatively judge. That is the honest version of "self-improving," and it is a rarer,
more honest thing than "the AI rewrites itself."

---

## 5. Honest horizon roadmap

Sequenced by leverage. **This DOVETAILS with `PLAN.md` and never contradicts it** —
`PLAN.md` is the near-term execution truth (do its Tier 0 hygiene and Tier 1 gaps first);
this table is the multi-year north star *above* it, mapping each frontier move to the
PLAN.md item it extends. "First-of-its-kind" is the defensible novelty; "Risk" is the honest
failure mode.

| Move | Horizon | Grounds-in (seed / PLAN.md item) | What makes it first-of-its-kind | Risk |
|---|---|---|---|---|
| **Refusal Reel + Cage Conformance Spec** | near | existing fail-closed drivers; the 512-test suite; `executor.py:436-443` (PLAN.md S5 cross-suite gate) | A self-running, re-runnable proof whose value is what the system REFUSES — including the operator's own RED approval | Proves contracts, not shell/container/model behavior; spec must publish its own gaps |
| **Continuous adversarial red-team harness** | near | negative-path test discipline; self-validating golden harness (PLAN.md S5) | A self-modifying agent continuously re-proven *unable to rewrite its own cage*, 1:1 to named invariants | "Couldn't break it" ≠ unbreakable; may surface real RED-escapes |
| **Semantic recall on FAISS (close lexical seams)** | near→mid | FAISS/`IndexIDMap` + hybrid retrieval already built (PLAN.md **S1**) | Semantic recall that widens RANKING but is structurally forbidden from promoting to verified | Embedder cold-start latency; needs a test pinning "recall never promotes" |
| **Evidence-Weighted Sleep (audited forgetting)** | near→mid | `MemoryConsolidator`; `db._migrate` supersede-not-delete (PLAN.md **S4**) | Forgetting as principled, evidence-gated, hash-chain-audited as learning | A TTL bug evicting a verified trail makes it *dumber* — must be dry-run + reversible |
| **Quant + audited model-rotation; evidence-calibrated routing + spec-decoding** | near→mid | `model_selector` (pure); `planner._calibrate`; RAM 8→16GB (PLAN.md **S1**) | A local router tuned by the system's OWN tamper-evident outcome history, not gameable telemetry | Quant degrades tool-calling non-uniformly; spec-decoding needs both models co-resident |
| **Glanceable trust halo + ambient summon** | near | `AiosTelemetry`/`metricsStore`; tested `soundEngine` (PLAN.md S6, FIDELITY) | Trust state made *perceptual*; an attention economy that can only interrupt you on real, un-fakeable evidence | FIDELITY: micro-detail only, goldens first; null state must read honest "unknown" |
| **External anchoring of the audit head** | near→mid | `verify_chain` head_hash; redact-before-hash (PLAN.md watchlist) | A self-modification ledger anchored to an out-of-band witness — tamper-evidence beyond the box | Tamper-EVIDENCE not tamper-proof; key must be off-tree; premature until a multi-party surface exists |
| **Self-consistency-by-verification (N→1 election)** | near | `_auto_verify`; self_apply two-snapshot (PLAN.md self-analysis surplus) | A self-modifying loop where a deterministic test harness, not the LLM, elects the survivor | N× pytest cost; only as good as the sibling test |
| **Earned-autonomy trust receipts / provenance gesture** | near→mid | `AutonomySnapshot`, `earned_autonomy` SSE, `AUTONOMY ⚡N` pill (FIDELITY) | Ask "WHY is this autonomous?" → a deterministic, evidence-backed, revocable answer | Must show revocations as prominently as grants; honestly dormant when OFF |
| **Verifier-judged tree search + sandbox world-model** | mid | advisory `Planner`; `skills.trail_map`; `confidence_filter` | Test-time search whose value function is a fail-closed deterministic kernel, not the model judging itself | Model-gated — theater on a 7B that emits one branch; world-model must never gate execution |
| **Self-curriculum mined from the audit chain** | mid | held-out-gated `curriculum.py`; `skill_signature_v2` (PLAN.md S1 dep) | Curriculum whose every label is a cryptographically-anchored exit code | Exact-prompt trigger until semantic recall lands; curriculum bloat |
| **Knowledge-graph traversal (recursive CTE)** | mid | `facts.py` + `consolidation.promote_fact` (PLAN.md **G2**) | A contradiction-aware, human-approved, audited graph whose multi-hop recall is deterministic SQL | NOT a learned world-model; bound hop-depth; read-only traversal |
| **Proof-carrying actions + boot/runtime attestation** | mid | self_apply byte-recompute; `agent_coord` tree-hash | A portable receipt that an autonomous write was earned, bounded, = exactly the approved diff | Keep checker single-sourced with enforcer; software self-attestation, not unforgeable |
| **VA2A handoff protocol** | mid | `agent_coord.py:512-539` (PLAN.md coordination surplus) | "Trust the evidence, not the other model" as an inter-agent *protocol* | Rigor theater unless verifier coverage underneath is real |
| **Voice as a directive (not consent) channel; multimodal informed consent** | mid | `cognitionBus`/`aiosAdapter`; `ApprovalPanel` (PLAN.md **G1**, ranked last) | Voice structurally barred from being a consent channel — speech proposes, only the gate decides | RAM/latency bet that may degrade breath-paced presence; voice must never wire to the approval POST |
| **Parallel heterogeneous swarm + verifier quorum; cryptographic agent identity** | mid | `swarm.py` (sequential-by-design); `tool_agent._dispatch` (gated on S1) | An ensemble that votes on independent VERIFIER verdicts, with a tie escalating to the human | 16GB can't hold 3×14B; identity is hygiene on one box until a second party exists |
| **Declarative constitution above the gateway** ⚠️ | mid | the implicit invariants; self_apply zone re-derivation | Constitutional principles ENFORCED in non-model code + an immutable audit of every amendment | **Touches frozen core** — must be strictly MORE restrictive + fail-closed + never the sole gate; needs explicit go; must not jump the queue |
| **Evidence-Distillation Flywheel (local LoRA on PASS-only)** | far | redact-before-hash chain; `record_outcome`; curriculum held-out gate (PLAN.md **S1** + RAM) | A recursively self-improving proposer structurally unable to launder its own confidence into the weights | Small/narrow corpus → overfit; near-term form is a few-shot exemplar bank; LoRA-tight on 16GB; never touches RED |
| **Cross-session meta-skills; trustless inter-colony market** | far | `skill_signature_v2`; the earned-autonomy bridge | Abstractions formed only from proven, audited evidence; a market where the buyer can't trust the seller's score | Abstraction quality thin on 7B; market premature with one install; imports must be probation-only |

**Queue discipline (honest):** do not let the verifiable-trust and multi-agent frontier
jump ahead of the two gates the calibre names — **a better brain and default-strong
isolation** (PLAN.md **S1**, **S2**) — which do more for real capability than any proof
layer. The frontier work is what makes this *first-of-its-kind and defensible*; the model
ceiling and isolation are what let it *genuinely run itself.* Both matter; the sequence is
brain/isolation first, proof/anchoring as a multi-party surface emerges.

---

## 6. What would PROVE it — the demonstrations that convince a skeptic

Three falsifiable, re-runnable artifacts — not pitches:

1. **The Refusal Reel re-run against the live code.** A skeptic runs `prove.py` themselves
   and watches the system: refuse a RED command, refuse the *same command after their own
   one-click approval* ("Human approval cannot authorise a RED action"), auto-execute an
   earned YELLOW shape and then *narrow the surface back to a human pause the instant one
   verified failure lands*, and flip `/api/v1/audit/verify` to TAMPER with the exact
   `broken_at` index when one byte is changed. The refusals are *structural*, not
   prompt-tuned — that is the un-dismissable proof the floor exists and the human cannot
   lower it.

2. **The flywheel closing once, end-to-end, on held-out evidence.** Mine the audit chain
   into a self-curriculum, distill a small LoRA on PASS-only traces, and show the new
   adapter promoted **only** because it mastered the auto-mined curriculum at ≥ the
   incumbent's rate on *fresh* held-out verifier runs — with the whole promotion recorded as
   its own audit entry citing the corpus head-hash. If the adapter is degenerate, show the
   gate *rejecting* it. That single closed turn — verified outcomes → corpus → a better
   proposer → falsifiably promoted, with the cage still deciding — is the proof that
   "self-improving" here means *bounded, verifiable, revocable*, not slideware.

3. **An externally-witnessed audit head surviving a tamper attempt.** Anchor the head
   off-box, then have a skeptic with full local write access recompute the chain forward
   from a tampered entry — and show that the next `verify --since-anchor` detects the divergence
   because the forged head matches no external witness. This converts the one named audit
   ceiling into a demonstrated tamper-evidence guarantee a third party can check.

---

## 7. Honest counterweight — the strongest case that it is NOT special yet

Told straight, at the operator's ~90% standard, folding in every specialist's
`honestCaveat`:

- **The brain is the ceiling, and the ceiling is real.** 7–8B local: planning is advisory,
  `_calibrate` is a no-op on a cold DB (raw model self-report runs the gate), castes are
  "architecture proven / 7B-limited," curriculum matching is exact-prompt-string. **This is
  a supervised assistant that can safely *act*, not yet a system that genuinely *runs
  itself.*** Nearly every cognitive/recursive/multi-agent move above is *model-gated* — a
  tree search over a model that can think of only one branch is theater; meta-skill
  abstraction is thin on 7B; the distillation corpus is two weeks of narrow
  `training_ground/*` vocabulary that a naive LoRA will overfit. **To overcome it:** a 14B+
  local brain that fits (PLAN.md S1), plus the semantic-recall layer — at which point the
  same architecture compounds instead of plateauing.

- **The autonomous surface is near-zero by design.** Host GREEN = `echo`/`pwd`;
  earned-autonomy is OFF by default. "Self-improving" is true and shipped but *deliberately
  narrow* — the flywheel turns slowly because the evidence stream is thin until autonomy is
  opened. **To overcome it:** widen the evidence→GREEN bridge carefully (shadow-grant
  probation, verifier quorum) *as evidence accumulates*, never as a config flag.

- **The strongest isolation is opt-in.** The hardened `DockerRunner` is real and tested, but
  the default host backend runs approved code as the backend OS user and is candidly "not an
  OS isolation boundary." Today the cage is a *policy/audit* cage by default, a true OS cage
  only with Docker present. **To overcome it:** PLAN.md S2 — make hardened Docker the default
  where available, or add a lighter host-path sandbox.

- **The audit chain has no external root of trust (yet).** A full-write-access attacker can
  recompute a self-consistent forgery. Inherent to the single-laptop threat model, not a
  defect — but the trust guarantee is "tamper-evident on this box," not "tamper-evident,
  period." **To overcome it:** external anchoring (§3.3) — *sequenced with the first
  multi-party surface, premature before then.*

- **The marquee face has zero unit tests.** The 3D superbrain — the "face that cannot lie"
  — rests on golden PNGs + puppeteer probes a human eyeballs; a hold-choreography or
  wave-anchoring regression would not fail CI. **To overcome it:** the standing
  micro-detailing mandate + FIDELITY-gated goldens, and targeted tests for the
  honesty-bearing seams (the dormancy/event tests already prove the principle).

- **The tests prove CONTRACTS, not the world.** Gating, refusal, verify, chain integrity are
  genuinely proven; real shell-quoting, real container flags, and real model behavior are
  not (and largely cannot be, by the test design). The Refusal Reel and Conformance Spec
  must say this plainly or be trivially debunked.

- **Each axis alone has prior art.** Fail-closed kernels, hash chains, constitutional
  principles, RAG memory, agent handoffs, 3D dashboards — none is novel in isolation. **The
  honest first-of-its-kind claim is the *merged axis*:** an evidence-locked fail-closed cage
  + an earned/revocable/RED-un-earnable autonomy bridge driven by the same verifier evidence
  + a real-data living-mind face that goes honestly dormant — carried *without compromise*
  through all six subsystems. **What must be true to keep the claim:** the discipline stays
  finished and the moves above stay honest — every channel proposes, only the gate decides;
  the model never vouches for itself; the floor never lowers; and the vision is reported at
  ~90%, never oversold.

The unglamorous hard part — the evidence-locked, fail-closed, audited, self-modifying core —
is the part most people never finish, and it is already built. The frontier is three moves
away (a better brain, default-strong isolation, a widened-but-evidence-gated autonomy
surface), and the system is architected to receive all three. That is the honest north star:
not "the AI that rewrites itself," but **the first AI-OS that can safely, auditably, and
revocably let itself act on PROVEN, narrow competence — and lets a skeptic re-run the proof.**

---

_Dated 2026-06-13. North star above `PLAN.md`; never a substitute for it. Every move grounds
in a named existing seed, is feasibility-rated, and respects all six invariants. Where a move
touches the frozen security core (the declarative constitution), it is marked ⚠️ and requires
explicit operator go-ahead and a strictly-more-restrictive, fail-closed design — or it does
not ship._
