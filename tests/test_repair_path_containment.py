"""The repair path checked containment lexically, and claimed isolation on failure.

Two defects, measured 2026-09-13 against `execute_registered_operation_in_service`.

CONTAINMENT. The target was resolved with `os.path.normpath` and checked with
`startswith`, which is a LEXICAL test -- it does not resolve symlinks. The only
link check was `target_path.is_symlink()`, which inspects the FINAL COMPONENT
only. So a redirected *intermediate directory* passed both: the path stays
lexically inside the staged root, and the leaf is an ordinary file.

Run end-to-end it returned `status="completed"`, `isolation_verified=True`, and
modified a file outside the staged root.

Note the fix cannot be "check `is_symlink()` on every component". On Windows a
DIRECTORY JUNCTION redirects exactly like a symlink, needs no privileges to
create, and `Path.is_symlink()` reports **False** for it. Only canonicalisation
catches that -- which is why this refuses on `realpath` instead.

`aios/infrastructure/executor/workspace.py::resolve_staged_workspace` already
did it correctly, on both sides, and is described in its own docstring as "the
trust boundary for the authenticated executor service". The repair path
re-derived the same question lexically a few lines after calling it. One
derivation, two callers -- the shape that caught two earlier escapes in this
repo.

EVIDENCE. Ten `status="failed"` returns reported `isolation_verified=True`,
including the refusals above. That field is not decoration: the executor service
gates on it (`require_isolation` in application/executor/service.py) and the
maintenance service reads it before trusting a repair. A field asserting
isolation was verified, on a path where nothing was verified, is this project's
narration-vs-evidence defect living inside the executor.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import tempfile

import pytest

from aios.domain.executor.protocol import ExecutorCapability, ExecutorJob

MARKER = "# DEFECT_MARKER: fix_required\n"


def _job(argv: tuple[str, ...], snapshot: str) -> ExecutorJob:
    return ExecutorJob(
        job_id="job-1",
        mission_contract_digest="d" * 64,
        capability=ExecutorCapability(
            capability_id="cap-1",
            action_digest="a" * 64,
            mission_contract_digest="d" * 64,
            expires_at="2099-01-01T00:00:00+00:00",
        ),
        image="none",
        argv=argv,
        workspace_snapshot=snapshot,
    )


def _redirect_dir(link: pathlib.Path, target: pathlib.Path) -> str:
    """Make *link* resolve to *target*, by whatever the platform allows.

    Returns the mechanism used, or "" when none is available. Windows symlinks
    need a privilege that ordinary users lack, but junctions do not -- and a
    junction is the more interesting case anyway, since `is_symlink()` is blind
    to it.
    """
    try:
        os.symlink(target, link, target_is_directory=True)
        return "symlink"
    except (OSError, NotImplementedError, AttributeError):
        pass
    if os.name == "nt":
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],
            capture_output=True,
            text=True,
        )
        if link.exists():
            return "junction"
        del result
    return ""


@pytest.fixture()
def planted(monkeypatch: pytest.MonkeyPatch) -> tuple[pathlib.Path, pathlib.Path, str]:
    """A staged root containing a directory that really points outside it."""
    root = pathlib.Path(tempfile.mkdtemp(prefix="aios-containment-"))
    outside = root / "OUTSIDE"
    outside.mkdir()
    victim = outside / "secret.txt"
    victim.write_text(MARKER + "OPERATOR SECRET\n", encoding="utf-8")

    staged = root / "staged"
    staged.mkdir()
    mechanism = _redirect_dir(staged / "sub", outside)
    if not mechanism:
        pytest.skip("no symlink or junction available on this platform")

    monkeypatch.setenv("AIOS_EXECUTOR_WORKSPACE_ROOT", str(root))
    return staged, victim, mechanism


def test_the_plant_really_does_redirect_outside(
    planted: tuple[pathlib.Path, pathlib.Path, str],
) -> None:
    """Guards the guard: if the plant did not escape, the test below is vacuous."""
    staged, victim, _ = planted
    through_link = staged / "sub" / "secret.txt"

    assert through_link.exists(), "the planted directory does not resolve"
    assert os.path.realpath(through_link) == os.path.realpath(victim)
    assert not os.path.realpath(through_link).startswith(
        os.path.realpath(staged) + os.sep
    ), "the plant resolves inside the staged root, so it proves nothing"


def test_a_redirected_intermediate_directory_is_refused(
    planted: tuple[pathlib.Path, pathlib.Path, str],
) -> None:
    """THE BAR. Containment must survive a path that only looks contained."""
    from aios.executor_service import execute_registered_operation_in_service

    staged, victim, _ = planted
    before = victim.read_text(encoding="utf-8")

    result = execute_registered_operation_in_service(
        _job(("repair", "REMOVE_MAINTENANCE_MARKER_V1", "sub/secret.txt"), str(staged))
    )

    assert result.status == "failed", (
        "a repair reached outside the staged workspace and reported success"
    )
    assert victim.read_text(encoding="utf-8") == before, (
        "the file outside the staged root was modified"
    )


def test_a_refusal_never_claims_isolation_was_verified(
    planted: tuple[pathlib.Path, pathlib.Path, str],
) -> None:
    """`isolation_verified` is read by `require_isolation`; it must be earned."""
    from aios.executor_service import execute_registered_operation_in_service

    staged, _, _ = planted

    result = execute_registered_operation_in_service(
        _job(("repair", "REMOVE_MAINTENANCE_MARKER_V1", "sub/secret.txt"), str(staged))
    )

    assert result.isolation_verified is False, (
        "a containment refusal reported isolation_verified=True"
    )


@pytest.mark.parametrize(
    ("argv", "what"),
    [
        (("notrepair",), "argv that is not a repair operation"),
        (("repair", "NOT_AN_OP", "x.txt"), "an unsupported operation id"),
        # NB: shell metacharacters are not listed here. `ExecutorJob` refuses
        # them in its own validator, so the executor's forbidden-character
        # branch cannot be reached through this constructor at all -- it is
        # defence in depth behind a guard that fires first.
        (("repair", "REMOVE_MAINTENANCE_MARKER_V1", "../escape.txt"), "traversal"),
        (("repair", "REMOVE_MAINTENANCE_MARKER_V1", "/abs.txt"), "an absolute path"),
        (("repair", "REMOVE_MAINTENANCE_MARKER_V1", "missing.txt"), "a missing target"),
    ],
)
def test_no_failure_path_claims_isolation_was_verified(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    argv: tuple[str, ...],
    what: str,
) -> None:
    """Every refusal, not just the interesting one.

    Ten separate `status="failed"` returns carried `isolation_verified=True`.
    Fixing only the containment branch would leave the field lying on nine
    others, so the property is asserted across the refusal surface.
    """
    from aios.executor_service import execute_registered_operation_in_service

    staged = tmp_path / "staged"
    staged.mkdir()
    monkeypatch.setenv("AIOS_EXECUTOR_WORKSPACE_ROOT", str(tmp_path))

    result = execute_registered_operation_in_service(_job(argv, str(staged)))

    assert result.status == "failed", f"expected a refusal for {what}"
    assert result.isolation_verified is False, (
        f"the refusal for {what} reported isolation_verified=True; "
        "require_isolation trusts that field"
    )


def test_an_ordinary_in_root_repair_still_succeeds(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A containment rule that refuses the legitimate case is not a fix."""
    from aios.executor_service import execute_registered_operation_in_service

    staged = tmp_path / "staged"
    (staged / "pkg").mkdir(parents=True)
    target = staged / "pkg" / "mod.py"
    target.write_text(MARKER + "value = 1\n", encoding="utf-8")
    monkeypatch.setenv("AIOS_EXECUTOR_WORKSPACE_ROOT", str(tmp_path))

    result = execute_registered_operation_in_service(
        _job(("repair", "REMOVE_MAINTENANCE_MARKER_V1", "pkg/mod.py"), str(staged))
    )

    assert result.status == "completed", f"legitimate repair refused: {result.reason}"
    assert result.isolation_verified is True
    assert "DEFECT_MARKER" not in target.read_text(encoding="utf-8")
