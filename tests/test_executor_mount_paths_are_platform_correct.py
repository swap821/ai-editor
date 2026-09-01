r"""Writable scope-root mounts must use the host's own path separators.

Found by the FIRST real container run of the containment suite, 2026-09-01, on
CI (Linux, Python 3.12). Docker refused every container with::

    invalid mount config for type "bind": bind source path does not exist:
    \home\runner\work\ai-editor\ai-editor\training_ground

Backslashes, on Linux. `_writable_scope_mounts` chose between Windows and POSIX
path handling with `ntpath.isabs`, and that predicate is version-dependent:

    Python 3.12:  ntpath.isabs("/home/runner/x")  ->  True
    Python 3.13+: ntpath.isabs("/home/runner/x")  ->  False

A leading slash is "absolute" under Windows semantics (drive-relative), so on
Python 3.12 every POSIX absolute path took the Windows branch and
`ntpath.normpath` rewrote the separators.

**`DockerRunner` was therefore broken outright on Linux** from the 2026-08-19
containment fix until this was caught. Three things hid it:

* the unit tests assert the CONSTRUCTED argv, and are run on Windows, where the
  branch happens to be correct;
* `tests/test_executor_integration.py` exercises the Executor *Service*, a
  different code path;
* the operator's machine is Windows on Python 3.14, where `ntpath.isabs`
  already returns False.

The PREDICATE tests run on any platform, and the predicate IS the fix -- they
would have caught this outage from a Windows laptop. The end-to-end resolver
cases are platform-gated on purpose: `pathlib.Path` is platform-bound, so on
Windows `Path("/home/x").resolve()` yields `C:\home\x`, and faking that would
test the fake. The POSIX cases run on CI's Linux, which is where the bug lived.
"""

from __future__ import annotations

import ntpath
import os
from pathlib import Path, PureWindowsPath

import pytest

from aios.core import executor as executor_module
from aios.core.executor import _is_windows_style, _writable_scope_mounts

#: The end-to-end resolver tests below cannot be faked on the other platform:
#: `pathlib.Path` is platform-bound, so on Windows `Path("/home/x").resolve()`
#: yields `C:\home\x`. Simulating it would test the simulation. The
#: cross-platform guard is `_is_windows_style` itself, exercised above -- that
#: predicate IS the fix, and it would have caught the outage on any host.
_posix_only = pytest.mark.skipif(
    os.name == "nt",
    reason="pathlib.Path is platform-bound; the POSIX resolver path runs on CI's Linux",
)
_windows_only = pytest.mark.skipif(
    os.name != "nt", reason="Windows drive-path resolution needs a Windows host"
)


def _mount_sources(mounts: list[str]) -> list[str]:
    """The `src=` value of every `--mount` spec."""
    sources: list[str] = []
    for spec in mounts:
        if not spec.startswith("type=bind"):
            continue
        for field in spec.split(","):
            if field.startswith("src="):
                sources.append(field[len("src=") :])
    return sources


# --------------------------------------------------------------------------- #
# The predicate
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "path, expected",
    [
        ("/home/runner/work/ai-editor/ai-editor/training_ground", False),
        ("/tmp/scope", False),
        ("/", False),
        ("C:\\Users\\k\\training_ground", True),
        ("D:/projects/lab", True),
        ("\\\\server\\share\\scope", True),
    ],
)
def test_only_real_windows_paths_take_the_windows_branch(
    path: str, expected: bool
) -> None:
    """A drive or UNC prefix is what actually requires ntpath semantics."""
    assert _is_windows_style(path) is expected


def test_the_predicate_is_not_ntpath_isabs() -> None:
    """Pinning the exact confusion that caused the outage.

    On Python 3.12 this assertion's `ntpath.isabs` call returns True for a POSIX
    path; on 3.13+ it returns False. The point is that `_is_windows_style` must
    return False EITHER WAY -- its answer cannot depend on the interpreter.
    """
    posix = "/home/runner/work/ai-editor/ai-editor/training_ground"
    assert _is_windows_style(posix) is False, (
        "a POSIX absolute path was classified as Windows-style; on Python 3.12 "
        "ntpath.isabs() says True here, and using it as the discriminator is "
        f"what emitted {ntpath.normpath(posix)!r} to Docker"
    )


# --------------------------------------------------------------------------- #
# The resolver, driven with each platform's paths on any host
# --------------------------------------------------------------------------- #
@_posix_only
def test_posix_scope_roots_keep_forward_slashes(monkeypatch) -> None:
    """The regression, reproduced without needing to be on Linux."""
    base = "/home/runner/work/ai-editor/ai-editor"
    roots = (Path(f"{base}/training_ground"), Path(f"{base}/lab"))
    monkeypatch.setattr(executor_module, "get_scope_roots", lambda: roots)

    sources = _mount_sources(_writable_scope_mounts(base))

    assert sources, "no writable mounts were emitted for two declared roots"
    for src in sources:
        assert "\\" not in src, (
            f"a POSIX mount source contains backslashes: {src!r}. Docker will "
            "refuse the container with 'bind source path does not exist'."
        )
        assert src.startswith("/"), src


@_windows_only
def test_windows_scope_roots_keep_backslashes(monkeypatch) -> None:
    """The other platform must not regress while fixing the first."""
    base = "C:\\Users\\k\\ai-editor"
    roots = (
        PureWindowsPath(f"{base}\\training_ground"),
        PureWindowsPath(f"{base}\\lab"),
    )
    monkeypatch.setattr(executor_module, "get_scope_roots", lambda: roots)

    sources = _mount_sources(_writable_scope_mounts(base))

    assert sources, "no writable mounts were emitted for two declared roots"
    for src in sources:
        assert src.startswith("C:\\"), (
            f"a Windows mount source lost its drive/separators: {src!r}"
        )


@_posix_only
def test_each_root_is_remounted_at_its_own_workspace_path(monkeypatch) -> None:
    """The destination must mirror the layout inside /workspace.

    A correct source with a wrong destination is the same outage wearing a
    different hat, so both halves are asserted.
    """
    base = "/srv/checkout"
    roots = (Path(f"{base}/training_ground"), Path(f"{base}/lab"))
    monkeypatch.setattr(executor_module, "get_scope_roots", lambda: roots)

    mounts = _writable_scope_mounts(base)
    joined = ",".join(mounts)

    for name in ("training_ground", "lab"):
        assert f"src={base}/{name}," in joined, joined
        assert f"dst=/workspace/{name}," in joined, joined


@_posix_only
def test_a_root_outside_the_workspace_is_still_skipped(monkeypatch) -> None:
    """The containment rule the fix must not weaken.

    A root that is not under the mounted workspace is skipped rather than
    mounted somewhere invented -- widening the mount to reach it would hand the
    sandbox a path the workspace never contained.
    """
    base = "/srv/checkout"
    roots = (Path("/etc"), Path(f"{base}/training_ground"))
    monkeypatch.setattr(executor_module, "get_scope_roots", lambda: roots)

    sources = _mount_sources(_writable_scope_mounts(base))

    assert sources == [f"{base}/training_ground"], (
        f"an out-of-workspace root leaked into the writable set: {sources}"
    )
