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

## 6. COMPOSITE SPEC v1 — the attack target (not yet ratified)

Implementable pseudocode against `secret_scanner.py` as it stands; the same
helper is exported and reused by `privacy_filter._redact_high_entropy`.

```python
_PATH_SEP = re.compile(r"[\/]")
#: Elevated merged-token threshold for path-shaped tokens. Empirical basis
#: (§1): merged word-paths score 3.6-4.1 bits/char; real random secrets in
#: base64/url-safe alphabets score 5.0+. 4.7 leaves margin on both sides.
_PATH_MERGED_ENTROPY_THRESHOLD = 4.7

def _entropy_token_is_credential(token: str) -> tuple[bool, str]:
    """Score one Pass-2 token. Returns (redact?, finding_label)."""
    if not _PATH_SEP.search(token):
        # NON-path tokens: byte-identical to today's rule. No behavior change.
        hit = (len(token) >= _credential_like_min_len(token)
               and shannon_entropy(token) >= _ENTROPY_THRESHOLD)
        return hit, "HIGH_ENTROPY"
    # Path-shaped tokens (contain a separator) get THREE channels:
    # (a) NEW DETECTION: named patterns on the separator-stripped reassembly —
    #     catches credentials split across separators, which today EVADE Pass-1
    #     (the contiguous run is restored before the regexes see it).
    #     AWS_SECRET_KEY keeps its _has_aws_context() requirement, evaluated at
    #     the token's position in the ORIGINAL payload, exactly as today.
    stripped = _PATH_SEP.sub("", token)
    for name, pattern in _NAMED_PATTERNS:
        if pattern.search(stripped):
            return True, f"PATH_REASSEMBLED_{name}"
    # (b) per-segment scoring under the EXISTING rule — a genuinely random
    #     segment (>=20 chars, >=4.0 bits/char) still redacts.
    for seg in _PATH_SEP.split(token):
        if seg and len(seg) >= _credential_like_min_len(seg) \
                and shannon_entropy(seg) >= _ENTROPY_THRESHOLD:
            return True, "HIGH_ENTROPY"
    # (c) merged-token scoring at the ELEVATED threshold — catches a generic
    #     secret spread thin across segments while releasing the 4.0-4.7
    #     word-path false-positive band.
    if len(token) >= _credential_like_min_len(token) \
            and shannon_entropy(token) >= _PATH_MERGED_ENTROPY_THRESHOLD:
        return True, "HIGH_ENTROPY"
    return False, ""
```

- Pass-2's replace callback delegates to this helper; Pass-1, Pass-3, the
  gateway ordering, and every caller are otherwise untouched. No masking
  anywhere. No grammar exemptions.
- `privacy_filter._redact_high_entropy` imports and applies the same helper
  (one truth; its `[SENSITIVE: hash]` placeholder format unchanged).

**Honest deltas vs today** (the attack round probes exactly these):
1. RELEASED: forward-slash-merged tokens whose merged entropy is 4.0–4.7 AND
   no segment is individually credential-like AND no named pattern
   reassembles. By construction this is the witnessed false-positive band.
   The attack round must hunt REAL credential formats living here.
2. GAINED: split-credential reassembly detection (today's confirmed A-kill
   payloads are all caught by channel (a)).
3. UNCHANGED (pre-existing limit, documented): Windows backslash paths never
   form merged tokens (the tokenizer excludes `\`), so they are per-segment
   today and per-segment under this spec; backslash-split credentials evade
   today and still would. Channel (a) does not extend across separate tokens.
   A future Pass-3-style window could; out of scope for v1.

**Acceptance corpora (committed as tests when ratified):**
- FP corpus must pass clean: both witnessed manifestations, mkdtemp/GUID tmp
  dirs, pytest tmp paths, the full build_auto_verify_command shapes.
- Smuggling corpus must ALL be caught: every §2 kill payload, AKIA/ghp_/sk-/
  JWT/PEM split across `/` at every offset, high-entropy 40-char base64
  secrets as single path segments, and the same embedded in runner commands.

## 7. ATTACK ROUND 2 VERDICT — SPEC v1 DIES. Effort CLOSED; spine NOT changed.

**Status change: this proposal is REJECTED. No `aios/security/**` edit will be
made.** Full round-2 transcript kept OUT of the repo (its synthetic attack payloads
contain credential-shaped strings that GitHub push-protection correctly blocks —
the very hygiene this analysis defends); it lives in the session scratchpad. The
verdict, findings, and decision below ARE the durable record.

Two independent adversarial lenses, attacking a faithful shadow that imported
the REAL scanner helpers (zero drift), both returned **SPEC_DIES** on verified,
reproducible **regressions** — cases today's scanner CATCHES that spec v1
RELEASES:
1. **N-way dilution across every named family** (Stripe/GitHub/GCP/OpenAI):
   `webhook_configs/sk_live_/OhbV.../VgRV.../Bcbf.../deploy.py` — today
   HIGH_ENTROPY-caught on the merged token (H≈4.6); spec v1 evades all three
   channels (segments under the 20-char floor, merged under 4.7, reassembly
   broken by the interposed directory word). Real-credential regression.
2. **AWS family, 16/16 reproducible** via doubled-separator + short glue char
   (`ke//ys/AKIA//IOSFODNN7EXAMPLE/x.py`): today caught, spec v1 evades every time.
3. **Hex secret in a word-path** (`logs/<32-hex>/readme.py`, a Django
   SECRET_KEY shape): today caught at the 4.0 merged bar; spec v1's channel (b)
   hex floor (32) + channel (c) elevated 4.7 both miss it.
4. **A NEW false-positive spec v1 introduces**: a 2-char dir `sk`/`gh` reassembles
   into a fake PATH_REASSEMBLED_OPENAI/GITHUB hit on innocent paths.
5. `_PATH_SEP` as written is forward-slash-only (backslash + mixed-separator
   paths bypass the whole scheme).

The amendments the verdict lists (strip short/dictionary segments before
reassembly; boundary-trim retries; backslash in the class; hex-aware channel
(c)) each patch one leak while the underlying trade stands: **any path-aware
relaxation of the merged-token entropy rule reopens dilution room that the
current crude rule covers.** The scanner's bluntness is load-bearing.

### The decision (CEO call, honest)
- **Keep the frozen spine unchanged.** The disease is milder than every
  proposed cure: the OPERATIONAL manifestation (RED-blocked forced verify) is
  ALREADY neutralized in production by `build_auto_verify_command`
  relativizing to the scope root (short paths, live since ecf743e). The
  remaining AUDIT-COSMETIC manifestation (a plain filename mangled mid-path in
  the tamper trail) is a genuine but minor honesty blemish, not a security or
  correctness hole.
- **Accepted residual, documented:** long absolute paths with mixed-case/high-
  diversity segments may be cosmetically redacted in audit payloads. Mitigation
  is behavioral (keep sandbox paths short/relative), never a spine relaxation.
- **If ever revisited:** a spec v2 must NOT relax the merged threshold and must
  NOT rely on separator splitting — the only direction round 2 leaves open is a
  filesystem-truth exemption (redact-suppress ONLY tokens that resolve to an
  actually-existing in-scope path), evaluated at a layer with disk access and
  AFTER Pass-1 named patterns run on the raw token — and even that must survive
  its own attack round before ratification. Not scheduled.

This is the analysis-first RED-zone discipline working as designed: two
adversarial rounds, and the spine stays frozen because no proposal survived.
