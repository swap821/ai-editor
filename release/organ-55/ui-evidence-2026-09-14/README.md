# Truthful-UI live evidence — real browser, real operator session

**Date:** 2026-09-14
**Method:** Kimi WebBridge driving the operator's own Chrome against
`http://localhost:5173` with a live backend on `localhost:8000`.
**Residual this addresses:** *"browser-session — truthful UI live evidence
requires operator browser session at :5173 (not inventable headless)"*

This is a real browser with a real, server-issued operator session — not a
headless render and not a mock. The session was established through the actual
`enroll → login → reauth` ceremony (201 / 200 / 200) from the page itself.

## What it found: the truthful UI was blind, and truthfully said so

`frontend/src/superbrain/lib/aiosMirror.ts` — the file whose own header reads
"Live backend connection for the truthful Living Mirror" — reached the backend
over two transports and **carried the operator session on neither**:

```ts
await fetch(`${AIOS_BASE}/api/v1/mirror/snapshot`);   // no credentials
new EventSource(streamUrl);                            // no withCredentials
```

Both are bonded reads. The backend answered, correctly:

```
401 this route requires a bonded operator session;
    loopback alone is a network path, not an identity
```

So a browser holding a perfectly good operator session rendered **"Control plane
unavailable"** forever. The surface was being *truthful about a blindness it was
inflicting on itself*.

Proven in the browser rather than argued from the code: with the session live,
`fetch(..., {credentials:'include'})` returned **200** while the bare `fetch(...)`
was rejected outright.

`aiosAdapter.ts` — its sibling — has always sent credentials and asserts it in
`aiosAdapter.session.test.ts`. This file simply never got the same treatment, and
no test could catch it because mocked transports cannot notice a missing cookie.

### Fixing it half-way was visible on screen

Adding `credentials` to the snapshot fetch alone left the page in a split state:
**"Models participating"** flipped from `Unavailable` to a measured `0` while
**"Control plane"** stayed `offline` — because those two read from *different
transports* and only one had been taught to carry the session. That is what sent
me back for the `EventSource`.

## The three states, each captured live

| file | state | what the UI shows |
|---|---|---|
| `ui-01-booted.png` | **unavailable / never bonded** | `Control plane: offline · UNAVAILABLE`, `Models participating: Unavailable`, red banner *"Control plane unavailable — Ambient life continues without claiming backend activity"*, sovereignty row reads `unbound` |
| `ui-05-online.png` | **connected** | `Control plane: online · MEASURED`, every tile `MEASURED`, green banner *"Sovereign spine connected"*, sovereignty row bound to `operator:dd47ad8e73304` |
| `ui-06-disconnected.png` | **was connected, now disconnected** | red `● offline` badge appears top-right, banner returns to unavailable, **operator binding retained**, last-measured values held rather than blanked |

That satisfies C8's requirement literally — *"BOTH an unavailable case and a
distinct error/stale/disconnected case"* — and the third state is genuinely
distinct from the first: one has no operator and reads `Unavailable`, the other
keeps the operator and keeps its last readings while flagging the loss.

The UI never invents a number in any of the three. That is the property these
organs claim.

## Scope — what this does and does not cover

**Directly exercised:** the Living Mirror snapshot/stream path
(`/api/v1/mirror/snapshot`, `/api/v1/mirror/stream`) — organs **20** and **48**.
The bug was in their own transport, and the fix is verified end to end
(`401 → 200 OK` in the backend log).

**Only incidentally observed:** organ **49**'s approval tile (`Approval: none
reported · MEASURED`) and organ **51**'s sovereignty row (`auto/supervised/unbound`
→ `offline/supervised/operator:…`) appear correct and live in these captures,
but neither was driven through its own surface. Screenshot calls began failing
partway through — the daemon/extension version mismatch the skill warns about —
and rather than retry a flaky path I stopped.

**So 49 and 51 keep a narrowed residual naming exactly what is missing, rather
than borrowing a pass from the home screen.**

## Regression cover

`aiosMirror.test.ts` now asserts `credentials: 'include'` on the snapshot fetch
and `withCredentials: true` on the stream, and the pre-existing cursor test
asserts the stream's second argument too — so the check cannot be satisfied by a
call that has quietly lost the session again.
