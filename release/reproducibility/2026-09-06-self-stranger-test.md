# Self-stranger install test — 2026-09-06

**Method:** fresh `git clone` from GitHub into an empty directory, then
`README.md` §§1–5 (lines 703–773) followed **literally** — no fixes, no prior
knowledge, no "I know what that means."

**Headline:** following the README exactly, on a supported Python, with a
successful install, **the backend does not start.** One undeclared dependency
is the entire blocker.

## Honest limits of this test

The intended clean-box run could not happen: container pulls are blocked from
this machine — both Docker Hub and `mcr.microsoft.com` fail with `EOF` on the
blob fetch. So this is a **degraded test**: fresh clone and fresh venv, but the
same OS and the same globally-installed toolchain.

It catches documentation and dependency stalls. It does **not** catch missing
system packages, OS differences, or anything masked by software already present
here. A real clean-box run is still owed.

## The blocker

```
RuntimeError: Form data requires "python-multipart" to be installed.
  aios/api/routes/memory.py:704  ->  @router.post("/api/v1/knowledge/ingest")
```

Root cause is a **manifest split**:

```
requirements.txt:78    python-multipart==0.0.32     present
pyproject.toml         absent
README line 718        pip install -e ".[test]"     installs from pyproject
```

`requirements.txt` is a `pip freeze`; `pyproject.toml` is the declared manifest.
The README points at the one missing the package. A working venv on the author's
machine hides this completely — the classic "works on my machine" from an
undeclared direct dependency.

**Proof it is the whole blocker:** installing only `python-multipart` into the
otherwise-untouched test venv:

```
GET /health -> 200
Application startup complete.
Uvicorn running on http://127.0.0.1:8000
```

## Findings, graded

| # | finding | verdict |
|---|---|---|
| 1 | `python-multipart` undeclared in `pyproject.toml`; backend cannot start from a documented install | **BLOCKER, genuine** |
| 2 | `py -3.11` fails on the author's own machine — 3.11 exists only as `Astral/CPython3.11.15` (uv-registered), which the `py` launcher will not resolve | **genuine** |
| 3 | README command pins exactly 3.11 while its own prose and `requires-python = ">=3.11"` both say "or newer". 3.12 was proven to work end to end | **genuine** |
| 4 | ~~No `.env` or `.env.example` is shipped~~ | **FALSE — my harness bug, see below** |
| 5 | `AIOS_VERIFICATION_AUTHORITY_KEY` appears **0 times** in the README *and* 0 times in `.env.example`, yet council missions fail without it | **genuine** |
| 6 | `pip install` died on Windows MAX_PATH | **artifact of this test, not a stall** |
| 7 | `torch>=2.0` + `sentence-transformers>=2.0` are REQUIRED, not optional — multi-GB before anything runs | context |
| 8 | Install instructions begin at line **715 of 1103** — ~700 lines of thesis first | context |

### On finding 6, against myself

The MAX_PATH failure looked like the most dramatic result and **is not real**:

```
torch's deepest relative path      ~128 chars
this test's base path               135  ->  264  > 260   FAILED
a user at C:\Users\name\ai-editor    23  ->  152  < 260   fine
```

Confirmed empirically by re-running at a 23-character base, where the install
succeeded. Reporting it as a genuine stall would have been the same error organ
55 spent forty cohorts teaching: **a harness indicting the system for a scenario
the harness itself created.**

### On finding 4, which was false — and which I acted on before checking

**`.env.example` already existed**: 12 KB, documenting every `AIOS_*` variable,
added in #188, and present in the fresh clone. The finding was produced by a bug
in this test's own script:

```bash
ls .env .env.example 2>/dev/null || echo "  no .env / .env.example shipped"
```

`ls` exits non-zero if **any** argument is missing. `.env` is gitignored and
absent, so the `||` fired and printed "not shipped" while `.env.example` sat
right there.

Worse than the false finding: I acted on it and **overwrote the real 12 KB file
with a 40-line replacement**, destroying comprehensive documentation. It was
caught only because `git status` showed `M` (modified) rather than `A` (added) —
the file was restored from `HEAD~1` before anything was pushed.

Two lessons, both ones this project already knew:
- a test that reports a gap must be verified before the gap is "fixed"
- `ls a b` is not a test for "does b exist"

Finding 5 survives the correction and is sharpened: the key is missing from
`.env.example` too. In fairness that file scopes itself to *"every AIOS_* var
`aios/config.py` reads"*, and this key is read directly through `os.environ` in
`verification.py`, so it sits outside its stated contract. It has now been added
there anyway, because the contract is not what a newcomer needs.

### On finding 5, the uncomfortable one

`AIOS_VERIFICATION_AUTHORITY_KEY` is the exact key whose absence made cohort 27's
council mission fail earlier the same day. That was hit, diagnosed from the
on-disk report, and fixed in the harness within minutes — and it never once
prompted the thought that a newcomer would hit the identical wall with **none of
that diagnosis available to them**.

That is the review's whole thesis in one example: the inward loop is fast and
legible, the outward one is invisible until somebody outside tries.

## A flaw in this harness, recorded

The first attempt reported `STRANGER_EXIT=0` while Docker had actually failed —
it captured `tee`'s exit code rather than docker's. Fixed by redirecting to a
file instead of piping. Same class of defect organ 55 keeps finding, this time
in the tooling built to find defects.

## What this changes

Fixed immediately (they are the blocker and its documentation):
- declare `python-multipart` in `pyproject.toml`
- stop pinning exactly 3.11 in the install commands
- document `AIOS_VERIFICATION_AUTHORITY_KEY` in the README and add it to the
  existing `.env.example`

Still owed:
- a genuine clean-box run once registry access works
- `scripts/install.sh` / `install.ps1` driven by these findings
- wire `aios/operations/doctor.py` into the install path so a newcomer is *told*
  what is missing instead of reading a traceback
- only then ask an actual stranger — the ask becomes "spend 20 minutes", not
  "spend an afternoon debugging my project"
