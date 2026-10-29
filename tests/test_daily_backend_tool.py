"""``tools/daily_backend.py``: the operator's daily backend, started one way.

Pinned here: the settings it launches with are the ones he chose, and an
``AIOS_ROUTER_CLOUD_TASKS`` inherited from his user-wide environment never
decides where a turn goes (2026-10-29: his ``reasoning,coding`` sent the daily
backend's coding turns to Bedrock first). Whether a reflex would serve is
``Cerebellum.readiness``, pinned in ``tests/test_reflex_readiness.py``.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tools import daily_backend

REPO = Path(daily_backend.__file__).resolve().parents[1]


def test_the_settings_are_the_ones_the_operator_chose() -> None:
    settings = daily_backend.daily_settings()
    roots = settings["AIOS_SCOPE_ROOTS"].split(os.pathsep)
    # training_ground FIRST: commands run from the parent of the first root.
    assert roots == [str(REPO / n) for n in ("training_ground", "lab", "work")]
    assert settings["AIOS_TASK_SCOPE"] == os.path.join("work", "ai-editor")
    assert settings["AIOS_EXECUTOR_TIMEOUT_S"] == "120"
    assert settings["AIOS_REPLAY_APPROVED_COMMANDS"] == "1"
    assert settings["AIOS_ROUTER_CLOUD_TASKS"] == ""


def test_the_sandbox_image_names_the_requirements_it_holds() -> None:
    """Dockerfile.verify's convention: the tag is the first 12 of the sha256 of
    requirements.txt, so a requirements change names an image not yet built."""
    digest = hashlib.sha256((REPO / "requirements.txt").read_bytes()).hexdigest()
    assert daily_backend.verify_image() == f"aios-verify:{digest[:12]}"
    assert (
        daily_backend.daily_settings()["AIOS_CONTAINER_IMAGE"]
        == daily_backend.verify_image()
    )


def test_no_secret_is_a_setting() -> None:
    settings = daily_backend.daily_settings()
    assert not set(settings) & set(daily_backend.KEYS)


def _cloud_tasks_seen(env: dict[str, str]) -> list[str]:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import json; from aios.security import limits; "
            "print(json.dumps(list(limits.ROUTER_CLOUD_TASKS)))",
        ],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=True,
    )
    return json.loads(result.stdout.strip().splitlines()[-1])


@pytest.mark.parametrize(
    ("chosen", "expected"),
    [("", []), ("reasoning", ["reasoning"])],
)
def test_an_inherited_cloud_opt_in_never_decides(chosen: str, expected: list) -> None:
    """The operator's user-wide value reaches every process he starts. The
    daily backend always sets its own, so only the launch choice counts."""
    inherited = {**os.environ, "AIOS_ROUTER_CLOUD_TASKS": "reasoning,coding"}
    assert _cloud_tasks_seen(inherited) == ["reasoning", "coding"]
    env = {**inherited, **daily_backend.daily_settings(cloud_tasks=chosen)}
    assert _cloud_tasks_seen(env) == expected


def test_down_stops_nothing_it_did_not_start(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(daily_backend, "STATE", tmp_path / "daily.json")
    assert daily_backend.main(["down"]) == 1
    assert "stopping nothing" in capsys.readouterr().out
