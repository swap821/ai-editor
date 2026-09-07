# `install.ps1`, run for the first time — 2026-09-07

**Result: it worked, and it found a defect that made it lie when it did not.**

## This is NOT a clean box

Stated first because the number below could otherwise be read as equivalent to
the Fedora container run, and it is not.

`scripts/install.sh` was proven in stock `quay.io/fedora/fedora:40` — a machine
with no Python, no `git`, no `pip`, nothing. This run is a **fresh clone on the
development machine**. Windows already had Python 3.14, git, a toolchain and a
running Ollama. It proves the *script*, not the newcomer-from-nothing path.

No Windows container was available, so the honest ceiling here is lower. What
was controlled: a fresh `git clone`, no `.env`, and no `AIOS_*` environment
variables set.

## The defect: it reported success on a failed install

The first run was at a deep path. `pip` died:

```
ERROR: Could not install packages due to an OSError: [Errno 2] No such file or
directory: '...\.venv\Lib\site-packages\torch\include\ATen\native\transformers\
cuda\mem_eff_attention\iterators\default_warp_iterator_from_smem.h'
```

The script **carried on**. It wrote the `.env`, ran the health check, and the
health check correctly caught it:

```
GAGOS v0.1.0 bootstrap failed; 5/6 checks passed (blocking: package_imports)
  [FAIL] package_imports (required): Missing packages: boto3, cryptography,
         fastapi, git, httpx, pydantic, sklearn, typer
```

and then printed:

```
==> Installation complete.
EXIT=0
```

`bootstrap`'s verdict was a **warning**. So anything scripting this installer
saw success on an install with eight required packages missing.

**An installer that reports success on a failed install is worse than one that
crashes — the crash is honest.** Both `pip` and `bootstrap` failures are now
fatal.

Fixed and verified in both directions:

```
long path,  pip fails   ->  EXIT=1, message naming MAX_PATH and a shorter path
short path, pip works   ->  EXIT=0, bootstrap 6/6
```

## The pip failure itself was partly my test location

Honest separation: the OSError is a Windows `MAX_PATH` overrun. The repository
root was 118 characters, and torch's deepest header sits ~145 beyond that —
over the 260 limit. `LongPathsEnabled` is `0` on this machine.

Re-run at a 20-character root, the same command installed cleanly. So the
failure is **not** a packaging defect; it is real for any user with a long path
and long paths disabled, which is the Windows default. The new error message
names both remedies.

## What the working run produced

```
GAGOS v0.1.0 bootstrap passed; 6/6 checks passed
  [OK] python_version · data_dir · env_file · token_length
  [OK] ollama_reachable
  [OK] package_imports (required): All required packages importable

key length : 64          is hex : True
torch      : 2.14.0+cpu
venv size  : 1.16 GB
HTTP /health = 200
```

A fresh clone, one command, no environment variables, no hand-written `.env` —
and a backend answering.

## `-CpuTorch` is deliberately absent, and that is measured

`install.sh` has `--cpu-torch` because Linux resolves `torch>=2.0` to the CUDA
build and pulls ~2.96 GB of NVIDIA libraries. Windows does not: this run
installed **`torch 2.14.0+cpu`** with no flag at all, in a 1.16 GB venv.

A flag that does nothing is worse than no flag — it implies the default is
wrong. The README already records that the flag is Linux-facing.

## Also corrected here

An external review recorded `scripts/install.ps1 ABSENT` and concluded *"the
one-command install you built runs on an OS you don't use."* The file is
`install.ps1`, at the repository root, and is tracked. The claim was a path
mistake.

What was true, and is now closed: it had never been run end to end, and it did
not print the `doctor` hint that `install.sh` does. `doctor` checks **runtime**
health — audit chain, backups, model runtime, executor — which is a different
question from `bootstrap`'s install-time checks, and a Windows newcomer was
never told it exists.

## What this still does not establish

**Nobody but the operator has run this.** Not on Windows, not on Linux. The
Fedora container removed the "works on my machine" objection for the *machine*;
it did not remove it for the *person*. That remains the single largest
unclaimed item in the reproducibility ladder, and it is not an engineering
problem.
