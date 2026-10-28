# Frozen copies of two local learning trails

*Committed 2026-10-28. These are evidence, not live files.*

The Learning Ledger (`.aios/state/LEARNING_LEDGER.json`) cites two trails that the
training harness appends to under `.aios/audit/`, which is gitignored. They
existed only on the operator's laptop, so in a clean clone, and in CI, the
verifier failed LC10 for L1, L6, L7 and L8, and LC4 for L3. These are frozen
copies, byte-identical to the laptop's files on 2026-10-28.

| File | sha256 | Records | Cited by |
|---|---|---|---|
| `organic-chain-runs.jsonl` | `79d329f654f7d257b324b07bbb16980da048885ff6cc7b36f2f22f6434410f9c` | 22 | L1, L3, L5, L6, L7, L8 (run `20260922T044658-557cc9a6` at `00dbf6f3`) |
| `reverse-engineering-runs.jsonl` | `518de390f1459286fbcc1c524553df2753b2aeff780c78acd48b835d1121c522` | 29 | L3's LC4 note (the append-only record of self-corpus attempts) |

## What was checked before committing

- **Secrets and personal data.** Every flag was checked by hand.
  - The repository's secret scanner flagged `reverse-engineering-runs.jsonl`. Every match is a false positive:
    - the "AWS secret key" is a 40-character git commit hash inside a `git worktree add` error;
    - the "high-entropy" strings are a test name (`test_build_auto_verify_command`) and a model id (`qwen3-coder-480b-a35b-v1:0`).
  - Every "password" or "secret" in either file is a fixture string from a redaction test, such as `'echo password=secret' == 'echo password=****'`.
  - No keys, tokens, e-mail addresses or principal ids were found.
  - The only personal item is the Windows user path, which already appears in 156 tracked files.
- **That the files support what the ledger says.**
  - In the cited run, L1 (lesson 105), L3 (skill 66), L5 (playbook 15) and L6 (curriculum level 1) each fired.
  - L7 and L8 claim things about the run as a whole, and the record matches them: 14 attempts, 2 earned, 12 rejected, every one reaching the model, every source file untouched, outcome `completed`.

## Not done

- The live trails at `.aios/audit/` keep growing on the laptop. These copies do not follow them.
- A later run's evidence needs its own committed copy.
