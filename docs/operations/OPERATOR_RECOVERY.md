# Operator recovery: a lost credential, without losing your identity

*Written 2026-10-21, after the first real use (2026-10-19). The tool is
`tools/operator_recover.py` (#522).*

## When you need it

You have lost your operator credential. The recovery code that enrollment
issued has no way to be used yet (no HTTP route accepts it).

**Do not re-enroll.** Re-enrolling mints a **new** operator id. Everything scoped
to the old one is then orphaned: lessons you re-admitted, skills, approvals.
This tool keeps the id and replaces only the secrets.

## How

Run it yourself, in a plain PowerShell window with no agent attached. It
refuses to run without a real terminal, so that your secrets never pass
through an agent.

```powershell
cd C:\Users\kumar\ai-editor
python tools/operator_recover.py --reset
```

1. It shows your operator id and what will change.
2. Type a **new credential** twice, then a **different recovery code** twice. Each must be at least 20 characters. Nothing appears while you type; that is intentional.
3. Type `reset` to confirm. Anything else aborts and changes nothing.

Git Bash (mintty) cannot read hidden prompts. Use PowerShell, or prefix the
command with `winpty`.

## What it does

- **Keeps the operator id.** Everything scoped to you stays yours.
- **Stores digests, never secrets.** Secrets you chose are stored as salted scrypt (N=2¹⁴, r=8, p=5). Enrollment's generated tokens stay SHA-256, and login accepts both.
- **Logs out every existing session**, by bumping the session generation.
- **Records the reset** as a `local_secret_reset` authentication event and in the tamper-evident audit log.
- **Needs no backend restart.**

## Why this is safe

Its only proof is local access to this machine's identity store. That access
already lets anyone delete the store and enroll a different operator, so the
tool grants nothing that access did not. Unlike re-enrolling, it loses nothing.

## Checking it worked (no secret is read)

```powershell
python -c "import sqlite3; from aios import config; c=sqlite3.connect(str(config.IDENTITY_DB_PATH)); print(c.execute('SELECT substr(credential_digest,1,7), substr(recovery_digest,1,7) FROM sovereign_operator').fetchone())"
```

Both values should start with `scrypt$`.

## The 2026-10-19 use

- **First run** (from the PR branch, before #522 merged): the operator id was kept, all 11 lessons scoped to it were intact, and the reset was recorded. The digests were still bare SHA-256, because CodeQL flagged that version.
- **After #522 merged, with salted scrypt:** the reset was re-run, and both digests are now scrypt, verified 2026-10-20.

## Not built yet

An HTTP route that accepts the recovery code. It needs the edge allowlist, the
policy kernel and an action type. Your reset stores a new recovery digest, so
that route will work for you once it exists.
