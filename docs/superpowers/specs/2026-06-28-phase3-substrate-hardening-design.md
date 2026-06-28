# Phase 3 — substrate hardening (audit ledger + secret scanner)

Date: 2026-06-28
Status: Approved (operator; full scope — "perfect phase 3"). FROZEN-SPINE change
authorized by the operator as a deliberate §VIII hardening (Human Review→Approve
before land); strengthen-only.
Branch target: `council-runtime-v01` → fast-forward `master` on green

## Goal

Make the tamper-evidence the entire governance-and-learning story rests on actually
hold. The audit ledger is already Ed25519-signed + SHA-256 hash-chained; this closes
its two real residual gaps and broadens the (already strong) secret scanner — so the
"tamper-evident" claim is honestly earned (Phase 0 honesty thesis).

## Authorization + invariants (frozen spine)

`aios/security/audit_logger.py` + `secret_scanner.py` are the FROZEN RED spine
(AGENTS.md §VIII). Edits here are permitted ONLY via the full §VIII flow with the
operator's explicit approval and must **only strengthen**. Hard rules:
- **Never weaken a guardrail.** Every change adds detection/integrity; none removes.
- **The runtime self-modification refusal is untouched** — the AI-OS still cannot
  edit its own spine (`self_apply` `frozen_subdirs=("security",)`, `SCOPE_ROOTS`
  RED). This is a *developer* §VIII change, not a product self-edit.
- **Non-breaking:** existing ledgers must still verify (no false "tampering").

## What's already done (verified in code — scope refocus)

The 2026-06-27 A+ hardening already closed most of the 2026-06-21 audit's scanner
claims: the scanner has PEM private keys, `scheme://user:pass@` URL creds
(`CONNECTION_STRING`/`DATABASE_URL`), JWT, every major provider key, bearer, 40-char
AWS secret, assignment patterns, entropy + sliding-window base64. So the scanner work
is small; the ledger gaps are the real Phase 3.

## Design

### 1. Collision-resistant chain preimage — VERSIONED, non-breaking
`compute_entry_hash` concatenates `previous_hash+timestamp+actor+payload+zone` with no
delimiter, so different field splits collide (e.g. `actor="ab",payload="c"` ==
`actor="a",payload="bc"`). The Ed25519 signature (over canonical JSON) already
mitigates exploitation, but the chain hash itself must be unambiguous.
- `compute_entry_hash(..., *, version: int = 2)`:
  - **v1** (legacy): the current concat — KEPT, so pre-existing entries still verify.
  - **v2**: `sha256(canonical_json({previous_hash, timestamp, actor, action_payload,
    security_zone}))` — sorted-key JSON is unambiguous; no field-boundary collision.
- Schema: add `hash_version INTEGER NOT NULL DEFAULT 1` to `tamper_audit_trail` via an
  ALTER-if-missing migration in `init_audit_db` (existing rows → v1).
- `log_action`: compute v2, store `hash_version=2`.
- `verify_chain`: recompute each entry's hash under ITS stored `hash_version` (absent
  → 1). A mixed v1/v2 chain verifies; tampering is still caught (recompute ≠ stored).
- Signatures are unchanged (already canonical-JSON; they cover the stored
  `current_hash`, so no signature versioning is needed).

### 2. Tail-truncation detection — signed tip-anchor
`verify_chain` validates genesis→tip, so deleting the latest N entries leaves a valid
shorter chain. Add an external anchor to the tip:
- New table `audit_tip_anchor` (single row, `anchor_id=1`): `tip_entry_id`, `tip_hash`,
  `signature`, `key_id`, `updated_at`.
- `log_action` (SAME transaction as the append): upsert the anchor to the new entry —
  `tip_entry_id=entry_id`, `tip_hash=current_hash`, Ed25519-signed over
  `canonical_json({tip_entry_id, tip_hash})`.
- `verify_chain` (when verifying to the tip, `to_id is None`): after the pass, compare
  the actual tip (`MAX(entry_id)` + its `current_hash`) to the anchor and verify the
  anchor signature. A PRESENT anchor that mismatches → truncation/tamper →
  `valid=False`, `reason="tail truncation detected"`. A MISSING anchor (legacy DB /
  manually-inserted rows) → `tip_anchor_valid=None`, does NOT fail (back-compat).
  `ChainStatus` gains `tip_anchor_valid: Optional[bool] = None`.
- **Honest limitation (documented):** the anchor is in the same DB, so an attacker
  with the signing key can re-sign a truncated anchor. It raises truncation to the
  same bar as signature forgery (key required) — a real strengthening for the local
  threat model; true immutability needs external anchor publication (out of scope).

### 3. Secret scanner — broaden PEM + close the short-key gap (low-FP only)
- **PEM:** generalize to
  `-----BEGIN [A-Z0-9 ]*PRIVATE KEY( BLOCK)?-----[\s\S]*?-----END [A-Z0-9 ]*PRIVATE
  KEY( BLOCK)?-----` — covers `ENCRYPTED`, `PGP … BLOCK`, and any future header.
  Zero false-positive risk (PEM markers are unambiguous).
- **Short hex / bare key:** add a CONTEXT-GATED detector only — a hex/token value of
  8+ chars immediately following a secret keyword + `=:` separator (closes the gap
  below `ASSIGNED_SECRET`'s 12-char floor, e.g. `api_key: deadbeef1234`). Keyword
  gating keeps false positives near zero. **NOT** a bare/un-gated short-hex detector
  (that would over-redact git SHAs, IDs, colors — a correctness regression, the
  opposite of "perfect").

## Error handling / fail-closed
- Any verify ambiguity → reported as invalid (fail-closed), never a silent pass.
- Migration is additive + idempotent; absent column/anchor → legacy behavior, never a
  false failure.
- Scanner additions only ever redact MORE; redaction stays non-reversible.

## Testing (Verifier owns; adversarial)
- **Collision:** a v1-colliding `(actor,payload)` pair → DIFFERENT v2 hashes.
- **Versioned verify:** a chain mixing a v1 row and v2 rows verifies; editing any
  field still flips `valid=False` at the right entry.
- **Tail-truncation:** append entries via `log_action`, delete the last row → a full
  `verify_chain` reports truncation (`tip_anchor_valid is False`, `valid=False`); an
  intact chain → `tip_anchor_valid is True`.
- **Anchor tamper:** mutate the anchor row → detected.
- **Scanner:** `ENCRYPTED`/`PGP` PEM blocks redacted; `api_key: deadbeef1234`
  redacted; a bare git SHA in prose (no keyword) is NOT redacted.
- Full existing security + audit suites stay green; 85% floor; the runtime
  frozen-spine refusal test still passes (we don't touch that path).
- Then a full multi-agent adversarial review (the integrity core warrants it).

## Rollout
No flag. Additive migration on `init_audit_db`. New entries are v2 + anchored;
existing chains keep verifying under v1. Operator approval required before land
(§VIII). After Phase 3: Phase 4 (the front door).
