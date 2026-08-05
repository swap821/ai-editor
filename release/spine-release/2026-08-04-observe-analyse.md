# §VIII Observe / Analyse — frozen security spine (organs 1–5)

**Prepared:** 2026-08-04 · **At commit:** `d7fd7217` · **Prepared by:** agent
(Claude Opus 5) · **For:** operator review under `AGENTS.md` §VIII
`Observe → Analyse → Propose → Test → Verify → **Human Review → Approve** → Deploy`

This is the *Observe/Analyse* deliverable. It exists so the operator's approval is
given over verified facts rather than over an agent's assurance. Everything below
was checked against code and test runs at this commit, not transcribed from the
ledger — the ledger is what is under review, so quoting it back would prove
nothing.

**Nothing in this document changes any organ's status.** Counts at time of
writing: `54 total, 46 green, 8 yellow`.

---

## Method

For each organ: locate the owner class in its declared production entrypoint,
read the code behind its load-bearing condition (the fail-closed / tamper-evident
claim), and execute every test the ledger cites. A path that resolves on disk is
not the same as a test that passes, so the tests were run.

**All 8 cited suites, ~400 tests: `PYTEST_EXIT=0`.**

```
tests/test_security.py                     tests/test_audit.py
tests/adversarial/test_gateway_bypass.py   tests/adversarial/test_audit_integrity.py
tests/adversarial/test_sandbox_escape.py   tests/test_generate_input_shield.py
tests/adversarial/test_secret_detection.py tests/test_chat_input_shield.py
```

---

## Organ 1 — Security Gateway (`SecurityGatewayAuthority`)

**Owner class:** `aios/security/gateway.py:397` — `classify()` present and is the
production path.

**Load-bearing claim (C5), verified in code:**

* `gateway.py:414` — empty/invalid command → `Zone.RED, 1.0, "Empty/invalid command (fail-closed)."`
* `gateway.py:503-506` — `except Exception` → `Zone.RED, "Fail-closed on classifier exception"`.
  The fail-closed property survives an internal error, which is the case that
  matters; a classifier that only fails closed on *expected* input is not
  fail-closed.
* Destructive / network-egress / env-mutation patterns each resolve RED
  (`:453`, `:459`, `:465`).

**Live evidence attached:** `proof_level: live`, re-checkable —
`python scripts/phase4_live_evidence.py --tip b5485d3b...` recording
`'echo hello'=>GREEN, 'pytest -q'=>YELLOW, 'rm -rf /'=>RED`.

**Substantive verdict:** C1–C8, C11, C12 pass or are N/A-by-design. C4 is
correctly delegated to organ 4, which owns the tamper-evident chain.

---

## Organ 2 — Scope Lock (`ScopeLockAuthority`)

**Owner class:** `aios/security/scope_lock.py:162` — `is_path_in_scope()`.

**Load-bearing claim (C5), verified in code:**

* `:169-170` — empty/invalid path → `ScopeResult(False, ..., "Empty or invalid path (fail-closed).")`
* `:166` docstring and `:178` — any resolution error yields `in_scope=False`;
  absolute paths override the base *and then fail the scope check*, which is the
  correct direction (an absolute path cannot escape by overriding the join).

**Substantive verdict:** C1–C8, C11, C12 pass or N/A-by-design. C4 N/A is
sound — there is no mutable journal here to chain.

---

## Organ 3 — Secret Scanner (`SecretScannerAuthority`)

**Owner class:** `aios/security/secret_scanner.py:328` — `scan_and_redact()`.

**Verified in code:** three-pass detection (named regex → entropy → sliding-window
Base64 across token boundaries), and `:339-340` returns an explicit
`ScanResult(detected=False, findings=())` on empty/invalid input rather than a
falsy ambiguity. C5's "empty findings is explicit" is accurate.

**Substantive verdict:** C1–C8, C11, C12 pass or N/A-by-design.

---

## Organ 4 — Tamper-Evident Audit Logger (`AuditLoggerAuthority`)

**Owner class:** `aios/security/audit_logger.py:711` — `verify_chain()`.

This is the strongest of the five on paper: it is the only one with **C3 and C4
both PASS** rather than N/A — a durable SQLite hash-chained ledger plus Ed25519
signature verification, with `verify_chain` loading public keys and detecting
breaks.

Independently exercised this session: Ed25519 sign / verify / tamper-rejection
confirmed working under the `cryptography 50.0.0` bump.

**Substantive verdict:** C1–C8, C11, C12 pass or N/A-by-design.

