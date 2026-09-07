"""The gates that exist, and whether they actually gate anything.

Three findings from the 2026-09-07 audit, each pinned so it cannot silently
come back:

* a reproducibility job that never ran,
* cloud sovereignty with no CI coverage at all,
* a spine hash that depended on how the repo was checked out.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]


def _ci() -> dict:
    with (REPO_ROOT / ".github" / "workflows" / "ci.yml").open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def test_the_reproducibility_gate_is_armed() -> None:
    """`golden-cohort-local` exists to fix "nobody else can re-run them".

    It was `workflow_dispatch` only, so it never ran on a PR or a push and
    fixed nothing. A reproducibility gate nobody triggers is a claim, not a
    gate.
    """
    job = _ci()["jobs"]["golden-cohort-local"]

    assert "if" not in job, (
        "golden-cohort-local is conditional again; if it only runs on demand it "
        "cannot answer the single-machine objection it was written for"
    )


def test_the_cloud_job_cannot_go_green_without_testing_anything() -> None:
    """A job that passes while exercising nothing is worse than no job.

    It looks like coverage. Every real step must be gated on credentials
    actually being present, so an unconfigured run reports its own absence
    rather than a tick.
    """
    steps = _ci()["jobs"]["cloud-contract"]["steps"]

    real = [s for s in steps if "pytest" in str(s.get("run", ""))]
    assert real, "the cloud job no longer runs anything even when configured"
    for step in real:
        assert "configured == 'true'" in str(step.get("if", "")), (
            f"step {step.get('name')!r} would run without credentials, so the "
            "job could go green having contacted no provider"
        )

    reporter = [s for s in steps if "SKIPPED" in str(s.get("run", ""))]
    assert reporter, "nothing announces the absence of cloud coverage"


def test_the_spine_is_pinned_to_lf() -> None:
    """Otherwise the spine hash describes a working tree, not the code."""
    attrs = (REPO_ROOT / ".gitattributes").read_text(encoding="utf-8")

    assert "aios/security/*.py text eol=lf" in attrs


def test_the_spine_hash_is_the_same_from_any_checkout() -> None:
    """THE BAR. Same commit -> same hash, on every machine.

    Measured before the pin: this Windows tree gave 52e393d0..., a pure-CRLF
    checkout gave c5ff3913..., and the committed bytes gave c980c996... --
    three values for one commit, so the number could not be compared or
    published.

    Compares the WORKING TREE against the bytes git actually stores, which is
    what another machine would check out.
    """
    import hashlib

    from aios.boot_attestation import compute_spine_hash

    files = sorted(
        subprocess.run(
            ["git", "ls-files", "aios/security/*.py"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        ).stdout.split(),
        key=lambda p: p.split("/")[-1],
    )
    if not files:
        import pytest

        pytest.skip("not a git checkout")

    digests = [
        hashlib.sha256(
            subprocess.run(
                ["git", "show", f"HEAD:{f}"], cwd=REPO_ROOT, capture_output=True
            ).stdout
        ).hexdigest()
        for f in files
    ]
    committed = hashlib.sha256("".join(digests).encode("utf-8")).hexdigest()
    working = compute_spine_hash(REPO_ROOT / "aios" / "security")

    assert working == committed, (
        "the working tree hashes differently from the committed bytes, so the "
        "spine hash still depends on how the repo was checked out"
    )


def test_the_pin_changed_no_frozen_content() -> None:
    """Line endings only. `aios/security/*` is frozen core (SS VIII)."""
    diff = subprocess.run(
        ["git", "diff", "HEAD", "--stat", "--", "aios/security/"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    ).stdout.strip()

    assert diff == "", f"the frozen spine has uncommitted changes:\n{diff}"
