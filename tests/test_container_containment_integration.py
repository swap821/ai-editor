"""The sandbox cannot write the spine that judges it — proven in a real container.

Ultra-plan Phase 8 / inventory item 84: "the container isolation boundary that
GREEN/YELLOW verification depends on is asserted only against a mock".

That item's broader claim is now stale — CI *does* build both images
(`docker compose --profile build-only build worker`,
`docker compose up -d --build --wait executor`) and runs
`tests/test_executor_integration.py` inside a container with
`AIOS_EXECUTOR_INTEGRATION=1`. But its core concern was aimed correctly, at a gap
that is still real:

**The containment fix itself has never been executed.** `tests/test_executor.py`
proves the fix by building the docker argv and asserting the string contains
`readonly=true`. That is a good unit test of argv CONSTRUCTION and proves nothing
about whether Docker honours it. The behaviour was verified by hand on
2026-08-19 — a container was made to create files in `aios/security/` before the
fix and refused after — and then nothing pinned it.

An argv assertion cannot catch:

* a Docker version that parses `readonly=true` differently, or drops it;
* an overlapping-mount ordering change where the writable scope-root mounts
  shadow the read-only parent and re-open the whole tree;
* a future edit that keeps the string and breaks the effect.

So this file runs the real thing: a command inside the real container, writing
to a real path, asserting the real outcome.

Both directions are asserted, because either alone is a trap. "Cannot write the
spine" passes trivially if the container cannot write ANYTHING — which would
break every mission while looking like security.

Gated on `AIOS_EXECUTOR_INTEGRATION=1` like its sibling, so it runs in CI where
Docker and the image exist, and skips with a reason on a laptop that has neither.

## Probes use `touch`, not a shell redirect

The first version of this file wrote its probes as a shell redirect, and every
case failed in CI with `ValueError: shell composition is not permitted` -- raised
by `parse_argv`, long before Docker was involved. The executor rejects the
metacharacters `;&|<>` and launches with `shell=False` BY DESIGN, so a
redirect-based probe tests the argv boundary and never reaches the mount it means
to test.

Worth stating rather than quietly fixing: a containment probe that dies at argv
parsing proves nothing about containment, while looking exactly like a failing
security test. `touch` carries no metacharacters, so these probes reach the
mount itself.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from aios import config
from aios.core.executor import DockerRunner
from aios.security import scope_lock

pytestmark = [
    pytest.mark.skipif(
        os.getenv("AIOS_EXECUTOR_INTEGRATION") != "1",
        reason="needs a real Docker daemon; set AIOS_EXECUTOR_INTEGRATION=1",
    ),
    pytest.mark.skipif(shutil.which("docker") is None, reason="docker CLI not on PATH"),
]

#: Paths a sandboxed command must never be able to create or modify. Both were
#: writable before the 2026-08-19 fix, and both are self-referential: the first
#: is the security spine that adjudicates the command, the second the ledger
#: recording the system's own status.
_FORBIDDEN = (
    "aios/security/_containment_probe.txt",
    ".aios/state/_containment_probe.txt",
)


def _image_available() -> bool:
    result = subprocess.run(
        [config.CONTAINER_RUNTIME, "image", "inspect", config.CONTAINER_IMAGE],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


@pytest.fixture(scope="module")
def runner() -> DockerRunner:
    if not _image_available():
        pytest.skip(
            f"{config.CONTAINER_IMAGE} is not built; CI builds it with "
            "`docker compose --profile build-only build worker`"
        )
    return DockerRunner()


def _run(runner: DockerRunner, command: str) -> tuple[str, str, int]:
    """Execute *command* through the real container backend."""
    return runner(
        command,
        cwd=str(scope_lock.command_cwd()),
        env={},
        timeout_s=120,
    )


@pytest.mark.parametrize("target", _FORBIDDEN)
def test_the_sandbox_cannot_write_the_tree_that_judges_it(
    runner: DockerRunner, target: str
) -> None:
    """The escape that was live on 2026-08-19, executed rather than described.

    `command_cwd()` returns the scope root's PARENT (the repo root) so
    `training_ground` imports as a package. A bind mount is read-write by
    DEFAULT, so that one omission made the entire repository writable by a
    sandboxed command — including `aios/security/`, the frozen spine, and
    `.aios/state/`, the ledger recording its own status.
    """
    host_path = Path(scope_lock.command_cwd()) / target
    assert not host_path.exists(), (
        f"{target} exists before the probe; a previous run leaked. Remove it "
        "before trusting this result."
    )

    stdout, stderr, exit_code = _run(runner, f"touch /workspace/{target}")

    assert not host_path.exists(), (
        f"CONTAINMENT ESCAPE: a sandboxed command created {target} on the host. "
        f"exit={exit_code} stdout={stdout[:200]!r} stderr={stderr[:200]!r}"
    )
    assert exit_code != 0, (
        f"the write to {target} reported success (exit 0) even though no file "
        "appeared; the container may be writing to a layer that is silently "
        f"discarded. stdout={stdout[:200]!r} stderr={stderr[:200]!r}"
    )


def test_the_sandbox_can_still_write_its_own_scope_root(runner: DockerRunner) -> None:
    """The other half, without which the test above passes for the wrong reason.

    A read-only workspace with nothing handed back would refuse the forbidden
    writes AND break every mission — missions create files in
    `training_ground/`. Read-only-everything is not the fix; read-only-parent
    plus writable-scope-roots is.

    The write must SUCCEED. EACCES was tolerated while item 84b was open (the
    container ran as nobody while the host directory belonged to the checkout
    user); now that the sandbox runs as the invoking uid, a permission failure
    here is a regression.

    A MISSING mount is checked separately and first, because that is what made
    the forbidden-write cases above pass vacuously on 2026-09-01: the container
    died at mount config, so "no file appeared" and "exit != 0" were both
    trivially true.
    """
    roots = scope_lock.get_scope_roots()
    if not roots:
        pytest.skip("no scope roots declared")
    root = roots[0]
    probe = root / "_containment_probe.txt"
    if probe.exists():
        probe.unlink()

    try:
        stdout, stderr, exit_code = _run(
            runner, f"touch /workspace/{root.name}/_containment_probe.txt"
        )

        # The mount must EXIST. This is the half that regressed on 2026-09-01:
        # `_writable_scope_mounts` emitted Windows separators on Linux, Docker
        # refused the container with exit 125, and the forbidden-write cases
        # above then "passed" because nothing ran at all.
        combined = f"{stdout}{stderr}".lower()
        assert "bind source path does not exist" not in combined, (
            f"the writable mount for {root.name}/ was not created at all -- the "
            "container never started, so every containment assertion in this "
            f"file is vacuous. stderr={stderr[:300]!r}"
        )
        assert exit_code != 125, (
            f"docker refused the container (exit 125): {stderr[:300]!r}"
        )

        # EACCES was tolerated here while item 84b was open: the container ran
        # `--user 65534:65534` while the host scope root belonged to the checkout
        # user, so on Linux this write could not succeed. That is fixed -- the
        # sandbox now runs as the invoking uid -- so the contract is a successful
        # write again, and a permission failure is a REGRESSION, not a known
        # limitation.
        assert exit_code == 0, (
            f"the sandbox could not write its OWN scope root {root.name}/. A "
            "read-only workspace with no writable roots handed back breaks every "
            "mission. If this says 'Permission denied', item 84b has regressed "
            "and the container uid no longer matches the host directory owner. "
            f"stdout={stdout[:300]!r} stderr={stderr[:300]!r}"
        )
        assert probe.exists(), (
            f"the write to {root.name}/ reported success but no file appeared on "
            "the host; the scope root is not actually bind-mounted read-write"
        )
        return

    finally:
        if probe.exists():
            probe.unlink()


def test_the_writable_set_matches_the_declared_scope_roots(
    runner: DockerRunner,
) -> None:
    """Writable-ness is derived from the live authority, not a second list.

    Two derivations of "what is in scope" disagreeing is the containment-escape
    shape this repo has been bitten by more than once. This asserts the RUNTIME
    consequence: a directory that is not a declared scope root, sitting inside
    the workspace, must not be writable.
    """
    workspace = Path(scope_lock.command_cwd())
    declared = {root.name for root in scope_lock.get_scope_roots()}
    candidates = [
        entry
        for entry in workspace.iterdir()
        if entry.is_dir()
        and entry.name not in declared
        and not entry.name.startswith(".git")
    ]
    if not candidates:
        pytest.skip("no non-scope directory in the workspace to probe")

    victim = candidates[0]
    probe = victim / "_containment_probe.txt"
    assert not probe.exists(), f"{probe} leaked from a previous run"

    stdout, stderr, exit_code = _run(
        runner, f"touch /workspace/{victim.name}/_containment_probe.txt"
    )

    assert not probe.exists(), (
        f"CONTAINMENT ESCAPE: {victim.name}/ is not a declared scope root but a "
        f"sandboxed command wrote into it. exit={exit_code} "
        f"stderr={stderr[:200]!r}"
    )


# --------------------------------------------------------------------------- #
# The controls that were only ever argv strings
# --------------------------------------------------------------------------- #
#
# Write containment above is executed. `--network none`, `--read-only` and the
# `/tmp` tmpfs were not: they were asserted by building the docker argv and
# checking the flag is present, which proves construction and nothing about
# whether Docker honoured it. That is the same declared-versus-actual gap M12
# exists to close, pointed at the sandbox instead of the gateway -- and the gap
# is not hypothetical here, because this repo has already shipped one control
# that was present in the argv and ineffective in the container (a bind mount
# that was read-write by default, live until 2026-08-19).
#
# Each probe asserts BOTH directions for the same reason the write probes do:
# "the network is unreachable" passes trivially in a container that cannot run
# anything at all.


def test_the_sandbox_has_no_network(runner: DockerRunner) -> None:
    """`--network none`, executed rather than described.

    A sandbox that can open a socket can exfiltrate whatever it can read, and
    M12 hands this container commands a model invented seconds earlier.

    Paired with a control that proves the interpreter runs, so a probe that
    fails because `python` is missing can never be mistaken for containment.
    """
    ok_out, ok_err, ok_code = _run(runner, 'python -c "print(1)"')
    assert ok_code == 0, (
        "the control probe could not run python, so a failing network probe "
        f"would prove nothing. stdout={ok_out[:200]!r} stderr={ok_err[:200]!r}"
    )
    assert "1" in ok_out

    # No semicolons: `parse_argv` rejects them as shell composition, so the
    # import is inlined rather than written as two statements.
    stdout, stderr, exit_code = _run(
        runner,
        "python -c \"__import__('socket').create_connection(('1.1.1.1',53),timeout=5)\"",
    )

    assert exit_code != 0, (
        "CONTAINMENT ESCAPE: a sandboxed command opened an outbound connection. "
        f"--network none is not in effect. stdout={stdout[:200]!r}"
    )
    assert "Error" in stderr or "error" in stderr, (
        "the network probe failed without a Python exception, so the cause is "
        f"unknown and may not be the network. stderr={stderr[:300]!r}"
    )


def test_the_sandbox_root_filesystem_is_read_only(runner: DockerRunner) -> None:
    """`--read-only`, executed rather than described.

    A writable rootfs lets a command drop a binary or edit interpreter config
    and have it survive to the next process in the same container.
    """
    stdout, stderr, exit_code = _run(runner, "touch /etc/_containment_probe")

    assert exit_code != 0, (
        "CONTAINMENT ESCAPE: a sandboxed command wrote to /etc. --read-only is "
        f"not in effect. stdout={stdout[:200]!r} stderr={stderr[:200]!r}"
    )


def test_the_sandbox_can_still_write_its_tmpfs(runner: DockerRunner) -> None:
    """The other half of the read-only probe.

    `HOME=/tmp` is set precisely because an arbitrary uid has no passwd entry,
    so pytest and pip need a writable home. If this stops working, the rootfs
    probe above starts passing for the wrong reason and every verification run
    breaks at the same time.
    """
    stdout, stderr, exit_code = _run(runner, "touch /tmp/_containment_probe")

    assert exit_code == 0, (
        "the sandbox cannot write its own tmpfs, so HOME=/tmp is broken and "
        f"the read-only probe above proves nothing. stderr={stderr[:300]!r}"
    )


def test_the_sandbox_cannot_fill_the_host_disk(runner: DockerRunner) -> None:
    """RLIMIT_FSIZE, executed rather than described.

    The only unbounded resource the sandbox had. `--memory`, `--cpus` and
    `--pids-limit` cap what a command consumes inside the container; none of
    them cap what it WRITES, and the scope roots are bind-mounted read-write
    from the host. Taking the machine down that way needs no containment escape
    at all -- it is a supported operation performed to excess.

    Writes into the tmpfs rather than a scope root, so a failure of this test
    cannot itself leave a large file on the operator's disk.
    """
    # 512 MiB limit, so 1 GiB must be refused. `seek` makes this a sparse write
    # that costs nothing until the limit is hit, and carries no semicolon --
    # `parse_argv` rejects those as shell composition.
    stdout, stderr, exit_code = _run(
        runner,
        "python -c \"open('/tmp/_fsize_probe','wb').truncate(1024*1024*1024)\"",
    )

    assert exit_code != 0, (
        "a sandboxed command created a 1 GiB file; RLIMIT_FSIZE is not in "
        f"effect and the writable scope roots are the host's disk. "
        f"stdout={stdout[:200]!r} stderr={stderr[:200]!r}"
    )


def test_the_fsize_cap_still_allows_a_normal_artefact(runner: DockerRunner) -> None:
    """The other half. A cap that refuses ordinary output is an outage.

    One mebibyte is larger than any log a verification run produces and three
    orders of magnitude below the cap, so this failing means the limit is set
    to something unusable rather than something protective.
    """
    stdout, stderr, exit_code = _run(
        runner,
        "python -c \"open('/tmp/_fsize_ok','wb').write(b'x'*1048576)\"",
    )

    assert exit_code == 0, (
        "the sandbox could not write 1 MiB, so RLIMIT_FSIZE is set too low and "
        f"real verification runs will fail. stderr={stderr[:300]!r}"
    )


# --------------------------------------------------------------------------- #
# Kernel-enforced controls, read from the container's own /proc
# --------------------------------------------------------------------------- #
#
# `--cap-drop ALL`, `no-new-privileges` and seccomp were the last three controls
# asserted only by their presence in the docker argv. The kernel publishes all
# three in /proc/self/status, so the container can be asked what it actually got
# rather than what it was asked for.
#
# This closes the argv-only set. `--userns` is deliberately NOT here: user
# namespace remapping is a DAEMON setting (`userns-remap` in daemon.json,
# surfacing as `name=userns` in `docker info --format '{{.SecurityOptions}}'`),
# and Docker's per-container `--userns` flag only accepts `host`, which DISABLES
# remapping. The runner cannot turn it on, so no probe here can honestly claim
# it. Enabling it is an operator change to the daemon.


def _proc_status(runner: DockerRunner) -> dict[str, str]:
    """`/proc/self/status` from inside the sandbox, as a mapping."""
    stdout, stderr, exit_code = _run(
        runner, "python -c \"print(open('/proc/self/status').read())\""
    )
    assert exit_code == 0, f"could not read /proc/self/status: {stderr[:300]!r}"
    fields: dict[str, str] = {}
    for line in stdout.splitlines():
        key, _, value = line.partition(":")
        if value:
            fields[key.strip()] = value.strip()
    return fields


def test_the_sandbox_holds_no_capabilities(runner: DockerRunner) -> None:
    """`--cap-drop ALL`, read back from the kernel.

    The BOUNDING set is checked too, not just the effective one. A non-empty
    bounding set means a setuid binary could still regain a capability the
    effective set dropped, which is the escape `--cap-drop ALL` is meant to
    foreclose rather than merely defer.
    """
    status = _proc_status(runner)

    assert status.get("CapEff") == "0000000000000000", (
        f"the sandbox holds effective capabilities: {status.get('CapEff')!r}"
    )
    assert status.get("CapBnd") == "0000000000000000", (
        "the capability BOUNDING set is non-empty, so a capability can still be "
        f"regained: {status.get('CapBnd')!r}"
    )


def test_the_sandbox_cannot_gain_privileges(runner: DockerRunner) -> None:
    """`--security-opt no-new-privileges`, read back from the kernel."""
    status = _proc_status(runner)

    assert status.get("NoNewPrivs") == "1", (
        "no-new-privileges is not in effect, so a setuid binary inside the "
        f"image could escalate: NoNewPrivs={status.get('NoNewPrivs')!r}"
    )


def test_the_sandbox_runs_under_a_seccomp_filter(runner: DockerRunner) -> None:
    """Seccomp mode 2 is SECCOMP_MODE_FILTER; 0 means no filter at all.

    Docker applies its builtin profile unless someone passes
    `seccomp=unconfined`. Nothing here passes that today -- this is what would
    notice if something started to.
    """
    status = _proc_status(runner)

    assert status.get("Seccomp") == "2", (
        "the sandbox is not running under a seccomp filter (mode 2 = "
        f"SECCOMP_MODE_FILTER): Seccomp={status.get('Seccomp')!r}"
    )


def test_the_sandbox_does_not_run_as_root(runner: DockerRunner) -> None:
    """The `--user` flag, read back rather than assumed.

    Paired with the capability probe: uid 0 with no capabilities is far less
    dangerous than uid 0 with them, but the mounted scope roots are host-visible
    and owned by the invoking user, so the uid still matters on its own.
    """
    status = _proc_status(runner)
    uids = (status.get("Uid") or "").split()

    assert uids and uids[0] != "0", f"the sandbox is running as root: Uid={uids!r}"
