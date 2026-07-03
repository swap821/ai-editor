# Scanner Path-Entropy False-Positive — Analysis + Proposal (RED-ZONE GATE)

**Status:** PROPOSED — touches `aios/security/**` (frozen spine). **No edit is
authorized by this doc**; implementation requires operator ratification via
the §VIII strengthen-only flow.
**Date:** 2026-07-03 · **Analysis:** 3-agent read-only workflow
(wf_278111ea), full JSON preserved at
`.aios/state/analysis/2026-07-03-scanner-path-entropy-analysis.json`.

## 1. Root cause (reproduced, file:line precise)

`secret_scanner.py` Pass-2's `_ENTROPY_TOKEN` char class **includes `/`**, so
a POSIX-style relative path (`training_ground/test_selfcheck.py`) is scored
as ONE merged token — directory + stem concatenated — whose entropy crosses
the 4.0 bits/char threshold at ≥20 chars even though each real segment is an
ordinary word. Pass-2 has **zero context gating** (unlike Pass-1 named
patterns and Pass-3 keyword windows). `privacy_filter._redact_high_entropy`
has the near-identical defect (it produced the witnessed
`test_[SENSITIVE: hash].py` shape byte-for-byte).

Two blast paths:
- **Audit honesty:** `audit_logger.log_action` redacts payloads → plain
  sandbox filenames mangled mid-path in the tamper trail.
- **Verified-evidence kill:** `gateway.classify` runs the credential scan
  BEFORE the pytest caution rule, so a long-enough embedded path flips the
  FORCED auto-verify command to RED — and RED is unapprovable by design
  (`execute_approved` refuses finally). In affected environments the
  supervised-verify step is structurally impossible.

Empirical boundary: snake_case English-like names never cross 4.0 (max ~3.9
at 61 chars); mixed-case-alnum random dirs (mkdtemp/GUID charset) cross
deterministically at ~22 chars.

## 2. Options analyzed — and ALL FOUR REFUTED as specified

An adversarial agent broke every option with working payloads (full
transcripts in the preserved JSON):

| Option | Kill |
|---|---|
| A. Per-segment scoring | Real 40-char secret split across attacker-chosen separators → every segment under the 20-char floor → EVADED |
| B. Path-grammar + runner-context exemption | Exemption is dead code as literally specified; and a bare `Zk9…secret….js` (no separator) satisfies the grammar → EVADED |
| C. SCOPE_ROOTS masking pre-scan | Masking runs before Pass-1, blinding the named AKIA/ghp_/JWT regexes to in-scope-path secrets → EVADED |
| D. Raise thresholds | Statistically confirmed: FP corpus and short real secrets occupy the SAME entropy band — no threshold separates them |

**Nothing gets implemented from the above as-is.** This is the analysis-first
gate working.

## 3. Composite recommendation (derived from the attacks; NOT yet specced)

The three kills point at one composite design, to be fully specced and
re-attacked before any ratification:

1. **Pass-1 named patterns additionally run on separator-stripped
   reassemblies** of path-shaped tokens → kills A's AKIA-split smuggling
   (the contiguous run is restored before the regexes see it).
2. **Pass-2 scores path-shaped tokens per-segment** (kills the FP band:
   word-like segments never reach 4.0) **AND ALSO scores the merged token at
   an ELEVATED threshold ≈4.7 bits/char** — real random secrets sit at 5.0+
   bits/char, merged word-paths at 3.6–4.1, so the classes separate where
   the single 4.0 threshold could not.
3. **No masking before Pass-1, ever** (C's lesson); **no grammar exemptions**
   (B's lesson); gateway ordering untouched.
4. Same change mirrored in `privacy_filter._redact_high_entropy`.

Honest residual: a generic (non-named-pattern) secret with entropy between
4.0–4.7 deliberately split across separators would evade Pass-2 — noting the
scanner's primary threat model is accidental model-emitted leakage, and
active adversarial splitting already has cheaper evasions today (whitespace
insertion). The named-pattern reassembly (item 1) covers the credential
formats that matter most.

## 4. Required before any spine edit

- Full spec of §3 with pseudocode → a SECOND adversarial workflow attacks it
  (same refute-by-default brief) → only a surviving spec goes to the
  operator for §VIII ratification.
- Acceptance corpora (both must be committed as tests): the FP corpus
  (sandbox paths, pytest tmp dirs, mkdtemp names, the two witnessed
  manifestations) must pass clean; the smuggling corpus (every payload from
  §2's kills + AKIA/ghp_/JWT/PEM/base64 embedded in path shapes) must ALL
  still be caught.
- Full gate + audit-chain tests green; strengthen-only argument reviewed.

## 5. Interim mitigation (already live, no spine involvement)

`tests/test_grant_workflow_steps.py` documents the short-path workaround;
`build_auto_verify_command` relativizes against the scope root so production
sandbox commands stay short. The witnessed-path FP band is currently avoided
in practice; the audit-trail cosmetic mangling persists until the real fix.
