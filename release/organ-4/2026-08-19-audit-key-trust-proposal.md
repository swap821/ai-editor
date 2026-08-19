# §VIII PROPOSAL — organ 4: the audit chain trusts keys it stores

**Status: PROPOSAL ONLY. No code in `aios/security/` was changed.**

`aios/security/audit_logger.py` is frozen core. AGENTS.md:186 — *"Any change to
it follows the full §VIII flow … a fix may be **proposed** for human review, but
**applying** one is RED/blocked."* Verified mechanically before writing this:

```
RED     aios/security/audit_logger.py   -> frozen core path blocked
```

This document is the *Propose* step. It stops there.

## Finding

`verify_chain` loads every verification public key from the database it is
verifying (`audit_logger.py:724`):

```python
for row in conn.execute("SELECT key_id, public_key_hex FROM audit_keys"):
    pub_keys[int(row["key_id"])] = Ed25519PublicKey.from_public_bytes(...)
```

`audit_keys` lives in `self.db_path` — the same SQLite file that holds
`tamper_audit_trail`. There is **no verification key pinned outside that file**;
a search for a trusted/pinned/expected public key in the module returns nothing.

The signing side is correct and should not change: the private key is volatile,
read from `AIOS_AUDIT_PRIVATE_KEY` (`audit_logger.py:81`, `:198`), never
persisted — exactly what AGENTS.md §VII.4 requires. **But a volatile signing key
protects signing, not trust.** Verification asks the artifact under suspicion who
is allowed to vouch for it.

## Consequence

An attacker who can write the audit database can:

1. rewrite or delete rows in `tamper_audit_trail`;
2. generate their own Ed25519 keypair and `INSERT` the public half into
   `audit_keys`;
3. re-sign the forged entries with their private half;
4. recompute the hash chain over the forged rows;
5. rewrite the in-DB tip anchor (`audit_tip_anchor`, `audit_logger.py:118`).

`verify_chain` then loads the attacker's key at line 724 and reports the forged
chain as valid, with `tip_anchor_valid=True`.

The module already knows the answer — its docstring says `get_anchor` exists for
*"external trust-anchor publication (blockchain, CT log, etc.)"* — but the
verifier never consults anything external, so the property depends on an
operational step outside the code and is not enforced by it.

### Threat model, stated honestly

This requires **write access to the audit DB**. It is not a remote bypass, and
an attacker with arbitrary host write access has other paths. It matters because
tamper-evidence is precisely the property that is supposed to survive that
attacker: an audit log whose verifier can be convinced by the same write that
forged it is a record, not evidence.

It is also newly reachable in practice: until today's executor fix (same PR), a
sandboxed container could write anywhere in the repo, `.aios/` included.

## Proposed fix, for human review

1. **Pin trust outside the database.** Verify against a public key supplied by
   the environment (`AIOS_AUDIT_PUBLIC_KEY`), or derived from
   `AIOS_AUDIT_PRIVATE_KEY` when that is present. Keys read from `audit_keys`
   are treated as *identifiers*, never as *authority*.
2. **Rotation stays possible.** Accept a pinned set, or require that each
   `audit_keys` row be signed by a pinned key — rotation is a real requirement
   (`audit_logger.py:19`, `:541`) and must not be traded away.
3. **Degrade loudly.** With no pinned key configured, report the chain as
   `signatures_unverified` rather than valid — *unavailable rather than a
   plausible zero*, which is the C5 rule this organ already claims.
4. **Publish the anchor.** `get_anchor` should be exported on a schedule to
   somewhere the attacker does not control; the in-DB anchor cannot anchor
   itself.

## What the operator is being asked

Whether to authorise a §VIII change to a frozen-core file. Nothing here is
urgent enough to justify bypassing that flow, and the ledger is **not** being
edited on the strength of this document: organ 4 keeps its current status until
a decision is made, because a finding is not a demotion and a proposal is not a
fix.

Applying this fix without that authorisation would be exactly the failure the
frozen core exists to prevent — an agent editing the module that adjudicates it.
