# Strict-release procedure (Phase 1 / Phase 6 chicken-egg)

## Why exact tip equality cannot hold on every ordinary commit

A commit SHA is a hash of its own final tree. A ledger file committed *as part
of* that commit can only truthfully record a *prior* commit's SHA (or an
evidence tip), never its own. Requiring `last_verified_sha == HEAD` on every
push is therefore unsatisfiable without lying.

## Ordinary CI (push / pull_request) — Phase 1 teeth

```bash
python scripts/build_release_manifest.py --check
python scripts/verify_organ_contracts.py --require-sha-ancestry
```

Rules:

- Every green organ has a well-formed 40-char `last_verified_sha`.
- That SHA is an **ancestor of HEAD** when git can answer (full clone).
- Written `condition_verdicts` C1..C12 are present for all 54 organs.
- Exact tip equality is **not** required.

Wired in `.github/workflows/ci.yml` (`release-authority` job).

## Strict release (Organ 23) — tagged evidence tip

`--strict-release` requires every green `last_verified_sha == HEAD` **and**
the regenerated manifest `source_commit_sha == HEAD`.

Honest ways to get exit 0:

1. **Evaluate at the evidence tip** (preferred when live evidence was stamped
   there). Example: tip `5d482164707c6c6e62f3da6a37cff79f252f9260` held
   tip-aligned live evidence + SHAs. Checkout that tip, regenerate the
   manifest in the ephemeral workspace, run:

   ```bash
   git checkout <evidence-tip>
   python scripts/build_release_manifest.py
   python scripts/verify_organ_contracts.py --strict-release
   git tag gagos-release-<date> <evidence-tip>
   ```

2. **Tip-alignment release commit** after a fresh live-evidence wave:
   - Run `scripts/phase4_live_evidence.py` and attach at the runner tip `T`.
   - Commit the ledger+evidence with `last_verified_sha = T` for every green
     (this commit's parent is `T`, or the commit *is* `T` if evidence was
     attached in the same tree as the runner).
   - Tag **`T`** (not a later doc-only commit) as `gagos-release-*`.
   - CI `release-strict-gate` runs on `workflow_dispatch` and on
     `gagos-release-*` tags; it regenerates the manifest ephemerally then
     runs `--strict-release`.

## What is NOT proof

- Stamping `last_verified_sha` to HEAD without re-running evidence.
- Hand-editing `release/organ-proof-manifest.json`.
- Declaring 54/54 while Outside-machine / Ollama / Docker / browser / frozen
  residuals remain (publish itemised shortfall with **exact condition numbers**
  instead — see `release/phase6/organ23-shortfall.md`).
