#!/usr/bin/env bash
# GAGOS installer for Linux and macOS -- parity with install.ps1.
#
# Written 2026-09-07 because the clean-box stranger test ran on Linux and there
# was no installer for it: install.ps1 is PowerShell only, so every non-Windows
# newcomer was following README prose by hand.
#
#   --cpu-torch      install the CPU-only torch build (see below)
#   --skip-health    skip the closing `python -m aios bootstrap`
set -euo pipefail

CPU_TORCH=0
SKIP_HEALTH=0
for arg in "$@"; do
  case "$arg" in
    --cpu-torch)   CPU_TORCH=1 ;;
    --skip-health) SKIP_HEALTH=1 ;;
    -h|--help)     sed -n '2,10p' "$0"; exit 0 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

step() { printf '\n==> %s\n' "$*"; }
here="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$here"

step "Checking Python"
PY=""
for cand in python3 python; do
  if command -v "$cand" >/dev/null 2>&1; then PY="$cand"; break; fi
done
[ -n "$PY" ] || { echo "No python3 on PATH. Install Python 3.11 or newer." >&2; exit 1; }
"$PY" - <<'CHECK'
import sys
if sys.version_info < (3, 11):
    sys.exit(f"Python 3.11 or newer required; found {sys.version.split()[0]}")
print(f"  {sys.version.split()[0]}")
CHECK

step "Creating the virtual environment at .venv"
if [ ! -d .venv ]; then
  # `python3 -m venv` needs ensurepip, which some distros ship separately
  # (Debian/Ubuntu: python3-venv). Say so rather than emitting its raw error.
  "$PY" -m venv .venv 2>/dev/null || {
    echo "venv creation failed -- on Debian/Ubuntu install python3-venv" >&2
    exit 1
  }
else
  echo "  .venv already exists"
fi
VENV_PY=".venv/bin/python"

step "Upgrading pip"
"$VENV_PY" -m pip install --quiet --upgrade pip

if [ "$CPU_TORCH" = "1" ]; then
  step "Installing the CPU-only torch build first"
  # MEASURED 2026-09-07: on Linux, torch>=2.0 resolves to the CUDA build and
  # drags in ~2.96 GB of NVIDIA libraries (cudnn 651 MB, cublas 543 MB, triton
  # 248 MB, ...) that a CPU-only machine never loads. The project pins
  # faiss-cpu, so CPU is the intended target.
  "$VENV_PY" -m pip install --index-url https://download.pytorch.org/whl/cpu torch
fi

step "Installing the project"
"$VENV_PY" -m pip install -e ".[test]"

step "Writing .env if absent"
# ONE template, shared with `python -m aios bootstrap --create-env`. It carries a
# freshly generated AIOS_VERIFICATION_AUTHORITY_KEY, so the file is usable as
# written -- install.ps1 used to keep its own copy that omitted that key
# entirely, which is the value the README calls genuinely required.
"$VENV_PY" - <<'ENVGEN'
from pathlib import Path
from aios.bootstrap import write_env_template
created = write_env_template(Path(".env"))
print("  created .env" if created else "  .env already exists; left alone")
ENVGEN

if [ "$SKIP_HEALTH" = "0" ]; then
  step "Health check"
  "$VENV_PY" -m aios bootstrap || {
    echo "bootstrap reported problems above. The install completed; fix those before starting." >&2
    exit 1
  }
fi

step "Done"
cat <<'NEXT'
  Activate:  source .venv/bin/activate
  Start:     python -m aios
  Diagnose:  python -m aios doctor
NEXT