---

## Organ 5 — Prompt Injection Shield (`InjectionShieldAuthority`)

**Owner class:** `aios/security/injection_shield.py:80` — `is_injection()`.

**Load-bearing claim (C5), verified in code:** `:94-95` — `except Exception:
return False`. This is **fail-SOFT, deliberately**, and the reasoning holds: this
shield is the *second* layer, and failing soft keeps the regex layer
authoritative rather than letting an embedder outage silently become a permissive
verdict. Failing closed here would let a model-loading error block legitimate
traffic while adding no security, since regex still applies.

Worth the operator noting explicitly: organ 5's C5 is "PASS-BY-DESIGN" on a
*different* rule than organs 1–3. That is defensible and documented, not an
oversight — but it is the one place where "fail-closed" is not literally true.

**Substantive verdict:** C1, C2, C5–C8, C11, C12 pass; C3, C4 N/A-by-design.

---

## The finding the operator must decide on

**C9 and C10 do not currently reflect reality for any of the five.**

* **C10 reads `"N/A/FAIL — no live evidence"` while every one of the five rows
  carries a `live_evidence` item with `proof_level: live`.** The verdict string
  is stale — written before the Phase 4 probe evidence was attached, and never
  re-derived. The organs' own blocker text already says so: *"Live read-only probe
  evidence IS now attached at the tip below."*
* **C9 is circular.** It reads `FAIL — yellow with named residual(s)` where the
  named residual is the frozen-spine block itself. C9 fails because the organ is
  yellow; the organ is yellow because C9 fails. It is a status echo, not a
  condition assessment.

Consequence: signing today would produce a digest over verdicts that contradict
their own rows. That is not the honest green that was asked for.

**This document deliberately does not fix C9/C10.** Rewriting the verdicts that
block green, inside the same change that builds the unlock, is precisely the move
the frozen spine exists to catch — and it should make any reviewer suspicious of
the agent proposing it. The correction is the operator's to authorise separately.

---

## What is genuinely NOT proven, and will not be by this approval

Stated so the approval is not read as more than it is:

1. **No independent third-party audit.** Every assurance above is
   correct-by-test and correct-by-probe, produced by the party that also wrote
   code in this repository today.
2. **No hostile-user evidence from production.** These organs have never faced a
   real adversary who was trying to get through them.
3. **Read-only probe, not exercised-under-load.** The Phase 4 evidence is a
   read-only classification probe. It proves the classifier answers correctly; it
   does not prove behaviour under concurrency, exhaustion, or sustained attack.
4. **Organ 5's shield fails soft**, by design — see above.

An operator approval discharges the *process* residual (§VIII was never
completed through a channel the code could receive). It does not manufacture
items 1–3, and the ledger should not later be read as claiming it did.

---

## Recommendation

The substantive conditions for all five are met, verified in code, with every
cited test passing. The block was never an evidence gap — it was a missing
approval channel, which is why the operator's own §VIII Approve+Deploy on
2026-07-31 (recorded at `organ_ledger.py:437`) left the organs yellow.

**Recommended sequence — corrected 2026-08-05.**

An earlier version of this document proposed signing first, then re-deriving
C9/C10, then signing again. **That does not work**, and the correction is worth
recording because the reasoning behind the mistake was superficially careful.

The digest covers each organ's `status` — the very field an approval authorises a
change to. A signature taken over the pre-approval (yellow) state therefore stops
verifying the instant the status is flipped to green. The approval invalidates
itself the moment it is acted on. Verified by computing both digests; now pinned
by `test_signing_the_pre_approval_state_does_not_authorise_green`, and the
signing CLI refuses outright rather than producing a useless signature.

The correct order is one signature, over the final state:

1. **Propose** — the ledger is prepared in its post-approval form: organs 1–5 set
   green, the §VIII blocker discharged, C9/C10 re-derived honestly. Uncommitted.
2. **Human Review** — the operator reads *that diff*, alongside this document.
   This is where the "agent edited the evidence" concern is actually addressed:
   not by the agent refusing to prepare the change, but by the operator seeing
   precisely what they are approving before they approve it. AGENTS.md §VIII is
   explicit that *"Proposing is GREEN"* — preparing the proposal is the agent's
   job; ratifying it is not.
3. **Approve** — the operator signs over exactly that state.
4. **Deploy** — ledger and attestation are committed together, so what was signed
   and what ships are the same bytes.

The earlier two-signature scheme was an artifact of the wrong ordering, not a
safeguard. It is not needed.
