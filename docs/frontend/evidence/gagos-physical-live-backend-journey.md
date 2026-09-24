# GAGOS physical embodiment — authenticated backend journey

Captured 2026-09-24 in a fresh disposable `AIOS_DATA_DIR`; the one-time
operator credential was held only in the streaming client process and was not
written to the repository or evidence.

## Journey

1. `POST /api/v1/auth/session` with the exact frontend Origin returned `200`,
   `authenticated=true`, and `cookieBased=true`.
2. `POST /api/v1/auth/enroll` returned `201` and an operator id. The returned
   enrollment credential was immediately used and never printed or persisted.
3. `POST /api/v1/auth/login` returned `200`, `authenticated=true`.
4. `GET /api/v1/auth/session` returned `200`, an authenticated operator, and a
   session-bound CSRF token.
5. An authenticated `POST /api/v1/chat` with `modelId=auto` returned
   `200 text/event-stream` and emitted the measured sequence:

   `turn.started → human_state → representative_context → route → text_chunk`
   (repeated) `→ done`

6. The authenticated `GET /api/v1/mirror/snapshot` returned `200` with
   `phase=idle`, `status=online`; no unmeasured physical or authority state was
   inferred from the response.

This proves a real authenticated backend turn and terminal replay boundary. It
does not prove that every backend worker/approval/verification posture has
been driven through the browser, nor does it replace the remaining human and
long-run performance acceptance.
