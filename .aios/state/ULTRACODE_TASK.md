# ULTRACODE TASK — current build hand-off

> Single current task ultracode (Claude-web) implements, then opens one focused PR.
> Claude Code (local) reviews on evidence + merges (the #1–#10 loop). Overwritten per task.
> Architecture is decided below — implement it as written; flag (don't silently change) anything wrong.

---

## TASK T3b — review/approve UI for Self-Analysis proposals + audit-before-write hardening

Two clearly-separated parts. Part 1 is a small **backend security hardening** of the T3a apply engine;
Part 2 is the **frontend review/approve UI** (option A's front half). Keep them delineated in the PR.

`aios/security/` untouched throughout.

---

### PART 1 (backend) — audit the APPLY *before* the write (fail-closed)

**Why:** today `SelfApplyEngine.apply` audits the APPLY *after* `git apply`, so a (rare) audit failure
could leave an applied-but-unlogged change. Make it consistent with `edit_file`/`create_file`
(audit-before-write, fail-closed): never write `aios/` without first recording the intent on the ledger.

**Change in `aios/core/self_apply.py`:**
- Move the APPLY audit to **before** the `git apply` write (right after the `before_bytes` snapshot +
  the clean-apply `--check`, but BEFORE the real `git apply`). Make it **fail-closed**: if the audit
  raises/returns no id, **refuse and do NOT write** (`ApplyResult("refused", "audit failed; not applied")`).
  Use a strict audit call here (NOT the best-effort `_safe_audit`). `applied_audit_id` = this entry's id.
- Keep the existing **ROLLBACK** audit on the verify-fail path as best-effort (`_safe_audit`) — the
  restore already happened, so a ledger hiccup there must not crash; the row is `rolled_back` regardless.
- Net flow: load → no-self-approval → zone gate → single-file confine → `before_bytes` →
  `git apply --check` → **audit APPLY intent (fail-closed)** → `git apply` → two-snapshot integrity
  (mismatch → restore + refuse) → verify → pass: `applied`(+`applied_audit_id`); fail: restore +
  best-effort ROLLBACK audit + `rolled_back`.
- **Tests (`tests/test_self_apply.py`):** add `test_apply_blocked_when_audit_fails` — a fake audit that
  raises → `ApplyResult.status == "refused"`, the file is **untouched** (byte-identical to before), the row
  stays `proposed`, and **verify never runs**. The existing happy-path and verify-fail-rollback tests must
  stay green (both still see an APPLY ledger entry; the fail path still sees APPLY + ROLLBACK).

---

### PART 2 (frontend) — the review/approve UI

Surface the `proposed` rows so the whole self-improvement loop is visible + clickable (no curl). Use the
existing T3a endpoints (already merged): `GET /api/v1/self-analysis/proposals?status=proposed`,
`POST …/{id}/apply` `{approvedBy}`, `POST …/{id}/reject`.

**`frontend/src/components/ProposalsPanel.jsx` (NEW):**
- On open, `GET …/proposals?status=proposed` → render a list. Each row shows: `target_path`,
  `finding_type`, `evidence`, a **zone badge** (`RED` red / `YELLOW` amber), and the `proposed_diff`
  rendered with the existing **`DiffView`** component.
- An **`approvedBy`** text input (default `"operator"`); Approve is disabled while it's empty or equals
  `"self_analysis_agent"` (mirror the backend no-self-approval so the UI never sends a doomed request).
- **Approve** → `POST …/{id}/apply` `{ approvedBy }`; show the returned `ApplyResult`
  (`applied` / `rolled_back` / `refused`) with its `reason` + `verify` summary; then refresh the
  list. **Reject** → `POST …/{id}/reject`; refresh.
- **RED proposals:** show them but **disable Approve** with a label like “RED — apply blocked (T4)”
  (the backend refuses RED anyway; the UI must reflect it, not invite a doomed click).
- Loading/empty/error states: a simple spinner, an "No open proposals" empty state, and a visible error
  message on a failed fetch/POST. Match the app's existing visual style (reuse classes/tokens already in
  `App.jsx`/components; do NOT pull in the parked `styles/*.css`).
- **Wire into `App.jsx`:** add a way to open the panel — a new bottom-tab (alongside `terminal`) labelled
  “Self-Analysis”, or an equivalent toggle. Keep it additive; don't disturb the chat/approval flow.

**Tests (`vitest`, mock `fetch`):**
- `ProposalsPanel.test.jsx`: renders a fetched proposal (target_path + the diff via DiffView); Approve
  POSTs to the apply endpoint with the entered `approvedBy` and shows the result; a **RED** proposal
  renders with Approve **disabled**; Reject POSTs to the reject endpoint.

---

### Acceptance
- Backend: full `pytest -q` green (Windows baseline **215 passed / 1 skipped**; +1 audit-fail-closed test).
  **Cloud (Linux) note:** the 2 pre-existing environmental `test_security.py` failures are NOT yours —
  confirm identical with changes stashed.
- Frontend: `eslint` clean · `vitest` green (existing + the new ProposalsPanel tests) · `vite build` green.
- `aios/security/` untouched. One focused PR (Part 1 backend + Part 2 frontend, clearly separated).
- Title: `Self-Analysis T3b: proposal review/approve UI + audit-before-write hardening`.

---

## Runway after T3b
- **T4 — core edit (RED, frozen):** `aios/security/*` is already RED-refused by T3a's zone gate; T4 is the
  explicit policy + surfacing it in the UI (show RED proposals as permanently review-only). Small.
- Then the marquee Self-Analysis module (T0–T4) is COMPLETE.
- Parallel: the **BREATHE** retry (sandbox, prompt #1 "use the edit_file tool").
- OPS tech-debt (tiny PR sometime): `testpaths = ["tests"]` so bare `pytest` ignores the `training_ground/`
  breath seed.
