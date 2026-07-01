# Spec — Continuous Frontend Renovation Worker (CRW)

**Status:** Design draft for operator review · **Date:** 2026-07-01 · **Author:** Claude
**Origin:** operator's standing idea (2026-06-03, `frontend-polish-worker-idea`) — now buildable because the supervision substrate shipped (Council Runtime, real rollback, ruflo shared memory, cloud-32B compute).
**Related:** `2026-07-01-fusion-roadmap-workorders.md` (the CRW is essentially "Lane K, running forever") · `2026-07-01-cortex-core-fusion-adr.md`

---

## 0. The one honest boundary (read first)

A machine **cannot see the WebGL brain render** (AGENTS.md §XIII: no headless WebGL; the final palette/texture/aesthetic call is the operator's browser). Therefore the CRW works **only the machine-verifiable axes of frontend quality** and **never** claims to improve subjective beauty. The taste stays in the operator's eyes — by design, not by limitation. Any proposal the CRW opens must cite **objective, reproducible evidence** (a failing check, a budget breach, a violation count). If it can't be measured, the CRW does not touch it.

This is what keeps the worker **net-positive** instead of a babysitting tax: it only ever surfaces work you'd otherwise do by hand and can verify at a glance.

---

## 1. What it is / is not

**Is:** a supervised, **propose-only**, externally-scheduled worker running on the **cloud L4 / qwen2.5-coder:32b** (off the operator's Claude budget) via **ruflo**, that continuously hunts machine-verifiable frontend regressions in the **lab** (`GAG demo/gag-orchestrator`), opens **gated, evidence-backed** proposals, self-verifies them green, canon-guards them, has them **council-prescreened**, and hands the operator a small approval queue to eyeball at `:5173`. Rollback-backed.

**Is not:** an autonomous applier, a palette/texture editor, a "make it prettier" free-roamer, a self-triggering daemon, or anything that writes to the frozen security spine. *"Never an autonomous daily self-driver — the exact anti-pattern this project rejects"* (original memory, still binding).

---

## 2. The two axes (only one is the CRW's job)

| Axis | Examples | Owner |
|---|---|---|
| **Machine-verifiable** ✅ CRW scope | a11y/WCAG contrast & focus order, reduced-motion correctness, keyboard nav, ARIA/semantic HTML, perf/DPR & bundle budget, dead/duplicate CSS, unused exports, `eslint`/`tsc` findings, token/canon compliance, test-coverage gaps on interaction logic, broken-link/asset refs | CRW proposes → operator approves |
| **Subjective beauty** ✋ NOT CRW | palette warmth, glow/density, "does the being feel premium", motion taste, composition | **Operator's browser only** (sacred canon) |

The CRW may maintain a **"human-look queue"** — a list of *things worth the operator glancing at* (e.g. "this component changed size") — but it **never labels those as improvements** and never edits on that basis.

---

## 3. Architecture

```
 External scheduler (cron / operator "go")         ← CRW cannot self-trigger (AGENTS §0.2, §VII.3)
        │
        ▼
 Cloud L4 VM  ──ruflo agent_execute──▶  qwen2.5-coder:32b  (the CRW "hands + eyes-on-code")
   (off Claude budget)                        │
        │                                     ▼
        │                         operates in the LAB  ('GAG demo/gag-orchestrator', unrestricted build space)
        │                                     │
        ▼                                     ▼
   ruflo shared memory  ◀────────────  proposal + evidence + dedup state
   (gagos-crw-*)                              │
                                              ▼
                        ┌──────────  DETECTOR → PROPOSER → SELF-VERIFY → CANON-GUARD ──────────┐
                        │                                                                        │
                        ▼                                                                        ▼
             Council pre-screen (PlannerQueen / reasoning)                          Operator approval queue
             — rejects noise, ranks by evidence strength —                          (:5173 glance, gated)
                        │                                                                        │
                        └──────────────────▶  approved  ──▶  npm run port ──▶ commit ──▶ rollback-if-regressed
```

**Why lab-not-product:** product `frontend/src/superbrain/*` is byte-synced from the lab by `npm run port` and **overwritten** — editing it directly is futile. The lab is the unrestricted build space; canon guards protect the only sacred bits. So the CRW edits the lab, and the port step is part of the *approved-apply* path, never the worker's.

---

## 4. The loop (one cycle)

1. **DETECT** — run the objective battery in the lab and collect concrete findings with evidence:
   - `npm run lint` (eslint), `npm run typecheck` (tsc), `npm run test` (vitest), `npm run build`
   - a11y audit (axe-core or eslint-jsx-a11y over the 2D chrome components), reduced-motion/focus checks
   - bundle/perf budget diff (build output size vs a stored budget)
   - dead-CSS / unused-export scan
   - `python tools/check_css_canon.py` + `python tools/check_canon_frozen.py` (palette/texture compliance — these are machine-checkable canon)
2. **DEDUP** — drop any finding already proposed-and-pending or **previously rejected by the operator** (ruflo `gagos-crw-rejected`). Never re-surface a rejected item. (Loop-until-dry discipline — no nagging.)
3. **PROPOSE** — for each fresh finding, the 32B drafts a minimal diff in the lab that fixes exactly that finding. One finding → one small proposal. No bundling, no scope creep.
4. **SELF-VERIFY** — the proposal must keep **all** gates green: `lint`, `typecheck`, `test`, `build`, both canon scripts. If red → discard silently (not the operator's problem).
5. **CANON-GUARD** — any palette/texture delta → auto-reject (the guards do this deterministically). The CRW may never pass `--allow-canon`.
6. **COUNCIL PRE-SCREEN** — PlannerQueen/reasoning ranks surviving proposals by evidence strength and kills low-value noise, so the operator queue stays short and high-signal. (Uses the shipped Council reasoning layer, fail-closed NARROW-ONLY clamp intact.)
7. **QUEUE** — write the proposal (diff + evidence + which check it fixes) to the operator's approval queue and ruflo `gagos-crw-pending`. **Stop. Do not apply.**
8. **APPROVE (human)** — operator reviews at `:5173`, approves/rejects. Approve → `npm run port` + commit (operator, or a gated apply step) → snapshot taken. Reject → recorded in `gagos-crw-rejected` so it never returns.
9. **ROLLBACK-IF-REGRESSED** — if an applied change later shows a regression, the real snapshot rollback (shipped this session) reverts it.

---

## 5. Safety invariants (non-negotiable)

1. **Propose-only. Nothing auto-applies.** The apply step is human-gated; `npm run port` + commit happen only after operator approval (AGENTS §VII, §VIII: proposing is GREEN, applying is YELLOW/RED).
2. **Unattended ⇒ plan-only** (§VII.3). The CRW is *always* unattended by definition → it is *structurally* incapable of YELLOW. Enforce in code, not just policy.
3. **Frozen security spine untouched** — `aios/security/*` out of scope; the CRW's `SCOPE_ROOTS` are the lab + `frontend/` non-product-safe files only.
4. **Palette + textures are sacred** — canon guards are hard gates; no `--allow-canon`; ever.
5. **All gates green or the diff dies** — `lint`+`typecheck`+`test`+`build`+both canon scripts.
6. **One-writer-per-tree** — the CRW holds an `agent_coord.py` lease (or runs in its own worktree) exactly like Codex; hash-pinned handoff for review. It coexists with Codex by staying on **frontend/lab files only** — disjoint from the backend spine Codex owns.
7. **Evidence or silence** — no proposal without a citable objective finding. No aesthetic claims.
8. **Bounded queue** — hard cap (e.g. ≤5 pending proposals). If the queue is full, the CRW idles. Prevents proposal spam / review-tax.
9. **No secret persistence; localhost-bound cloud tunnel** (existing ollama-startup hardening).
10. **Cost guard** — the cloud VM keeps its idle auto-shutdown; the CRW schedule respects a credit budget.

---

## 6. Continuity & anti-nag (ruflo)

- `gagos-crw-state` — last scan fingerprint + budget spent.
- `gagos-crw-pending` — open proposals (dedup source).
- `gagos-crw-rejected` — operator-rejected findings; **permanent skip list** (the mechanism that stops it re-proposing the same thing every run — the difference between a helper and a pest).
- `gagos-crw-landed` — approved+applied, for the changelog.
Each cycle: recall these first (don't cold-start), reconcile, then act. Mirrors the `experiences.jsonl` discipline into the searchable shared brain.

---

## 7. Build plan (phased, small, reversible)

- **P0 — Detector harness (no worker yet).** Wire the objective battery (§4.1) into one script that emits a JSON findings list with evidence. Runs locally. *Value even standalone:* a "frontend health" report. Gate: green on current lab.
- **P1 — ruflo dedup/state + rejected skip-list.** The memory spine (§6) with a fake findings list. Prove no-nag: a rejected finding never re-surfaces.
- **P2 — Proposer on cloud-32B (propose-only, manual trigger).** 32B drafts one minimal diff per finding in the lab; self-verifies all gates; writes to the queue. Operator triggers manually, reviews at `:5173`. No scheduler yet.
- **P3 — Council pre-screen + ranking.** Route surviving proposals through PlannerQueen; short, high-signal queue.
- **P4 — External scheduler + cost guard.** Cron the cycle; enforce plan-only-when-unattended in code; VM idle-shutdown respected.
- **P5 — Apply path + rollback wiring.** Gated approve → port → commit → snapshot; regression → rollback. (Operator still clicks approve.)

Each phase is independently useful and shippable; stop at any phase and you still have value (P0 alone is a health report).

---

## 8. Non-goals (explicit)

- No autonomous applying, ever.
- No palette/texture/aesthetic editing or judging.
- No headless "does it look good" screenshotting of the WebGL brain (impossible; dishonest to fake).
- No backend edits (Codex's lane; the CRW is frontend/lab only).
- No self-triggering.
- Not a replacement for the operator's `:5173` eye — a **feeder** to it.

---

## 9. Open decisions for the operator

1. **Approval surface:** where do you want the queue — a panel in GAGOS, a `.aios/state/CRW_QUEUE.md` file, or a ruflo-backed list you ask me to summarize?
2. **Cadence:** continuous (every N min while the VM is up) vs. a daily batch vs. on-demand only? (Cost + review-load tradeoff.)
3. **a11y engine:** axe-core (runtime, needs a headless DOM for the 2D chrome) vs. static `eslint-jsx-a11y` only (cheaper, no runtime). Recommend starting static.
4. **Scope of "frontend":** just the 2D chrome (`GagosChrome`, tokens, non-WebGL) — where machine checks are strong — or also the R3F/lab TS where checks are weaker? Recommend 2D-chrome-first.
5. **Does the CRW count as the second builder** (taking Lane K's machine-verifiable quick-wins continuously) now that Kimi may be out, with Codex on the spine?

---

## 10. Honest bottom line

This is the original propose-only polish worker, finally standable-behind because rollback, council supervision, ruflo continuity, and free cloud compute now exist. It will **not** make your brain more beautiful while you sleep — that's yours and should stay yours. It **will** take the objective, measurable drudgery (a11y, perf, dead code, canon compliance, lint/type/coverage) off your plate as a steady stream of small, evidence-backed, one-glance-approvable diffs — and never nag you twice about the same thing. That's the version worth building.

— Grounded: `tools/check_{css_canon,canon_frozen}.py`, lab `GAG demo/gag-orchestrator`, frontend gates `lint`/`typecheck`/`test`/`build`, AGENTS.md §VII/§VIII/§XI/§XIII, shipped Council + rollback + ruflo.
