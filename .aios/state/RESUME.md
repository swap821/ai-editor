# RESUME MANIFEST

## Current goal
The AI-OS is a real, supervised, memory-driven cognitive system (see
`.aios/state/BACKEND_TRUE_PICTURE.md` — the 8-agent deep read; NOT an MVP).
Active front: extend its CAPABILITY (earned autonomy + worker swarm) and keep
the superbrain frontend worthy of it. Two CEOs/Chief Architects: Claude + Codex
(50/50, §III-A). Codex is OFFLINE, back ~2026-06-16 → documented pattern is
operator-authorized landing + POST-HOC Codex inbox review.

## Last completed and verified (2026-06-13, Claude session)
1. RECOVERED the limit-killed Fable micro-detail audit (132 findings) and
   shipped POLISH II–XI of the superbrain (sound, interaction a11y+visual,
   motion/tokens, signal+galaxy shaders, chrome alignment, glass rim+approval
   recipe, galaxy color-space, cortex casing, console rim+approval anchoring).
   All committed + ported byte-faithful; goldens are documentary
   (polish-ladder-complete.png). Held: approval-panel entrance, objective-bar
   scaleX, section-label weight (judgment calls).
2. BACKEND_TRUE_PICTURE.md — deep, honest architecture read (security spine,
   cognition core, multi-store memory, stigmergic learning, RAG production path
   + CAG-style recall-before-turn injection, self-apply).
3. EARNED AUTONOMY (the evidence->GREEN bridge): `aios/core/autonomy.py`
   AutonomyLedger; wired into ToolAgent's YELLOW seam + `main.py` make_agent;
   `GET/POST /api/v1/development/autonomy`. Opt-in (`AIOS_EARNED_AUTONOMY`),
   off by default, RED un-earnable, instant-revoke-on-failure, frozen spine
   untouched. 13 tests.
4. WORKER SWARM (ant-colony): `aios/agents/swarm.py` run_swarm (decompose -> N
   ephemeral gated workers -> synthesize; stigmergic via conversation+sandbox+
   trails; bounded by SWARM_MAX_WORKERS). Wired as the `swarm` request flag.
   5 tests.
