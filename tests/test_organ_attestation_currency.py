"""An attestation the code has moved out from under is not evidence.

WHY THIS FILE EXISTS. The twelve-condition green contract asks, in C12, whether
`last_verified_sha` is an ANCESTOR of HEAD:

    elif ancestry_fn(root, sha) is False:
        failures.append(("C12", f"last_verified_sha {sha} is not an ancestor..."))

An old commit is an ancestor of HEAD forever. So an organ verified once stays
green however far the code beneath it travels, and nothing in C1-C12 notices.

Measured 2026-09-13, before this rule existed:

    38 of 55 organs pinned to one sha dated 2026-07-31
    199 commits landed since
    46 of 55 organs had their OWN production_entrypoints change after their
       attestation -- all 46 of them green

That is not a hypothetical drift. Three PRs in the same week (#328, #329, #330)
found live ungoverned production objects -- a CapabilityAuthority issuing
capabilities the emergency stop could not halt, MissionService built with no
latch in four production sites, thirteen runtime boundaries whose stop check
returned silently when nothing was wired -- every one inside a GREEN organ, and
not one line of the ledger changed.

The rule here is relevance, not age. An organ whose entrypoints have not been
touched since it was verified is still telling the truth however old it is. A
two-day-old attestation over a file that changed yesterday is not.
"""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

_spec = importlib.util.spec_from_file_location(
    "_verify_currency", REPO_ROOT / "scripts" / "verify_organ_twelve_conditions.py"
)
_verify = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_verify)


def _record(sha: str | None, entrypoints: list[str]):
    return SimpleNamespace(
        organ_id=999,
        name="probe",
        last_verified_sha=sha,
        production_entrypoints=entrypoints,
    )


def _sha_that_predates(path: str) -> str | None:
    """A commit from before *path* last changed, or None if history is too thin."""
    out = subprocess.run(
        ["git", "log", "--format=%H", "-2", "--", path],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    ).stdout.split()
    return out[1] if len(out) > 1 else None


def test_the_organ_that_was_green_over_thirteen_fail_open_boundaries_is_flagged() -> (
    None
):
    """THE BAR, reproduced against the real ledger rather than asserted.

    Organ 26's authority owner is `EmergencyStopHardWiringAuthority` and its
    `production_entrypoints` are -- exactly -- the files whose stop check was
    fail-open: the gateway, learning, maintenance, recovery, capabilities,
    main.py, actions and council routes.

    It declared C1-C12 PASS over the thirteen boundaries that could not be
    halted. This rule is the one that refuses that.
    """
    from aios.application.governance.organ_ledger import load_ledger

    ledger = load_ledger(REPO_ROOT / ".aios/state/ORGAN_GREEN_LEDGER.json")
    organ_26 = next((r for r in ledger if r.organ_id == 26), None)
    assert organ_26 is not None, "organ 26 is missing from the ledger"

    failures = _verify._staleness_failures(organ_26, REPO_ROOT)

    assert failures, (
        "organ 26's attestation is treated as current even though the files it "
        "attests to have changed -- the exact gap that let it stay green over "
        "thirteen fail-open boundaries"
    )
    condition, message = failures[0]
    assert condition == "C12"
    assert "STALE" in message
    assert "production_entrypoints" in message


def test_an_untouched_entrypoint_is_not_called_stale() -> None:
    """A rule that fires on a truthful attestation is worse than no rule.

    `AGENTS.md` has not changed in a long time and is not an entrypoint of
    anything; pinned at HEAD, nothing has moved since, so nothing is stale.
    """
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True
    ).stdout.strip()

    assert not _verify._staleness_failures(_record(head, ["AGENTS.md"]), REPO_ROOT)


def test_a_file_that_changed_after_the_attestation_is_stale() -> None:
    """The mechanism itself, on a synthetic record.

    Pins the rule independently of whatever the shipped ledger happens to say,
    so it keeps meaning something after the re-verification sweep.
    """
    target = "scripts/verify_organ_twelve_conditions.py"
    older = _sha_that_predates(target)
    if older is None:  # pragma: no cover - only in a shallow clone
        pytest.skip("history too shallow to name a commit before the last change")

    failures = _verify._staleness_failures(_record(older, [target]), REPO_ROOT)

    assert failures, f"{target} changed after {older[:12]} and was not flagged"
    assert target in failures[0][1]


def test_an_organ_with_no_entrypoints_is_left_to_the_other_conditions() -> None:
    """Scoped deliberately: this rule answers one question and no others.

    With nothing declared to attest to, there is nothing to be stale about --
    C1 and C2 are the conditions that care about a missing entrypoint list.
    """
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True
    ).stdout.strip()

    assert not _verify._staleness_failures(_record(head, []), REPO_ROOT)


def test_a_missing_sha_is_left_to_c11() -> None:
    """C11 already reports a missing or malformed sha; do not double-report it.

    Organ 55 legitimately carries a null sha while it awaits the operator's
    attestation, and must not collect a second, misleading failure here.
    """
    assert not _verify._staleness_failures(_record(None, ["AGENTS.md"]), REPO_ROOT)
    assert not _verify._staleness_failures(
        _record("not-a-sha", ["AGENTS.md"]), REPO_ROOT
    )
