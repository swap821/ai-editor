# RESUME MANIFEST

Last updated: 2026-06-30T17:23Z

## Current Goal
Birth-readiness P0 hardening is landed and GitHub-green; the local-browser
birth proof has now been witnessed against an isolated runtime. A CI hotfix is
in progress for the rollback approval false positive exposed by run
`28462607128`. Do not declare "born" until CI is green, non-builder review, and
operator visual acceptance are complete.

## Last Completed + Verified
- Local/browser proof continuity was committed and pushed as `793adc1`
  (`docs: record local browser birth proof`). GitHub CI run `28462607128`
  passed frontend but failed backend on
  `test_rollback_endpoint_uses_cookie_session_without_body_session`.
- Root cause: a legitimate rollback snapshot SHA
  `362869006241aca05ad0219b818267172ec2e53d` contained `ec2`, so the broad
  AWS-secret regex classified the approval payload as credential-like when the
  durable approval store scanned `{"snapshot_id": ...}` before persistence.
- Hotfix applied locally: `ApprovalStore` now scans a copy of rollback payloads
  with valid 40-hex `snapshot_id` normalized to `<rollback-snapshot-sha>`, while
  preserving the exact persisted payload and still refusing extra secret fields.
  Regression tests were added in `tests/test_approvals.py`.
- Local verification passed: `tests/test_approvals.py -q`,
  `tests/test_api.py::test_rollback_endpoint_uses_cookie_session_without_body_session -q`,
  and full backend gate
  `.venv\Scripts\python.exe -m pytest -q --cov=aios --cov-report=term-missing --cov-report=xml --cov-fail-under=85`
  exited `0` with total coverage `89.20%`.
- Local Chrome DevTools proof loaded `http://localhost:5173` against backend
  `http://localhost:8000`: WebGL canvas rendered (`2133x1356` backing pixels),
  session became authenticated through httpOnly cookie flow
  (`cookieBased=true`, `sessionId=null`, `document.cookie=""`), and the
  approval surface rendered via `window.__injectApproval`.
- Browser artifacts are under
  `.aios/tmp/birth-local-browser-proof-20260630-223039/`: initial screenshots in
  `screens/`, post-restart mission screenshots in `screens-after-restart/`,
  and JSON evidence in each `browser-proof.json`.
- Live supervised Council loop passed with strong evidence: mission
  `mission-943967ce806a` originated -> `awaiting_approval` -> King approval
  scheduled execution -> worker touched only `target_strong.txt` -> forbidden
  probe `backend/blocked_probe.txt` was blocked -> verifier ran
  `.venv\Scripts\python.exe -m pytest tests --no-cov`, exited `0`, emitted
  `1 passed`, and reported `verificationStrength=STRONG`,
  `verificationMeetsFloor=true`. Evidence:
  `.aios/tmp/birth-local-browser-proof-20260630-223039/council-proof-strong.json`.
- Restart persistence passed: backend was stopped and restarted against the same
  proof data dir; mission `mission-943967ce806a` still returned `completed` with
  `STRONG` verification and the post-restart browser page displayed the persisted
  Council report (`completed`, `approve`, `VERIFY STRONG`). Evidence:
  `.aios/tmp/birth-local-browser-proof-20260630-223039/restart-proof.json`.
- Earlier mission `mission-b17577c72839` also completed but its scratch verifier
  was correctly marked `WEAK` because coverage defaults hid the pytest pass
  count; this was superseded by the strong mission above.
- Proof backend/frontend processes were stopped after capture; no listening
  process remains on ports `8000` or `5173`.

## Single Next Action
Commit and push the rollback approval false-positive hotfix, watch the new
GitHub CI run to success, then hand off `birth-local-browser-proof` for
non-builder review with the proof paths above.

## Open Approvals / Blockers
- Current blocker: GitHub CI must be made green after run `28462607128` failed.
- Product birth remains gated by non-builder review plus the operator's own
  browser acceptance; Codex cannot self-certify the organism as born.

## Active Files
- Continuity files to update/commit if desired:
  `.aios/state/RESUME.md`. Hotfix files: `aios/core/approvals.py`,
  `tests/test_approvals.py`. Proof artifacts remain ignored under `.aios/tmp/`.
