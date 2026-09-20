"""The executor's remote workspace path must be POSIX on every host.

`_probe_executor` sends `workspace_snapshot` to a Linux container, and the
executor refuses anything outside its staging root (`_workspace_allowed`,
HTTP 403). Built with `pathlib.Path`, that string is separator-dependent: on
Windows `Path("/workspace/jobs") / name` renders with backslashes, every job is
refused, and organ 40's own live probe reports HTTP 403 -- which reads as
"isolation is broken" rather than "the path was mis-built".

tests/test_executor_integration.py never caught this because it composes the
same path with an f-string, so the two derivations disagreed exactly where it
mattered. This test pins the production one.
"""

from __future__ import annotations

import sys
from pathlib import PurePosixPath, PureWindowsPath

import pytest

from aios.application.governance import runtime_proof as rp
from tests.source_rules import executable_source


def test_remote_path_uses_posix_separators_on_any_host() -> None:
    """The invariant, stated against the construction the code performs."""
    remote = PurePosixPath("/workspace/jobs") / "gagos-v1-proof-deadbeef"
    assert str(remote) == "/workspace/jobs/gagos-v1-proof-deadbeef"
    assert "\\" not in str(remote)


def test_windows_path_construction_would_be_refused() -> None:
    """Why the fix matters: the old construction yields a refused string.

    Asserted through PureWindowsPath so the regression is visible on Linux CI
    too -- a Windows-only failure that only reproduces on Windows is exactly
    the kind that ships.
    """
    bad = PureWindowsPath("/workspace/jobs") / "gagos-v1-proof-deadbeef"
    assert "\\" in str(bad)
    assert not str(bad).startswith("/workspace/jobs")


def test_probe_executor_builds_the_remote_path_with_purePosixPath() -> None:
    """Structural: the production line must not use the OS-dependent Path."""
    src = executable_source(rp._probe_executor)
    assert "PurePosixPath(config.EXECUTOR_REMOTE_WORKSPACE_ROOT)" in src, (
        "the remote workspace path must be built with PurePosixPath; "
        "pathlib.Path is separator-dependent and yields a 403 on Windows"
    )
    assert "Path(config.EXECUTOR_REMOTE_WORKSPACE_ROOT) /" not in src.replace(
        "PurePosixPath(config.EXECUTOR_REMOTE_WORKSPACE_ROOT) /", ""
    )
