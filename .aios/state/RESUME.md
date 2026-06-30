# RESUME MANIFEST

Last updated: 2026-06-30T21:37Z

## Current Goal
Address Claude's non-builder birth-proof review, land the fixes, confirm GitHub
CI, then hand off for re-review. Do not declare "born" until GitHub CI,
non-builder approval, and operator browser acceptance are complete.

## Last Completed + Verified
- Claude's review artifact is tracked at
  `.aios/state/BIRTH_PROOF_REVIEW_2026-06-30.md`; Codex response is
  `.aios/state/BIRTH_PROOF_RESPONSE_2026-07-01.md`.
- Findings closed locally:
  real browser approval loop (no injected approval), durable httpOnly sessions
  across backend restart, backend stdout/stderr proof logs, restore-capable
  Council rollback IDs, GLB spec/gloss warning suppression, local runtime DB
  ignore hygiene, and CouncilDashboard glass canon drift.
- New real browser proof:
  `.aios/tmp/birth-browser-proof-20260630-212617/birth-browser-proof.json`.
  It captured a backend `human_required` SSE frame, clicked the visible
  authorize button, replayed the same server token (`joHh7-HGjKVd...` prefix),
  landed the scoped edit, stayed authenticated after backend restart, captured
  non-empty backend logs, and saw no `KHR_materials_pbrSpecularGlossiness`
  warning.
- Local gates passed:
  backend coverage gate `89.12%`; frontend `npm run typecheck`;
  frontend `npm run test -- --run` (`63` files / `376` tests); frontend
  `npm run build`; `tools/check_css_canon.py`; `tools/check_canon_frozen.py`;
  and `git diff --check`.

## Single Next Action
Commit and push the review fixes, watch GitHub CI to green, then run
`python agent_coord.py handoff birth-local-browser-proof --from codex --to claude`
with the proof paths and commit hash.

## Open Approvals / Blockers
- GitHub CI has not yet run for this uncommitted fix set.
- Product birth remains gated by GitHub CI, non-builder re-review, and the
  operator's own browser acceptance; Codex cannot self-certify it as born.

## Active Files
- Review fixes: `.gitignore`, `aios/api/main.py`, `aios/config.py`,
  `aios/core/session_manager.py`, `aios/runtime/snapshots.py`,
  `aios/runtime/spawner.py`, `frontend/src/superbrain/lib/brainScene.ts`,
  `frontend/src/workbench/CouncilDashboard.css`, `frontend/vite.config.js`,
  and the matching backend tests.
- Continuity/review docs: `.aios/state/BIRTH_PROOF_REVIEW_2026-06-30.md`,
  `.aios/state/BIRTH_PROOF_RESPONSE_2026-07-01.md`,
  `.aios/state/RESUME.md`, `.aios/memory/experiences.jsonl`.
