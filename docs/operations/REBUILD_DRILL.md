# Rebuild drill: GAGOS recovered from GitHub plus a data backup

*Run 2026-10-19 on the operator's laptop by the coding agent, at his request
("honestly complete" the dependability items). Personal-dependability item 4:
his "stranger" is himself after a reinstall or a laptop loss.*

## What was done

The README Quick Start was followed **as written**, into an empty `C:\drill`,
by a script that recorded every step's exit code and duration:

| Step | Exit | Time |
|---|---|---|
| `python -m aios backup create` (from the live install) | 0 | 2.5 s |
| `python -m aios backup verify` | 0 | 1.3 s |
| `git clone https://github.com/swap821/ai-editor.git` | 0 | 32 s |
| `py -3 -m venv .venv`, pip upgrade | 0 | 19 s |
| `pip install -e ".[test]"` | 0 | 317 s |
| `.env` from `.env.example` plus a generated `AIOS_VERIFICATION_AUTHORITY_KEY` | — | — |
| `python -m aios backup restore --input …` | 0 | 7 s |
| `python -m aios doctor` | **1** | 2 s |
| backend `python -m aios` on port 8010, `GET /health` | 200 | 5 s |
| restored memory compared with the live memory | equal | — |
| `npm ci`, `npm run build` | 0 | 68 s |
| **Total** | | **7.6 min** |

**Restored memory was identical to the live store.** Counts in both:
- 90 procedural skills;
- 121 lessons;
- 232 semantic memories;
- 14 compiled playbooks.

Backup and restore are faithful.

## The one red step: `doctor`, and it is red on the live install too

`doctor` reports `audit_integrity: fatal — audit hash chain failed
verification`. `python -m aios audit verify` says the same on the **live**
install: 780 entries, "Invalid Ed25519 signatures detected". So the restore
did not cause it; the drill surfaced it.

**Measured cause:**
- **Which entries.** The 351 "invalid signatures" are exactly the 351
  **unsigned** entries, ids 1–351, written 2026-06-02 to 2026-06-29, before
  audit signing existed.
- **The rest is sound.**
  - Every entry since then (352–780) is signed and verifies.
  - The hash chain is unbroken.
  - The tip anchor is valid.
- **The consequence.** The verifier counts unsigned history as invalid, so
  on this install the check can **never** pass again.

**A second, separate gap: trust is never anchored.**
- No `AIOS_AUDIT_PRIVATE_KEY` is stored. It is not in the keystore's list,
  `.env` or the environment.
- So every backend process signs with a key generated at startup. There are
  76 such keys in the database.
- Verification can then only check signatures against keys the audited
  database supplies about itself. The module calls this "internally
  consistent", not "attested".

Both live in `aios/security/audit_logger.py` (organ 4, frozen spine). The
choices are the operator's:
1. **How pre-signing history is judged.** It could be closed by an
   operator-signed boundary record over entries 1–351, or reported as
   "unsigned legacy" without failing the chain. Silently accepting unsigned
   entries is not an option.
2. **Anchoring the audit trust.** Store an `AIOS_AUDIT_PRIVATE_KEY`. That
   needs the keystore to manage that name, and storing it is his act.

## What a real laptop loss would still break (this drill could not)

- **The backup lives on the laptop.** `python -m aios backup create` writes
  under `data/backups` on the same disk, so a lost laptop loses its backups
  too. **Decision for the operator:** where an off-machine copy goes (a USB
  drive, OneDrive, another machine), and how often.
  `backup create --if-stale` is already designed for a scheduled task.
- **Keys are not in the backup, by design.** Windows Credential Manager is
  per machine and per user. On a new laptop, every key must be stored again
  with `python -m aios.launcher keys set …` from wherever he keeps them
  offline:
  - `AIOS_API_TOKEN`
  - `AIOS_EXECUTOR_TOKEN`
  - `AIOS_VERIFICATION_AUTHORITY_KEY`
  - `AIOS_PROMOTION_AUTHORITY_KEY` and `AIOS_CHECKPOINT_AUTHORITY_KEY` (since #523, 2026-10-19). A new checkpoint key cannot verify rollback points signed with the old one; that only matters for an in-flight rollback.
  - `AIOS_LEARNING_KEY_LIVE`
  - the AWS pair
- **The operator credential IS in the backup** (the identity store is under `data/`). If you have lost the credential itself, `docs/operations/OPERATOR_RECOVERY.md` replaces it without losing your operator id.
- **The spine signing key.** The private half lives only with the operator.
  It was lost once already (2026-10-19, rotated in #516).
- **Local models are not in the backup.** `ollama pull` each one again.
- **This drill shared the laptop's** Credential Manager, Ollama and Python
  install, so it did not exercise those.

## How to repeat it

```
python tools/rebuild_drill.py C:\drill C:\Users\kumar\ai-editor
```

The script is `tools/rebuild_drill.py`, and its record is
`C:\drill\drill.json`. Delete `C:\drill` afterwards. It is a full clone plus
a venv, about 2–3 GB.
