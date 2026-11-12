"""The Security Queen's path rules on Windows spellings (2026-11-12).

Found while building GAGOS's sandbox verification: the queen compared
protected paths case-sensitively, so on Windows "AIOS/SECURITY/x.py" (which IS
aios/security/x.py) was not seen as protected; and its normaliser's
``lstrip("./")`` ate a dotfile's own dot. Now the comparison is
case-insensitive, and what Windows reads as another path (":" streams, 8.3
short names, a segment ending in a dot or a space) is unsafe, by the same
rules GAGOS's envelope applies.
"""

from __future__ import annotations

import pytest

from aios.council.queens.planner import CouncilMissionRequest, PlannerQueen
from aios.council.queens.security import SecurityQueen


def _review(*files: str):
    request = CouncilMissionRequest(
        mission_id="mission-0123456789ab",
        goal="change a file",
        workspace_root=".",
        allowed_files=list(files),
        allowed_tools=["read_file", "write_file"],
    )
    return SecurityQueen().review(PlannerQueen().draft(request).contract)


@pytest.mark.parametrize(
    "rule",
    [
        "AIOS/SECURITY/gateway.py",
        "aios/Security/gateway.py",
        r"aios\SECURITY\gateway.py",
        r".\AIOS\security\gateway.py",
        "AIOS/CORE/EXECUTOR.py",
        "aios/core/Approvals.py",
    ],
)
def test_the_protected_foundation_in_any_case_is_denied(rule) -> None:
    verdict = _review(rule)
    assert verdict.verdict == "deny"
    assert "Protected foundation" in verdict.reason


@pytest.mark.parametrize(
    "rule",
    [
        "aios/security./gateway.py",
        "aios/security /gateway.py",
        "aios/SECURI~1/gateway.py",
        "aios/core/x.py:hidden",
        "aios/core/x.py::$DATA",
        "aios/core/x.py.",
        "frontend/src/x|y.ts",
    ],
)
def test_windows_spellings_of_another_path_are_unsafe(rule) -> None:
    verdict = _review(rule)
    assert verdict.verdict == "deny"
    assert "Unsafe allowed file rule" in verdict.reason


def test_ordinary_files_still_pass() -> None:
    verdict = _review(
        "frontend/src/superbrain/lib/tabStore.ts", "./aios/core/router.py"
    )
    assert verdict.verdict != "deny", verdict.reason


def test_a_dotfile_keeps_its_dot() -> None:
    queen = SecurityQueen()
    assert queen._normalize_path_rule(".env") == ".env"
    assert (
        queen._normalize_path_rule("./.github/workflows/ci.yml")
        == ".github/workflows/ci.yml"
    )
    assert queen._normalize_path_rule(r".\aios\x.py") == "aios/x.py"
