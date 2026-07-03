# RESUME MANIFEST

Last updated: 2026-07-03T01:25Z (post-landing addendum: W0-W1 LANDED
f359102; learning seam FIXED cfd40cf — prove_it 7/7 ALL STEPS PROVED;
CI green end to end; wave 2 routed to Codex as frontend-beautification-w2)

## Current Goal
The product thesis was WITNESSED live (operator's browser, his approvals) and
the ten-minute "prove it" path now exists as a shipped artifact. The verify
chain got its deepest fix in weeks (-q/addopts stacking). Two decisions/tasks
are open: the operator's W0-W1 landing word, and the workflow_steps seam
(task_a4019017) that keeps the prover's LEARNING step honestly red.

## FIRST ACTIONS FOR THE NEW SESSION
0. DONE since this manifest's first draft: W0-W1 landed (f359102) on the
   operator's word; the workflow_steps seam fixed+pushed (cfd40cf, prover
   7/7); wave 2 routed to Codex (msg 152). Items 1-2 below are RESOLVED,
   kept for context. NEW next: review Codex's wave-2 handoff when it lands
   (gates on the operator's live eye at :5173); scanner path-entropy RED
   false-positive chip (task_0d074242) awaits an analysis-first session.
1. **W0-W1 landing (RESOLVED — landed f359102):** Codex's beautification slice
   is reviewed + APPROVED by Claude (inbox msg 150, snapshot 66bc378e, all 7
   files verified byte-unchanged; formal verdict blocked only by unrelated
   tree churn from the concurrent prove-it builder). On "land it": commit
   Codex's 7 files + its test as one commit, push, then waves 2-4 unlock.
2. **workflow_steps seam (RESOLVED — cfd40cf, task chip consumed):** granted writes on a
   resume turn emit only tool_result frames; main.py:3823 counts only
   tool_call into workflow_steps -> record_attempt never fires on the clean
   supervised path. Acceptance test: `prove_it.py --scripted` prints 7/7.
3. Backend seams also filed (blueprint §8): approval-resume RE-PLANS through
   the model (caused 9 approval pauses + filename drift reverse_string->
   string_reverser in the witnessed turn); literal default session-id
   fallbacks ('ui-session' etc.) collapse callers into shared memory buckets;
   secret-scanner false-positives on plain filenames.

## Shipped this session (all pushed, CI green through ecf743e's run pending)
- `c69492d` fix(ci): cryptography pin — CI had been red since e8de86b's own
  run was cancelled; audit-recovery Ed25519 tests now run armed on CI.
- `8864501` W3 conformance guard (authority synchronous, never rides the bus;
  five mutation red-proofs) + `c9b88fa` epoch closeout — wonder-epoch
  cortex-bus design doc W1-W3 COMPLETE.
- `9ba2e55` redaction chips in the trail (TDD; the raw [SENSITIVE: hash]
  tokens witnessed live) + `620f4da` beautification blueprint (27 findings
  curated into Codex waves; two audit "P0s" struck as phantoms with ground
  truth recorded in the doc §1).
- `2c686e3` the PROVE-IT PATH: prove_it.py (LIVE + SCRIPTED, honest evidenced
  checklist, .git fenced, exit 0 iff all PROVED) + PROVE_IT.md (witnessed
  browser run) + smoke tests. Its FIRST honest run caught the next bullet.
- `ecf743e` fix(verify): -o addopts= isolates the forced auto-verify from
  inherited pytest.ini addopts (-q stacking -> -qq suppressed the summary ->
  every real auto-verify capped WEAK -> skills could NEVER promote in this
  env). Real-subprocess regression test added (the FakeRunner gap). Prover
  step 6 now PROVED STRONG through the whole production stack.

## The witnessed proof (2026-07-03 ~00:00-00:05 IST, operator's Edge)
Directive typed into the being's chat -> organism honestly REFUSED the
out-of-sandbox path -> corrected -> "Holding for your approval" -> operator
clicked approvals -> scoped writes landed in training_ground/ -> tests pass
6/6 (verified independently). Router served gemini-2.5-flash (cloud), badge
updated live. Dev-events 341-351 carry the whole chain. The turn's
'unverified' ending was the -q defect (now fixed) + re-planning seam (filed).

## Open Approvals / Blockers
- W0-W1 landing word (operator). Codex lease RELEASED; no active writer.
- Wonder organs remain caged; each needs its own operator gate.
- Port landmine STANDS: do NOT run `npm run port`.
- Operator triage pile (pre-existing/untracked): DEEP_AUDIT_REMAINING_REPORT
  +48 lines; AGENTS.md Cowork-import hunk (operator's own text, decide
  keep/drop); repo-root junk ('pointfield_v19/20', '32-char', '7.0', '92pc',
  'Fable', 'None', etc. — shell-quoting artifacts); training_ground scratch
  (reverse_string/string_reverser pairs + two '.[SENSITIVE'-named files);
  .aios/tmp_shots/; .codex/.
- training_ground/.git was corrupted by a workflow builder and SURGICALLY
  REPAIRED (110 snapshots preserved, dirty-tree commit path re-verified).
  prove_it.py + workflow constraints now categorically fence .git.

## Active Files
- prove_it.py · PROVE_IT.md · tests/test_prove_it.py (the demo path)
- aios/agents/tool_agent.py (build_auto_verify_command) ·
  tests/test_auto_verify_strength_regression.py
- .aios/state/FRONTEND_BEAUTIFICATION_BLUEPRINT.md (waves 2-4 queued)
- Codex's uncommitted W0-W1: frontend tokens/chrome CSS ×5 +
  tools/check_css_canon.py + tests/test_frontend_beautification_w0_w1.py

## Notes Not Yet Promoted
- Dev servers: backend :8000 + vite :5173 were RUNNING at closeout (operator
  was viewing live); WebBridge session "witnessed-proof" attached to his Edge.
- Sonnet alias verified claude-sonnet-5; supervision pattern ran 4 workflows
  this session (W3 guard, prove-it ×2, beautification audit) — the audit
  seeded 2 phantom defects into its own lenses (extraction artifact) and the
  verify agent once inverted the CONFIRMED/REFUTED enum while its substance
  said CONFIRMED; Fable ground-truth review caught both. Lesson: never seed
  unverified observations into lens prompts as fact.
