"""The sandbox runs as the invoking uid, never as root, never as a stranger.

Inventory item 84b. The container was hardcoded to `--user 65534:65534`
(nobody) while the host scope roots belong to whoever checked the repository
out, so **on Linux the sandbox could not write its own scope root** and no
file-creating mission could succeed::

    touch: cannot touch '/workspace/training_ground/x': Permission denied

Docker Desktop on Windows translates bind-mount ownership itself, which is why
this was invisible on the operator's machine until the containment suite ran
against a real daemon on CI.

## Why changing the uid does not weaken containment

The reachable set is defined by the MOUNTS, not the uid: the workspace bind is
`readonly=true`, only declared scope roots are remounted writable, and Docker
enforces those permissions independently of who the process is. The container
also has `--network none`, `--read-only`, `--cap-drop ALL`,
`--security-opt no-new-privileges` and resource caps.

The trade-off that IS real: a container escape now holds the invoking user's
privileges rather than nobody's -- bounded by the flags above, and by the fact
that the parent backend process already runs as that user.

## Why these tests are platform-agnostic

Both previous Linux-only defects in this file (`ntpath.isabs` separator
corruption, and this one) were invisible on Windows and shipped as a result. So
the fallback and root-refusal branches are exercised by monkeypatching `os`
rather than by being on the platform that happens to reach them.
"""

from __future__ import annotations

import os

import pytest

from aios.core import executor as executor_module
from aios.core.executor import _UNPRIVILEGED_FALLBACK_USER, _container_user


def test_a_posix_host_runs_the_sandbox_as_the_invoking_user(monkeypatch) -> None:
    """The fix: the uid must match whoever owns the bind-mounted scope roots."""
    monkeypatch.setattr(os, "getuid", lambda: 1001, raising=False)
    monkeypatch.setattr(os, "getgid", lambda: 2002, raising=False)

    assert _container_user() == "1001:2002"


def test_a_host_without_posix_uids_falls_back(monkeypatch) -> None:
    """Windows has no `os.getuid`.

    Docker Desktop maps bind-mount ownership itself there, so the historical
    unprivileged id stays correct -- and `nobody` exists in the worker image, so
    `getpwuid` resolves.
    """
    monkeypatch.delattr(os, "getuid", raising=False)
    monkeypatch.delattr(os, "getgid", raising=False)

    assert _container_user() == _UNPRIVILEGED_FALLBACK_USER == "65534:65534"


def test_the_sandbox_is_never_root_even_when_the_backend_is(monkeypatch) -> None:
    """A fail-safe the old hardcode did not have.

    Deriving the uid from the caller means a backend running as root would
    otherwise hand root to the disposable container -- strictly worse than the
    behaviour being replaced. Refuse and fall back instead.
    """
    monkeypatch.setattr(os, "getuid", lambda: 0, raising=False)
    monkeypatch.setattr(os, "getgid", lambda: 0, raising=False)

    assert _container_user() == "65534:65534"


def test_a_root_group_alone_is_not_refused(monkeypatch) -> None:
    """Only uid 0 is the danger; gid 0 is common and harmless on macOS.

    macOS user accounts default to gid 20 (`staff`), but gid 0 (`wheel`) appears
    in enough setups that refusing it would break the fix for no security gain --
    group membership grants nothing here, since the container has `--cap-drop
    ALL` and the mounts are what bound it.
    """
    monkeypatch.setattr(os, "getuid", lambda: 501, raising=False)
    monkeypatch.setattr(os, "getgid", lambda: 0, raising=False)

    assert _container_user() == "501:0"


# --------------------------------------------------------------------------- #
# The argv actually carries it
# --------------------------------------------------------------------------- #
def _docker_argv(monkeypatch, tmp_path) -> list[str]:
    """Capture the argv DockerRunner would launch, without a daemon."""
    captured: dict[str, list[str]] = {}

    def fake_run(argv, **kwargs):
        captured["argv"] = argv

        class _Completed:
            stdout = ""
            stderr = ""
            returncode = 0

        return _Completed()

    runner = executor_module.DockerRunner(process_runner=fake_run)
    monkeypatch.setattr(executor_module, "get_scope_roots", lambda: ())
    runner("echo hi", cwd=str(tmp_path.resolve()), env={}, timeout_s=5)
    return captured["argv"]


def test_the_argv_uses_the_derived_user(monkeypatch, tmp_path) -> None:
    """A helper nothing calls is a helper that fixes nothing."""
    argv = _docker_argv(monkeypatch, tmp_path)

    assert "--user" in argv, argv
    assert argv[argv.index("--user") + 1] == _container_user(), (
        "the container is not launched as the derived user"
    )
    assert "65534:65534" not in argv or _container_user() == "65534:65534", (
        "the uid is still hardcoded rather than derived"
    )


def test_the_argv_sets_a_container_local_home(monkeypatch, tmp_path) -> None:
    """An arbitrary uid has no passwd entry.

    `getpwuid` then raises and `os.path.expanduser` fails, which breaks pytest
    and pip in ways that look like product bugs. HOME is stripped from the child
    environment by design, so the container needs its own.
    """
    argv = _docker_argv(monkeypatch, tmp_path)

    assert "HOME=/tmp" in argv, (
        "no container-local HOME; a non-65534 uid has no /etc/passwd entry and "
        "home-directory resolution will fail inside the sandbox"
    )


def test_the_hardening_flags_are_untouched(monkeypatch, tmp_path) -> None:
    """The uid change must not have quietly relaxed anything else.

    These flags -- not the uid -- are what bound the sandbox, which is the whole
    argument for the change being safe. If any of them regressed, that argument
    collapses.
    """
    argv = _docker_argv(monkeypatch, tmp_path)

    for flag, value in (
        ("--network", "none"),
        ("--cap-drop", "ALL"),
        ("--security-opt", "no-new-privileges"),
    ):
        assert flag in argv, f"{flag} disappeared from the container argv"
        assert argv[argv.index(flag) + 1] == value, f"{flag} changed value"
    assert "--read-only" in argv

    workspace = next(
        (a for a in argv if a.startswith("type=bind") and "dst=/workspace," in a), None
    )
    assert workspace is not None, f"no workspace mount in argv: {argv}"
    assert "readonly=true" in workspace, (
        "the workspace bind is no longer read-only -- that, not the uid, is what "
        "stops the sandbox writing the spine that judges it"
    )
