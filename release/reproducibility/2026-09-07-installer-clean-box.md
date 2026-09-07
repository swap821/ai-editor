# The installer, judged on a clean box — 2026-09-07

**Result: a stranger running `scripts/install.sh` on a machine that has never
seen this project gets a working backend.** Four defects the previous clean-box
run could not see are closed.

Judged in `quay.io/fedora/fedora:40`, a fresh container each time. The previous
stranger test (#314) passed while these defects were live, because the harness
supplied by hand what a newcomer would not — the key, the package list, the
install steps. This run supplies nothing.

## What the box was asked

```bash
dnf install git python3 python3-pip
git clone https://github.com/swap821/ai-editor.git
cd ai-editor && ./scripts/install.sh --cpu-torch
```

No environment variables. No hand-written `.env`. No pip commands.

## What it got

```
==> Writing .env if absent
  created .env

==> Health check
GAGOS v0.1.0 bootstrap passed; 5/6 checks passed
  [OK]   python_version (required)
  [OK]   data_dir (required)
  [OK]   env_file (required)
  [OK]   token_length (advisory)
  [FAIL] ollama_reachable (advisory)  -- no model runtime in the container
  [OK]   package_imports (required): All required packages importable

KEY PRESENT, length=64
BACKEND UP (HTTP 200)
torch 2.14.0+cpu
venv size: 1.5G
```

The one failure is advisory and correct: there is no Ollama in the container.
`bootstrap` reports it and still passes, which is the intended behaviour for an
advisory check.

## The four defects, and what now holds them

**1. The `.env` template omitted `AIOS_VERIFICATION_AUTHORITY_KEY`** — the value
the README calls the one genuinely required setting, and the key whose absence
killed cohort 27. A newcomer got a `.env` that could not run.

Now generated per-install with `secrets.token_hex(32)`. The box shows
`length=64`, i.e. a real 32-byte key, not a placeholder.

There were also **two templates** — `aios/bootstrap.py::write_env_template` and a
duplicate heredoc inside `install.ps1` — and the Windows copy was the one missing
the key. `install.ps1` now calls the Python writer. Two templates can drift; one
cannot.

**2. `package_imports` was a hand-maintained list** and omitted
`python-multipart`, the dependency whose absence actually stopped the backend
importing in the degraded stranger test. FastAPI needs it at import time to build
the route table, so a fresh clone died before serving anything — while
`bootstrap` reported every package importable.

Now derived from `pyproject.toml`'s `dependencies` array. **Shown catching the
thing it missed**, not merely existing: with `multipart` masked out,

```
passed: False | Missing packages: multipart
```

A hand-maintained list is only as good as whoever remembers to update it. This
one cannot fall behind the manifest, because it is the manifest.

**3. There was no Linux/macOS installer** — only `install.ps1`, while the clean
box that exposed all of this runs Linux. `scripts/install.sh` now has parity.

**4. The CPU torch index appeared nowhere.** On Linux `torch>=2.0` resolves to
the CUDA build and pulls ~2.96 GB of NVIDIA libraries — cudnn 651 MB, cublas
543 MB, triton 248 MB — that a machine without an NVIDIA GPU never loads. This
project pins `faiss-cpu`; CPU is the intended target.

`--cpu-torch` installs from `download.pytorch.org/whl/cpu`. The box confirms
`torch 2.14.0+cpu` and a **1.5 GB** venv.

## A fifth, found by running it

The first attempt died before pip:

```
/usr/bin/env: 'bash\r': No such file or directory
```

`scripts/install.sh` is committed with LF and a Linux clone gets LF, so this was
the harness shipping the Windows working-tree copy. But it is a real exposure:
`core.autocrlf=true` gives every Windows contributor CRLF in the working tree,
and one committed that way is a CRLF shebang on the exact platform the installer
exists to serve. `.gitattributes` now pins `*.sh text eol=lf`.

Worth stating plainly: this defect was invisible to inspection and took eleven
seconds to find by execution.

## What this does not establish

macOS is untested — `install.sh` targets both and only Linux was run. The
container had no GPU, so the CUDA path is unexercised; `--cpu-torch` is verified,
its absence is not. And a passing installer is not a working *product*: the box
started a backend with no model runtime, so nothing downstream of `/health` was
asked to do anything.
