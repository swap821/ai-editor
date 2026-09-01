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
# The resolver, against REAL directories on whatever host is running
# --------------------------------------------------------------------------- #
# These use `tmp_path` rather than fabricated absolute paths. The first version
# hard-coded "/home/runner/..." and passed on Linux while failing on macOS with
# "no writable mounts were emitted": `_writable_scope_mounts` calls `.resolve()`
# on each ROOT but not on the BASE, and macOS resolves `/home` and `/var`
# through symlinks -- so the two disagreed, `relative_to` raised, and every root
# was silently skipped. Real directories, with the base resolved the same way,
# keep the comparison honest on every platform.
#
# The separator assertion is therefore against `os.sep`, the host's own
# convention, which is the actual invariant. Hard-coding "/" would just move the
# platform bug into the test.


def _scope_fixture(tmp_path, monkeypatch, names):
    base = tmp_path.resolve()
    roots = []
    for name in names:
        root = base / name
        root.mkdir(parents=True, exist_ok=True)
        roots.append(root)
    monkeypatch.setattr(executor_module, "get_scope_roots", lambda: tuple(roots))
    return str(base), roots


def test_mount_sources_use_the_hosts_own_separators(tmp_path, monkeypatch) -> None:
    """The regression: a source with foreign separators is unmountable.

    On CI (Linux, Python 3.12) every source came out with backslashes and Docker
    refused the container with "bind source path does not exist".
    """
    base, _ = _scope_fixture(tmp_path, monkeypatch, ("training_ground", "lab"))

    sources = _mount_sources(_writable_scope_mounts(base))

    assert len(sources) == 2, f"expected one mount per declared root, got {sources}"
    foreign = "/" if os.sep == chr(92) else chr(92)
    for src in sources:
        assert foreign not in src, (
            f"mount source {src!r} uses foreign separators for this host "
            f"(os.sep={os.sep!r}); Docker will refuse it with 'bind source path "
            "does not exist'"
        )
        assert src.startswith(base), f"{src!r} is not under the workspace {base!r}"


def test_each_root_is_remounted_at_its_own_workspace_path(
    tmp_path, monkeypatch
) -> None:
    """The destination must mirror the layout inside /workspace.

    A correct source with a wrong destination is the same outage wearing a
    different hat, so both halves are asserted. Destinations are always POSIX --
    they name paths INSIDE the Linux container, whatever the host is.
    """
    base, _ = _scope_fixture(tmp_path, monkeypatch, ("training_ground", "lab"))

    joined = ",".join(_writable_scope_mounts(base))

    for name in ("training_ground", "lab"):
        assert f"dst=/workspace/{name}," in joined, joined


def test_a_root_outside_the_workspace_is_still_skipped(tmp_path, monkeypatch) -> None:
    """The containment rule the fix must not weaken.

    A root that is not under the mounted workspace is SKIPPED rather than
    mounted somewhere invented -- widening the mount to reach it would hand the
    sandbox a path the workspace never contained.
    """
    base, roots = _scope_fixture(tmp_path, monkeypatch, ("training_ground",))
    outside = (tmp_path.parent / "outside_the_workspace").resolve()
    outside.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(executor_module, "get_scope_roots", lambda: (outside, roots[0]))

    sources = _mount_sources(_writable_scope_mounts(base))

    assert sources == [str(roots[0])], (
        f"an out-of-workspace root leaked into the writable set: {sources}"
    )


def test_the_resolver_does_not_use_ntpath_isabs() -> None:
    """A structural guard, because the behavioural one is platform-limited.

    Reverting the call sites to `ntpath.isabs` does NOT fail the tests above on
    Windows: there the two predicates agree, so the difference only shows on
    POSIX with Python 3.12 -- which is exactly why this shipped broken for two
    weeks and was invisible on the operator's machine.

    Verified by experiment while writing this file: restoring the old predicate
    left all ten cases green on Windows. So the revert is caught here, on any
    host, rather than waiting for a Linux runner to notice.
    """
    import inspect

    source = inspect.getsource(executor_module._writable_scope_mounts)
    assert "ntpath.isabs" not in source, (
        "_writable_scope_mounts is choosing its path flavour with ntpath.isabs "
        "again. That predicate returns True for POSIX absolute paths on Python "
        "3.12, which rewrites /home/... into backslashes and makes Docker refuse "
        "every container with 'bind source path does not exist'."
    )
    assert "_is_windows_style" in source, (
        "the resolver no longer consults _is_windows_style; a drive or UNC "
        "prefix is the only property that should select ntpath semantics"
    )
