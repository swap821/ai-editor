"""GAGOS's sandbox contains what runs in it -- proven in a real container.

Since 2026-11-03 a model-written proposal runs its tests BEFORE review (the
operator: "Yes honestly"), so the container is no longer a second line behind a
reviewer: it is the line. tests/test_gagos_sandbox.py asserts the argv; an argv
assertion cannot catch a Docker that ignores a flag. This file runs a probe
inside the real container, through the same runner and limits GAGOS uses
(:func:`aios.maintenance.sandbox_tests.default_runner`), and asserts what it
could and could not do:

- no network: neither a TCP connection nor a DNS lookup;
- nothing writable outside the container's own ``/tmp``: not the mounted copy,
  not the image's root;
- ``/tmp`` IS writable -- both directions, or "cannot write" would pass for a
  container that cannot run anything;
- a secret in the host's environment does not reach it, even when the
  ``docker`` client itself was given the whole environment;
- it is not root, and it sees only the copy it was given.

Gated like tests/test_container_containment_integration.py, on
``AIOS_EXECUTOR_INTEGRATION=1`` and a built image (``AIOS_CONTAINER_IMAGE``),
and run in the same CI step.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess

import pytest

from aios import config
from aios.maintenance import sandbox_tests as st

pytestmark = [
    pytest.mark.skipif(
        os.getenv("AIOS_EXECUTOR_INTEGRATION") != "1",
        reason="needs a real Docker daemon; set AIOS_EXECUTOR_INTEGRATION=1",
    ),
    pytest.mark.skipif(shutil.which("docker") is None, reason="docker CLI not on PATH"),
]

PROBE = """
import json, os, socket

out = {}
try:
    socket.create_connection(("1.1.1.1", 53), timeout=5)
    out["tcp"] = "open"
except OSError:
    out["tcp"] = "blocked"
try:
    socket.getaddrinfo("example.com", 443)
    out["dns"] = "resolved"
except OSError:
    out["dns"] = "blocked"
for target in ("/workspace/escape.txt", "/usr/escape.txt", "/etc/escape.txt", "/tmp/ok.txt"):
    try:
        with open(target, "w") as handle:
            handle.write("x")
        out[target] = "written"
    except OSError:
        out[target] = "refused"
out["secret"] = os.environ.get("GAGOS_PROBE_TOKEN")
out["uid"] = os.getuid()
out["workspace"] = sorted(os.listdir("/workspace"))
print(json.dumps(out))
"""


@pytest.fixture(scope="module")
def probe(tmp_path_factory) -> dict:
    image = config.CONTAINER_IMAGE
    if not st.image_built(image):
        pytest.skip(f"{image} is not built")
    tree = tmp_path_factory.mktemp("gagos-probe")
    (tree / "probe.py").write_text(PROBE, encoding="utf-8")
    os.environ["GAGOS_PROBE_TOKEN"] = "never-in-the-sandbox"
    try:
        # The whole host environment to the client: the worst case.
        out, err, code = st.default_runner(image)(
            "python probe.py", cwd=str(tree), env=dict(os.environ), timeout_s=180
        )
    finally:
        os.environ.pop("GAGOS_PROBE_TOKEN", None)
    assert code == 0, f"the probe did not run: exit {code}\n{out}\n{err}"
    result = json.loads(out.strip().splitlines()[-1])
    result["host_escape"] = (tree / "escape.txt").exists()
    return result


def test_the_sandbox_has_no_network(probe) -> None:
    assert probe["tcp"] == "blocked" and probe["dns"] == "blocked", probe


def test_the_sandbox_writes_only_its_own_tmp(probe) -> None:
    for target in ("/workspace/escape.txt", "/usr/escape.txt", "/etc/escape.txt"):
        assert probe[target] == "refused", (target, probe)
    assert not probe["host_escape"], "a file appeared in the host's copy"
    assert probe["/tmp/ok.txt"] == "written", "the sandbox must still be usable"


def test_no_host_secret_reaches_the_sandbox(probe) -> None:
    assert probe["secret"] is None, probe


def test_the_sandbox_is_not_root_and_sees_only_its_copy(probe) -> None:
    assert probe["uid"] != 0
    assert probe["workspace"] == ["probe.py"], probe


def test_a_killed_client_does_not_leave_the_tests_running() -> None:
    """``timeout -s KILL`` inside the container: the limit holds there."""
    if not st.image_built(config.CONTAINER_IMAGE):
        pytest.skip(f"{config.CONTAINER_IMAGE} is not built")
    found = subprocess.run(
        [
            shutil.which("docker") or "docker",
            "run",
            "--rm",
            "--network",
            "none",
            config.CONTAINER_IMAGE,
            "timeout",
            "-s",
            "KILL",
            "1",
            "sleep",
            "30",
        ],
        capture_output=True,
        timeout=120,
        check=False,
    )
    assert found.returncode == 137, found
