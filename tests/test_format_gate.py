"""The repo-wide formatting gate, and the two things it is allowed to skip.

The gate this replaced was a hand-maintained list of ~22 paths in ci.yml, and
that is precisely how release-authority went red: six files drifted out of
compliance and only one of them was on the list. Coverage depended on whoever
added a file remembering to add it twice.

A repo-wide check has no list to fall behind. But it needs exclusions, and an
exclusion list is the same hazard in a smaller box -- so these tests assert that
the exclusions are exactly the two deliberately-frozen sets and nothing else.
"""

from __future__ import annotations

import re
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

#: The only paths the formatter may skip, and why each is frozen or excluded.
#:
#: aios/security/*.py     boot_attestation.compute_spine_hash hashes these
#:                        bytes; reformatting one breaks
#:                        verify_spine_integrity (and AGENTS.md SS VIII).
#: tests/golden/fixture   SelfAnalysisAgent flags long functions by LINE COUNT,
#:                        so reformatting moved the fixture across the
#:                        threshold and changed the analyzer's diagnosis.
#: training_ground, lab   The RUNTIME SANDBOX scope roots (config.SCOPE_ROOTS).
#:                        The agent writes files here while it works, so gating
#:                        CI on their formatting would fail the build on what a
#:                        curriculum run happened to produce.
_ALLOWED_FORMAT_EXCLUSIONS = {
    "aios/security/*.py",
    "tests/golden/fixture/**/*.py",
    "training_ground/**/*.py",
    "lab/**/*.py",
}


def _format_exclusions() -> set[str]:
    with (REPO_ROOT / "pyproject.toml").open("rb") as fh:
        config = tomllib.load(fh)
    return set(config["tool"]["ruff"]["format"]["exclude"])


def test_the_formatter_skips_exactly_the_two_frozen_sets() -> None:
    """An exclusion list is a place to hide a regression. Pin it.

    Adding a third entry is the cheap way to make a formatting failure go away,
    and it would look like configuration rather than like the suppression it is.
    """
    assert _format_exclusions() == _ALLOWED_FORMAT_EXCLUSIONS


def test_excluding_from_format_does_not_exclude_from_lint() -> None:
    """The spine must still be LINTED. `formatter.exclude` is not `linter.exclude`.

    This is the whole reason the exclusion is expressible at all. If a future
    edit moved these patterns to the top-level `exclude` key, ruff would stop
    linting the most security-critical code in the repo and every check would
    still pass -- silently, because there would be nothing left to report.
    """
    with (REPO_ROOT / "pyproject.toml").open("rb") as fh:
        ruff = tomllib.load(fh)["tool"]["ruff"]

    assert "exclude" not in ruff, (
        "a top-level ruff `exclude` would drop LINT coverage, not just formatting"
    )
    assert "extend-exclude" not in ruff

    listed = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "aios/security/", "--show-files"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    ).stdout
    checked = {Path(line).name for line in listed.splitlines() if line.strip()}

    for spine in (
        "gateway.py",
        "scope_lock.py",
        "audit_logger.py",
        "secret_scanner.py",
    ):
        assert spine in checked, f"ruff check no longer lints {spine}"


def test_the_repo_is_format_clean() -> None:
    """What the gate asserts, asserted locally so it fails before CI does."""
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "format", "--check", "."],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout


def test_the_gate_actually_fails_on_a_misformatted_file(tmp_path) -> None:
    """A gate that has never failed is indistinguishable from one that cannot.

    Run against a throwaway file rather than dirtying the repo -- the point is
    to prove the checker reports, not to prove ruff works.
    """
    bad = tmp_path / "bad.py"
    bad.write_text("def f( a,b ):\n  return   a+b\n", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, "-m", "ruff", "format", "--check", str(bad)],
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0, "the format check passed a misformatted file"


# --------------------------------------------------------------------------- #
# The pin
# --------------------------------------------------------------------------- #


def _ci_text() -> str:
    return (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")


def test_ruff_is_pinned_once_for_the_whole_workflow() -> None:
    """Two pins disagreed, and the disagreement was invisible until now.

    release-authority pinned 0.9.10 while the repo was swept with 0.15.22. The
    two format a long lambda parameter list differently and each undoes the
    other, so NO single byte-state satisfies both. That stayed hidden while the
    gate checked only ~22 files; widening it repo-wide surfaced it immediately
    (tests/test_conversation_pipeline.py).

    One pin, referenced everywhere, is the only arrangement where "the repo is
    formatted correctly" is a well-defined claim.
    """
    text = _ci_text()

    literal_pins = re.findall(r"ruff==(?!\$\{\{)[0-9]", text)
    assert not literal_pins, (
        "a literal ruff== pin reappeared; use ${{ env.RUFF_VERSION }} so the "
        "workflow cannot disagree with itself"
    )
    assert re.search(r'^  RUFF_VERSION: "[0-9]+\.[0-9]+\.[0-9]+"$', text, re.M)


def test_the_pinned_version_is_the_one_running_here() -> None:
    """Local ruff and the gate's ruff must agree, or 'clean' means two things.

    Skipped rather than failed when they differ: a contributor on another ruff
    is not a broken repo, but they cannot trust a local pass either, and this
    says so out loud instead of letting them find out in CI.
    """
    pinned = re.search(r'^  RUFF_VERSION: "([^"]+)"$', _ci_text(), re.M).group(1)
    local = subprocess.run(
        [sys.executable, "-m", "ruff", "--version"], capture_output=True, text=True
    ).stdout.split()[-1]

    if local != pinned:
        pytest.skip(
            f"local ruff {local} != gate pin {pinned}; a local format pass does "
            "not predict the gate's verdict"
        )
    assert local == pinned
