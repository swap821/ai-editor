# The UI still boots unbonded — verified in a browser — 2026-09-06

This closes the one bar from the invariant-I plan that reasoning could not
satisfy:

> **The UI must still boot unbonded** and be able to open the bond ceremony. If
> it cannot, the allowlist is wrong.

Privileged reads now require a bonded operator session. If the allowlist were
even slightly wrong, the app would be a locked door with the key inside: unable
to render far enough to reach the ceremony that grants the bond.

## Method

A real browser (Chrome headless, CDP), against a backend with **no operator
enrolled at all** — the hardest case, since there is no bond to present.

```
backend  127.0.0.1:8000   fresh AIOS_DATA_DIR, unbonded
frontend localhost:5173   npm run dev (CORS requires this exact origin)
```

## Result: passes

**The shell renders.** All five tabs present (Living Mind, Workbench,
Governance, Operations, History), and the app degrades honestly rather than
erroring:

```
Control plane      offline      UNAVAILABLE
Models participating Unavailable MEASURED
Approval           none reported MEASURED
"Control plane unavailable -- Ambient life continues without claiming backend activity."
```

That banner is the correct behaviour: the UI says it cannot see the control
plane instead of inventing a status. An unbonded caller genuinely cannot read
those routes any more.

**The bond ceremony opens.** The trigger is present and live:

```
trigger found   label="unbound"   aria-expanded="false"
after click     aria-expanded="true"
panel text      SOVEREIGN BOND · ONE HUMAN
                "GAGOS serves exactly one human. No sovereign session is ..."
```

Screenshots: `ui-unbonded.png`, `ui-ceremony-open.png` (session scratch).

## Why this needed a browser and not an argument

I had already reasoned it would work: `fetchOnboardingState` returns an empty
state on `!res.ok`, and the allowlist was derived from what `SovereigntyPanel`
calls. That reasoning was right — but it was reasoning, and the bar said
*verify*. The same reasoning would have produced the same confident answer if
the allowlist had been missing `/api/v1/auth/session`, in which case the
ceremony could not have reported bond status at all.

## Companion measurement

The full read surface, same tree, unauthenticated:

```
readable unauthenticated:  5 / 54   (was 39 / 54 before the fix)
  /api/v1/auth/session
  /api/v1/models/{auto,bedrock,gemini,local}

/api/v1/mirror/governance  200 but self-censoring (constitution.version = unavailable)
/api/v1/mirror/snapshot    401
/api/v1/mirror/executor    401
```

Exactly the declared allowlist, and the mirror exemption behaves as designed:
the one route that authorises per field is served, its siblings that authorise
nothing are refused.