5. LIVE-PROVEN both (backend on :8000, AIOS_EARNED_AUTONOMY=true, min=3):
   - Swarm built a REAL verified file: `training_ground/wordcount.py` +
     test (3 passed). 7B finished subtask 1, not subtask 2 (model-limited,
     architecture proven). Driver: `swarm_demo.py` (operator-authorized,
     curriculum-driver hard allowlist).
   - Earned autonomy GRADUATED live (`earn_demo.py`): streak 1->3 = earned,
     then turns 3/4/5 auto-granted writes with ZERO approvals, each VERIFY
     PASS. Ledger: create_file:training_ground/*.py = earned, succ=6.
   Full suite: 456 passed, 1 skipped. Pushed to swap821/ai-editor master.
6. COORDINATION CATCH-UP done: routed earned-autonomy-and-swarm-v1 (builder
   claude/reviewer codex), claimed lease -> hash-pinned handoff (msg 17) +
   review-request (msg 18) to Codex; marked his msg #8 read; gitignored .aios/tmp.
7. PRESERVED all of Fable 5.0's Jun 9-12 work: parent (backend+docs, 66 commits)
   + lab superbrain both pushed; his pre-lab .agents/ build-notebooks folded into
   the lab repo (build-history/) + pushed (off-machine, ab57a99); visual_test/
   harness in a new local-only GAG demo/ repo (b3bb917) — operator to push to
   swap821/gag-demo himself (agent blocked by exfil guardrail; one-liner given).
8. SUPERBRAIN SHOWS ITS CAPABILITIES (lab faaf087 / product 1967fea): API forwards
   the earned_autonomy SSE event (e9e9e09); aiosAdapter publishes AUTONOMOUS ACTION
   (the brain acts on its own earned trust) + CAPABILITY EARNED (a class graduates)
   + getAutonomy() getter. LIVE-PROVEN: ledger persists across restart (earned:1),
   an earned create_file streams `event: earned_autonomy`. 26 lab + 456 backend tests.

## Single next action
**WHOLE-ai-editor deep analysis: DONE + pushed (2026-06-13, commit 75406b1).**
The 8-lens read-only Workflow (11 agents, ~30min) ran and synthesized the 4
deliverables — all in `.aios/state/`: `SYSTEM_TRUE_PICTURE.md` (whole-system map +
end-to-end request->SSE->cage->audit composition), `HIDDEN_KNOWLEDGE.md` (prioritized
non-obvious findings, file:line-cited), refreshed `PLAN.md` (blueprint-vs-reality +
forward roadmap; supersedes the 06-03 Slice plan), `BACKEND_TRUE_PICTURE.md`
cross-linked as a doc set. Raw lens findings archived in `whole_system_lenses.json`.
Honest totals re-confirmed: 512 passing (457+1skip backend, 29 product, 26 lab), 90%
aios/ coverage. NOTE the P0 finding: a LIVE Bedrock token sits in `frontend/.env`
(gitignored, verified never committed — no repo leak — but rotate+relocate; PLAN H1).

**FUTURE_FRONTIER: DONE + pushed (operator-directed, 2026-06-13).** A 2nd Workflow
(`ai-editor-future-frontier`, run wf_88b1cc68-374, 10 agents): calibre assessment -> 8
futurist specialists (cognitive-arch, recursive-self-improvement, verifiable-trust,
lifelong-memory, edge-frontier-model, symbiosis-interface, multi-agent, category) ->
synthesis into `.aios/state/FUTURE_FRONTIER.md` (725 lines): the north-star ABOVE PLAN.md
(does not replace it). Spine = the **Evidence-Locked Self-Improvement Flywheel** (verified
outcomes -> audit-chain gold corpus -> better local brain+trails -> wider earned autonomy
-> more verified outcomes). 39 recs across 8 themes, horizon-tagged, each grounded in a
named seed + honest risk; roadmap table dovetails PLAN.md; §6 proof demos (Refusal Reel,
flywheel-closes-once, externally-witnessed audit head); §7 honest counterweight. Raw
calibre+advice archived in `future_frontier_advice.json`. Honest headline: frontier-grade
ENGINEERING, not yet a frontier AI SYSTEM — gates are intelligence (7B ceiling) + isolation
(host default), NOT architecture; 3 moves away (better brain S1, default-strong isolation
S2, widened earned autonomy). The ⚠️ "declarative constitution" rec touches frozen core =>
needs explicit operator go + strictly-more-restrictive fail-closed design.

## Next action (open)
Operator to pick the next front. Strongest leverage per FUTURE_FRONTIER queue discipline:
brain/isolation FIRST (PLAN.md S1 quant+14B / S2 default-Docker), then the near-term
proof artifacts (Refusal Reel + Cage Conformance Spec, both [near]). Tier-0 hygiene (H1
rotate the live `frontend/.env` Bedrock token, H2 cruft, H3 doc-currency) is cheap and
should precede any deploy. Per standing rules: restate the chosen item and WAIT for
explicit OK before writing code.

(Background — already complete this session:)
Earned-autonomy feature is now COMPLETE end-to-end + the brain SHOWS it:
- AUTONOMY ⚡N topbar readout (lab dc8116c, additive, live-verified);
- earned grants AUDIT-TAGGED as distinct 'earned-autonomy' hash-chain entries
  with evidence (lab 0e6b253, 457 tests);
- swarm/role-pass caste NARRATION in the terminal (lab 7a89ce1).
Live backend ON :8000 (AIOS_EARNED_AUTONOMY=true, ledger persists earned:1).
DEFERRED (deliberately, low ROI): full 3D swarm-worker viz + a transient SWARM
topbar indicator — swarm turns are rare + 7B-limited; revisit with a 14B+ model.
OPERATOR DECISIONS: (a) whether earned autonomy ships ON by default (config
default is OFF); (b) push GAG demo/ backup to swap821/gag-demo (one-liner given).
Codex reviews earned-autonomy-and-swarm-v1 (handoff msg 17/18) when back ~06-16.

## Open approvals/blockers
- Lease discipline: did all the above with `active_writer: null` (no worktree
  lease held) — §III-A wants the builder to hold it. Operator-authorized, but
  note the gap; reacquire/handoff going forward.
- Codex inbox msg #8 (2026-06-10, correct-resume-stale-runway): unread; his
  process note = "released without hash-pinned handoff, no formal verdict".
- Earned autonomy is ON in the running backend (min=3). Default config is OFF.
- Demo artifacts on disk: swarm_demo.py, earn_demo.py, training_ground/
  wordcount.py + test_proof{1..5}.py (trivial earn-demo files).

## Runtime
Brief: `.venv\Scripts\python agent_coord.py brief --agent claude`
Backend: `.venv\Scripts\python -m uvicorn aios.api.main:app --port 8000`
  (live now with AIOS_EARNED_AUTONOMY=true, CORS incl :3000)
Frontend (lab): `cd "GAG demo/gag-orchestrator"; npm run dev` (:3000)
Tests: `.venv\Scripts\python -m pytest -q`  (baseline 456 passed, 1 skipped)
Autonomy ledger: `GET /api/v1/development/autonomy`
Swarm: POST /api/generate with `"swarm": true`
True picture: `.aios/state/BACKEND_TRUE_PICTURE.md`
