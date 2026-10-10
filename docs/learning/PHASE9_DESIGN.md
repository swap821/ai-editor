# Phase 9 design: the carried items

*For the plan "the learning loop, held to the cage's standard". Phase 9
carries items the earlier phases found and could not close in their own
scope.*

## Already closed

- **L4 re-earned through the fresh-target harness, and L2 with a stronger
  tier.** Both landed in #404 (AWS ladder; Learning Ledger 7/8, with L5 yellow
  by design).

## The two reconciliations (2026-10-05)

Each is the same failure: two parts of the evidence machinery answer one
question two ways. Each fix gives the question one derivation, with two
callers.

### 1. "Did this organ's code move since it was verified?"

- **The disagreement.**
  - The organ gate (`_entrypoint_drift`, which feeds C10 and C12) walked the
    log: `git log --name-only <sha>..HEAD -- <entrypoints>`.
  - The currency tool (`changed_since`) diffed the trees:
    `git diff --name-only <sha>..HEAD`.
- **The log walk was wrong in both directions.**
  - **False staleness.** An entrypoint edited and then reverted, or a squash
    that carried the identical content, counted as moved. The file is
    byte-identical to the one attested.
  - **False freshness.** Take evidence gathered on a branch that a squash
    orphaned, where the branch's own edit to an entrypoint never reached HEAD.
    The gate read it as current, because no commit between the orphan and HEAD
    touched the file, although HEAD's file is not the file the evidence
    attested.
- **The fix.** `changed_since` (in `scripts/verify_evidence_currency.py`) is
  the one derivation. It compares content, takes a `root`, and reports
  unreadable git as `<unresolvable: …>`, which callers treat as drift and never
  as fresh. `_entrypoint_drift` now calls it.
- **Measured on master `5469e34a`:** 117 attestation and live-evidence checks
  across the ledger. One answer changed: organ 55 (yellow), where the log walk
  also flagged a reverted edit and both versions still report drift. No green
  organ moves either way.
- **Tests:** `tests/test_one_drift_derivation.py`, on throwaway repositories.
  Against the old gate, 5 of its 7 tests fail. Three are the real
  disagreements: reverted edit, squash of the same content, and the orphaned
  branch's own edit. Two only change the "unavailable" marker, since the old
  gate also failed closed there.

### 2. "Is this live-evidence row bound to its commit?"

- **The disagreement.**
  - `scripts/verify_evidence_lineage.py --update` re-points a squash-orphaned
    sha to an ancestor whose entrypoints are byte-identical.
  - For a live row citing a `release/phase4` artifact or a CI run, C10 checks
    the citation against the row's commit: the artifact's `tip_sha`, and the
    commit the run ran at.
  - So a re-pointed row was a row C10 refuses (#368, which re-gathered
    instead). The only guard was a sentence in `phase4_attach_ledger.py`'s
    refusal message.
- **Why not teach C10 content-equivalence?** It is not checkable where it
  matters. A clean CI clone does not have the orphaned commit, so it cannot
  compare blobs at it.
- **The fix.** `commit_bound_citations(description)` in
  `scripts/verify_organ_twelve_conditions.py` is the one derivation.
  - C10 reads its artifact and run citations through it.
  - The lineage tool asks it before moving a live row. A row proven *at* the
    orphan is reported "re-gather at a current commit, do not re-point" and
    left untouched.
  - The attestation sha, and rows citing no commit-bound proof, are still
    re-pointed on byte-identical content, as before.
- **Measured on master `5469e34a`:** 52 organs in lineage, 5 spine organs
  untouched, 0 re-pointable. One is unprovable: organ 44 (yellow), whose sha
  `e3b0b00365e6` has no ancestor with identical entrypoints. That is real
  staleness, already there, and unchanged by this fix.
- **Tests:** `tests/test_lineage_respects_c10.py`.
  - With the lineage half reverted, both refusal tests fail and the control
    (a row citing only a test node) still passes.
  - With the gate half reverted, the module cannot import the shared function.
