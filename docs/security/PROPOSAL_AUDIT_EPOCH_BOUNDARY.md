# Proposal (§VIII): an operator-signed epoch boundary for the audit chain

*Status: PROPOSED 2026-10-19, not applied. `aios/security/audit_logger.py` is
frozen core (organ 4, spine). Only the operator decides and applies it.*

## Observe (measured 2026-10-19, live install)

`python -m aios audit verify` reports: 780 entries, `valid: false`, "Invalid
Ed25519 signatures detected". The rebuild drill (`docs/operations/REBUILD_DRILL.md`)
surfaced it, because `doctor`'s required `audit_integrity` check is fatal.

| Entries | Dates | Signed | Verdict today |
|---|---|---|---|
| 1–351 | 2026-06-02 to 06-29 | **no** (before audit signing existed) | counted invalid |
| 352–780 | 2026-06-29 to 09-21 | yes, by **76 per-process keys** | verify, but only against keys the database lists about itself |

- **The chain itself is sound.** Hash links are unbroken and the tip anchor
  is valid. This is not tampering.
- **Two rules, each right on its own, make the chain permanently red:**
  1. **An unsigned entry counts as a stripped signature** (2026-08-19). It
     blocks the downgrade attack: forge the payloads, recompute the chain,
     delete the signatures. A verifier cannot tell a pre-signing entry from a
     stripped one, so all 351 genuine June entries fail, forever.
  2. **Trust is unanchored.** No `AIOS_AUDIT_PRIVATE_KEY` is stored (not in
     the keystore's list, `.env` or the environment). Every backend process
     therefore signs with a key it generated at startup.
     - Verification can only use keys the audited database supplies itself.
     - Pinning a key (`AIOS_AUDIT_PUBLIC_KEY`) would turn entries 352–780 red
       as well: by design, only pinned keys count once one is pinned.

So **anchoring trust cannot be done without first deciding what the history
before the anchor means.** The two decisions are one decision.

## Propose: an epoch boundary the operator signs

The operator signs, with the spine release key he already holds, a record of
three things: **"the chain up to entry N has head hash H, at commit C"**.
Verification then:

- **Up to N:** checks hash links only. A tampered early entry changes H, so it
  is still detected. Signatures are not required there.
- **After N:** requires a signature under a **pinned** key, with unsigned
  entries counted as stripped, exactly as today.

The boundary is stored outside the audited database, in
`.aios/state/audit_epoch_boundary.json`, signed and committed like the spine
attestation. A boundary that does not verify means verification proceeds as
today, i.e. fails closed.

**Operator steps, once:**
1. Store a persistent audit key. The keystore learns the name
   `AIOS_AUDIT_PRIVATE_KEY`; `keys generate` and `keys set` are his act.
2. Restart the backend, so new entries are signed by that one key.
3. Sign the boundary at the current tip. A new
   `spine_release_attest.py audit-boundary` command, TTY-only and confirmed
   with `approve` like `sign`, records N, H and C.
4. Set `AIOS_AUDIT_PUBLIC_KEY`, or rely on the private key's public half.
   Verification is then anchored.

## Alternatives considered

- **Re-sign entries 1–780 with the new key.** Rejected: it fabricates
  signatures for events nobody signed at the time. That is exactly the
  laundering a tamper-evident log exists to prevent.
- **Exempt unsigned entries before 2026-06-29 by date.** Rejected: the
  timestamp is a column in the database under suspicion, so an attacker
  would just backdate.
- **Leave it.** `doctor` stays red forever, and red-forever is ignored. The
  real alarm then has nowhere to go.

## Tests to land with it

- A boundary signed by an unpinned key does not verify, and the chain fails
  closed.
- An early entry edited after the boundary is caught by the hash at N.
- An unsigned or ephemerally signed entry **after** N is still invalid.
- No boundary file: behaviour is exactly today's.
- The spine-mutation probe gains entries for every new decision point.

## Decision needed

1. The boundary design as above, or another treatment of pre-anchor history.
2. Whether the boundary is signed with the spine release key (no new key) or
   a separate audit key.
