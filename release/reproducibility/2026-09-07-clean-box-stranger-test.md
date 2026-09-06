# Clean-box stranger test — 2026-09-07

**It works.** On a stock `quay.io/fedora/fedora:40` container, following
`README.md` §§1–6 literally, the backend starts and answers `GET /health` with
**200**.

This is the run the 2026-09-06 log said was owed. That one was explicitly
**degraded** — fresh clone and venv, but the same OS and toolchain — and it still
found a blocker that stopped the backend starting at all. This one is a genuine
clean box: different OS, no Python packages, no toolchain, nothing of mine.

```
Fedora release 40 (Forty)
python3   /usr/bin/python3   3.12.10
git       ABSENT
pip       ABSENT

step 1  git clone                 exit 0
step 2  python3 -m venv .venv     exit 0
        pip install -e ".[test]"  exit 0
step 3  cp .env.example .env      exit 0
step 5  python -m aios            BACKEND UP, HTTP 200
```

**The `python-multipart` fix from #294 holds on a real clean box.** That was the
blocker the degraded run found; it does not recur here.

## The finding: ~3 GB of CUDA on a CPU-only machine

`torch>=2.0` on Linux resolves to the **CUDA** build by default, so the install
pulls the entire NVIDIA stack onto a box that has no GPU:

```
nvidia-cudnn-cu13     651 MB      nvidia-cufft          214 MB
torch                 555 MB      nvidia-cusparse       162 MB
nvidia-cublas         543 MB      nvidia-cuda-nvrtc      90 MB
triton                248 MB      nvidia-curand          62 MB
nvidia-cusolver       223 MB      + nvidia-nvshmem, nvjitlink, nvtx,
nvidia-nccl-cu13      216 MB        cufile, cupti, cuda-runtime, ...

measured subtotal (largest linux wheels): 2.96 GB
```

Measured from the PyPI metadata for the exact versions the run installed, not
estimated. It is a **subtotal** — several smaller `nvidia-*` packages are not
counted.

The project pins `faiss-cpu`, so CPU is plainly the intended target. A newcomer
on a CPU-only Linux machine currently downloads ~3 GB of GPU libraries they will
never load. The 2026-09-06 log recorded "multi-GB before anything runs" as
*context*; this is that number, measured, on the platform where it is worst.

The obvious remedy is the CPU wheel index
(`--index-url https://download.pytorch.org/whl/cpu`), but **that is not applied
here**: this file is a measurement, and the installer work it feeds is supposed
to be driven by the log rather than guessed alongside it.

## A finding I retracted against myself

My harness reported that `.env.example` offers no
`AIOS_VERIFICATION_AUTHORITY_KEY` line to fill in, because it grepped for
`^AIOS_VERIFICATION_AUTHORITY_KEY=`.

**False.** `.env.example:83` carries `# AIOS_VERIFICATION_AUTHORITY_KEY=` — a
correct commented placeholder that a newcomer uncomments. The strict anchor was
my script's error, not the template's.

This is the second stranger test in a row where the harness produced a false
finding. The first one (`ls .env .env.example`, which exits non-zero if *either*
path is missing) was acted on and destroyed a 12 KB file before being caught. A
test that reports a gap must be reproduced before the gap is "fixed".

## Honest limits

- **Not tested: whether `python3 -m venv` works without `python3-pip`.** The
  script installed `git` and `python3-pip` up front, so that path is unmeasured.
  The README's Requirements list names Python, Node and Git — all accurate — but
  stock Fedora 40 ships neither `git` nor `pip`, and only the former is listed.
- The frontend (§6) was not started; this covers the backend path only.
- One distro. A Debian/Ubuntu box may differ, and the Windows path is unchanged
  and separately evidenced.
- No mission or cohort was run inside the container — this measures *install and
  start*, nothing about governance behaviour.

## Incidental

The run installed `torch-2.14.0`, `pydantic-2.13.5` and `pydantic-core-2.46.5` —
the versions dependabot proposes in #309 — and the backend started on them. That
is weak positive evidence for that PR, not a substitute for its CI.
