"""A GAGOS mission runs through the council's own execution (2026-11-13).

Move A3 on the aliveness map. The mission GAGOS originated inside the
operator's envelope is approved by its slot, its folder holds its files at the
base commit, the Foundry stages that folder, GAGOS's writer writes into the
stage and nowhere else, the sandbox's verdict is the run ledger's verification,
the reviewer judges the change, and promotion writes it back to GAGOS's own
folder only when the worker completed with STRONG tests.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from aios import config
from aios.api.routes import council as council_route
from aios.domain.missions.mission_state import MissionState
from aios.infrastructure.missions.sqlite_mission_repository import (
    SqliteMissionRepository,
)
from aios.maintenance import sandbox_tests as sb
from aios.operations import council_origination as co
from aios.runtime import gagos_writer as gw
from aios.runtime.contracts import MissionContract
from tests.test_gagos_council_origination import TEST, _briefed, _envelope, _task

BASE = "it('starts', () => {});\n"
NEW = "it('starts', () => {});\nit('stays bounded', () => {});\n"

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="needs git")


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture()
def repo(tmp_path) -> tuple[Path, str]:
    root = tmp_path / "repo"
    (root / Path(TEST).parent).mkdir(parents=True)
    (root / TEST).write_text(BASE, encoding="utf-8", newline="")
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(
        root,
        "-c",
        "user.name=t",
        "-c",
        "user.email=t@t",
        "commit",
        "-qm",
        "base",
    )
    return root, _git(root, "rev-parse", "HEAD")


@pytest.fixture()
def world(tmp_path, monkeypatch, repo):
    """A real deliberation of a GAGOS goal, its workspaces under tmp."""
    import aios.council.gateway_reasoning as reasoning

    monkeypatch.setattr(reasoning, "build_council_llm_client", lambda **kw: None)
    monkeypatch.setattr(reasoning, "build_dissent_llm_client", lambda **kw: None)
    workspace_root = tmp_path / "council_workspace"
    workspace_root.mkdir()
    monkeypatch.setattr(config, "COUNCIL_WORKSPACE_ROOT", workspace_root)
    monkeypatch.setattr(config, "EXECUTOR_WORKSPACE_ROOT", tmp_path / "stages")
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    envelope = _envelope(tmp_path)
    out = co.originate_goal(
        _task(),
        _briefed(),
        envelope=envelope,
        workspace_root=co.gagos_workspace(workspace_root),
        runtime_root=runtime,
        detect_injection=lambda text: None,
    )
    assert out["state"] == "awaiting_approval", out
    return envelope, runtime, out["mission_id"], repo


def _passed() -> sb.SandboxVerdict:
    return sb.SandboxVerdict(
        sb.PASSED, "2 tests in 1 files pass", tests=(TEST,), passed_count=2
    )


def _run(world, *, write=None, verify=None, review=None):
    envelope, runtime, mission_id, (root, base) = world
    seen: dict = {}

    def writer(contract):
        seen["root"] = contract.workspace_root
        seen["base"] = (Path(contract.workspace_root) / TEST).read_text(
            encoding="utf-8"
        )
        return {TEST: NEW}

    out = co.run_gagos_mission(
        mission_id,
        envelope=envelope,
        runtime_root=runtime,
        repo_root=root,
        base_commit=base,
        write=write or writer,
        verify=verify or (lambda edits: _passed()),
        review=review or (lambda edits, verdict: (True, "it does what he asked")),
    )
    record = SqliteMissionRepository(runtime / council_route.MISSIONS_DB_NAME).get(
        mission_id
    )
    return out, record, seen


def test_a_mission_runs_in_its_stage_and_is_promoted_to_gagoss_folder(world) -> None:
    out, record, seen = _run(world)
    assert out["state"] == "completed", out
    assert out["files"] == {TEST: NEW}
    assert record.state is MissionState.COMPLETED
    folder = Path(record.contract.workspace_root)
    assert (folder / TEST).read_text(encoding="utf-8") == NEW
    # The writer wrote into a stage of the folder, never the folder itself,
    # and read the file as it was at the base commit.
    assert Path(seen["root"]).resolve() != folder.resolve()
    assert seen["base"] == BASE


def test_the_approval_is_the_envelopes_slot(world) -> None:
    import sqlite3

    envelope, runtime, mission_id, _ = world
    _run(world)
    with sqlite3.connect(runtime / council_route.MISSIONS_DB_NAME) as conn:
        actor, capability = conn.execute(
            "SELECT actor, capability_digest FROM mission_transitions "
            "WHERE mission_id = ? AND to_state = ?",
            (mission_id, MissionState.APPROVED.value),
        ).fetchone()
    slot = envelope.held_slot(mission_id)
    assert actor == f"envelope:{slot.envelope_id}"
    assert capability == slot.slot_digest


def test_a_rejected_review_fails_the_mission_and_promotes_nothing(world) -> None:
    out, record, _ = _run(
        world, review=lambda edits, verdict: (False, "it tests the wrong thing")
    )
    assert out["state"] == "failed"
    assert "the reviewer rejects: it tests the wrong thing" in out["reason"]
    assert record.state is MissionState.FAILED
    folder = Path(record.contract.workspace_root)
    assert (folder / TEST).read_text(encoding="utf-8") == BASE


@pytest.mark.parametrize(
    "outcome", [sb.BROKE, sb.UNTESTED, sb.UNAVAILABLE], ids=lambda o: o
)
def test_tests_that_do_not_pass_fail_the_mission_unreviewed(world, outcome) -> None:
    reviewed = []
    out, record, _ = _run(
        world,
        verify=lambda edits: sb.SandboxVerdict(outcome, "why", passed_count=0),
        review=lambda edits, verdict: reviewed.append(1) or (True, "yes"),
    )
    assert out["state"] == "failed" and f"the sandbox: {outcome}" in out["reason"]
    assert record.state is MissionState.FAILED and reviewed == []


def test_a_writer_that_reaches_outside_its_files_fails(world) -> None:
    out, record, _ = _run(world, write=lambda c: {"frontend/src/other.ts": "x"})
    assert out["state"] == "failed"
    assert "not one of the mission's files" in out["reason"]
    assert record.state is MissionState.FAILED


def test_a_revoked_envelope_runs_nothing(world) -> None:
    from tests.test_gagos_envelope import Who

    envelope, runtime, mission_id, _ = world
    envelope.revoke(principal=Who())
    out, record, seen = _run(world)
    assert out["state"] == "refused" and "revoked" in out["reason"]
    assert record.state is MissionState.AWAITING_APPROVAL and seen == {}
    assert not any(Path(record.contract.workspace_root).iterdir())


def test_a_mission_runs_once(world) -> None:
    _run(world)
    out, _, _ = _run(world)
    assert out["state"] == "refused" and "completed" in out["reason"]


# -- writing into the stage ---------------------------------------------------------


def _contract(stage: Path, files=(TEST,)) -> MissionContract:
    return MissionContract(
        mission_id="mission-0123456789ab",
        goal="g",
        worker_type="hybrid_plan_worker",
        created_by="gagos",
        workspace_root=str(stage),
        allowed_files=list(files),
    )


@pytest.mark.parametrize(
    "rel,why",
    [
        ("frontend/src/other.ts", "not one of the mission's files"),
        ("../outside.ts", "may not climb"),
        ("/x.ts", "absolute"),
        ("aios/security/gateway.py", "never GAGOS's to write"),
        (TEST + ":hidden", "not a plain"),
    ],
)
def test_only_the_missions_own_plain_paths_are_written(tmp_path, rel, why) -> None:
    with pytest.raises(gw.WriterRefused, match=why):
        gw.write_into_stage(
            tmp_path,
            _contract(tmp_path, files=(TEST, "aios/security/gateway.py")),
            {TEST: NEW, rel: "x"},
        )
    assert not (tmp_path / TEST).exists()  # all or nothing


def test_a_differently_cased_path_is_written_under_the_missions_spelling(
    tmp_path,
) -> None:
    written = gw.write_into_stage(tmp_path, _contract(tmp_path), {TEST.upper(): NEW})
    assert written == {TEST: NEW}


def _link(link: Path, target: Path) -> None:
    if sys.platform == "win32":
        import _winapi

        _winapi.CreateJunction(str(target), str(link))
    else:
        os.symlink(target, link, target_is_directory=True)


def test_a_link_on_the_way_down_the_stage_is_refused(tmp_path) -> None:
    stage, outside = tmp_path / "stage", tmp_path / "outside"
    (stage / "frontend").mkdir(parents=True)
    outside.mkdir()
    _link(stage / "frontend" / "src", outside)
    with pytest.raises(gw.WriterRefused, match="is a link"):
        gw.write_into_stage(stage, _contract(stage), {TEST: NEW})
    assert not any(outside.rglob("*"))


def test_the_backend_writes_only_into_a_stage_of_its_mission(tmp_path) -> None:
    import asyncio

    backend = gw.GagosWriterBackend(
        write=lambda c: {TEST: NEW}, verify=lambda e: _passed()
    )
    contract = _contract(tmp_path)  # no staged workspace in its metadata

    async def go():
        return await backend.reap(await backend.spawn(contract))

    result = asyncio.run(go())
    assert result.status == "failed" and "no stage" in result.summary
    assert not (tmp_path / TEST).exists()
