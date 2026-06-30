# RESUME MANIFEST

Last updated: 2026-06-30T10:54Z

## Current Goal
Birth-readiness P0 hardening is ready to land from local `master`
(`origin/master` base `e70dee8`). Codex reclaimed the worktree under
`birth-readiness-p0-fixes`, did a review pass, fixed one additional rollback
target-binding edge, reran gates, and witnessed the live supervised Council loop.

## Last Completed + Verified
- Rollback now requires a validated session cookie or fallback session and a
  one-shot rollback approval token bound to the exact snapshot SHA. Review caught
  and fixed the omitted-`snapshotId` case so "previous snapshot" is resolved at
  approval time, not execution time.
- Browser frontend no longer exposes `NEXT_PUBLIC_AIOS_TOKEN`; it uses httpOnly
  session cookies with a verified fallback body session only when cookies fail.
- Deterministic workers now require verification commands and report failed
  verification as `failed`; LLM workers still require verification before success.
- `request_change` is denied unless the MissionContract allows the tool, and the
  Security Queen requires explicit `metadata.model_policy`.
- Real CI now runs `pip_audit` and `npm audit`; tracked scratch probes were
  deleted and local live-proof artifacts are ignored.
- Local gates after review fix: backend full pytest coverage gate passed at
  89.19%; frontend typecheck passed; Vitest passed 63 files / 376 tests; frontend
  build passed; `pip_audit -r requirements.txt` and `npm audit --audit-level=high`
  were clean; `git diff --check` passed.
- Live supervised-loop witness passed on a temporary backend at
  `127.0.0.1:8019`: mission `mission-a579d8114766` originated -> reached
  `awaiting_approval` -> King approval scheduled execution -> worker touched only
  `target.txt` -> verifier exit `0` -> final report `completed`.

## Single Next Action
Commit this patch on `master`, push to GitHub, watch the pushed GitHub Actions CI
run to completion, then harden repository governance (branch protection/required
CI plus Dependabot/security settings where permissions allow).

## Open Approvals / Blockers
- No code blocker. `pip check` remains red only because this local Python 3.14.5
  venv has several packages whose metadata does not support the platform,
  including pre-existing local `torch 2.12.0`; CI targets Python 3.11 and the
  vulnerability audits are clean.
- Product birth is still not public-ready until GitHub CI and repository
  governance are confirmed on the pushed commit.

## Active Files
- Backend/session/security: `aios/api/main.py`, `aios/runtime/worker_entry.py`,
  `aios/runtime/worker_api.py`, `aios/council/queens/security.py`
- Frontend/session: `frontend/src/superbrain/lib/aiosAdapter.ts`,
  `frontend/src/superbrain/lib/sessionId.ts`, related tests/config docs
- Dependency/CI/docs: `.github/workflows/ci.yml`, `requirements.txt`,
  `frontend/package*.json`, `README.md`, `.aios/state/PLAN.md`,
  `.aios/state/RENOVATION_PLAN.md`
