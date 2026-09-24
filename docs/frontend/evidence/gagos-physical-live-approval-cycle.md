# GAGOS Physical Embodiment — Live Approval-Hold Evidence

Captured 2026-09-24 against the disposable backend started from this worktree.

## Run

- Backend data lived in a fresh temporary `AIOS_DATA_DIR` and was deleted after
  the run. The enrollment credential remained process-only; it was not printed
  or persisted.
- `POST /api/v1/auth/session` returned `200` with a cookie-backed session.
- `POST /api/v1/auth/enroll` returned `201`; the one-time credential was used
  immediately, without being recorded.
- `POST /api/v1/auth/login` returned `200`.
- `POST /api/v1/auth/reauth` returned `200`.
- `GET /api/v1/auth/session` returned `200` for the authenticated operator.
- An authenticated `POST /api/generate` returned `200` and streamed:
  `turn.started → alignment → step → plan → text_chunk → route → step →
  human_required`.

The requested action was deliberately narrow: create exactly one new file at
`training_ground/physical-embodiment-live-approval.txt` with one evidence line.
The `human_required` payload reported `requiresApproval=true`, contained a
server-issued approval token, and identified that exact creation target. The
file was still absent from the repository after the stream ended.

## Interpretation

This is live evidence that an authenticated physical-intent turn reaches the
real YELLOW approval hold, rather than being represented only by a deterministic
fixture. It proves the no-write boundary at the hold: no approval replay was
sent, so no file was created. The disposable service and all temporary data
were stopped and removed afterward; port 8000 was left unused.

The generation capability is route-bound and is replayed through
`/api/generate`; the generic `/api/v1/approval/req` endpoint is for command
capabilities, so it was not misused to claim a rejection of this file token.
This run therefore does not claim approved execution, forced verification,
worker lifecycle coverage, hardware performance, accessibility, or human visual
acceptance.
