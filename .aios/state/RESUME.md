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

## Single next action
COORDINATION CATCH-UP (this session lapsed it): leave Codex a POST-HOC review
note for the earned-autonomy + swarm features (his to review as non-builder),
hash-pinned; mark his unread inbox msg #8 read; keep RESUME current. THEN, real
follow-ups: (a) tag earned-autonomy auto-grants explicitly in the audit
hash-chain (currently audited as the write, not labelled 'earned-autonomy');
(b) the swarm/castes need a 14B+ local model to sustain multi-role output
(7B-limited); (c) decide whether earned autonomy stays on in product.

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
