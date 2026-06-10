# RESUME MANIFEST

## Current goal
Return to the Self-Analysis pre-T2 runway now that the coordination era is
landed and the tree is clean.

## Last completed and verified
2026-06-10 — three slices landed on master with operator approval:
- `4532698` AIOS_INTERPRET_ALIGNMENT flag gate (Claude-built; off-mode test
  covers the skip path; provider-returns-None pattern).
- `fdc3d5f` Claude/Codex coordination control plane + operator-approved
  AGENTS.md §III-A (Codex-built, Claude doc clauses; lease/inbox/hash-pinned
  handoff/drift-refused verdicts; live-proven both directions).
- This state commit (RESUME/CEO_LOG/experiences through the landing).
- AGENTS.md was hunk-split across commits 1-2 via temp-copy round-trip
  (hash-verified D78A3A6E… both ways) so each slice carries only its lines.
- Suite on the landed tree: **397 passed / 1 skipped** (verified pre-landing
  on identical bytes). §III-A governance text has explicit operator approval.

## Single next action
Start the Self-Analysis pre-T2 runway, smallest first: report-row dedup
(re-runs accumulate duplicate `open` findings). Route it through
`agent_coord.py` — the 50/50 balancer assigns the builder; the other agent
reviews against the hash-pinned handoff.

## Open approvals/blockers
- None.

## Coordination ledger
Tasks `agent-coordination-v1` and `equal-agent-routing-policy` both APPROVED
(hash-pinned verdicts in coordination.db). `session-checkpoint-claude` and
`land-three-slices` were Claude state/landing leases, released clean.

## Runtime
Brief: `.venv\Scripts\python agent_coord.py brief --agent claude`
Backend: `.venv\Scripts\python -m uvicorn aios.api.main:app --port 8000`
Frontend: `cd frontend; npm run dev`
Tests: `.venv\Scripts\python -m pytest -q`
