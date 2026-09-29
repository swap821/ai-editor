"""tools/activate_skills.py: the operator's activation tool refuses everything else.

The route itself is pinned end to end in tests/test_phase2_skill_activation_route.py;
this pins the tool: read-only listing with a risk label, the operator's own
declaration, a credential only from the operator (never enrollment), the exact
route, stopping at the first refusal, and a credential that never reaches output.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from aios.domain.learning.repository import SkillRecord, SkillRepository
from tools import activate_skills as tool

SECRET = "op-credential-that-must-never-print"


def _record(legacy_id: int, steps: list[str], *, ready: bool) -> SkillRecord:
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    return SkillRecord(
        skill_id=f"arc-{legacy_id}",
        version=1,
        problem_signature=f"goal {legacy_id}",
        applicability_conditions={},
        known_exclusions=[],
        required_inputs=[],
        required_project_state={},
        procedure=json.dumps(steps),
        allowed_tools=sorted({s.split(":", 1)[0] for s in steps}),
        allowed_scope_pattern="",
        expected_observations=[],
        verification_plan=None,
        escalation_conditions=[],
        source_trajectory_ids=[],
        confidence=0.8,
        success_count=4,
        failure_count=0,
        last_validated_versions=[],
        state="candidate",
        created_at=now,
        updated_at=now,
        provenance={
            "source": "migrated",
            "legacy_id": str(legacy_id),
            "review_ready": "true" if ready else "false",
        },
    )


class FakeSession:
    instances: list["FakeSession"] = []

    def __init__(self, base: str) -> None:
        self.base = base
        self.posts: list[str] = []
        self.bootstrapped = False
        FakeSession.instances.append(self)

    def bootstrap(self, display_name: str = "") -> "FakeSession":
        self.bootstrapped = True
        return self

    def post_stream(self, path: str, payload: dict, timeout: int):
        self.posts.append(path)
        status = 403 if "arc-2/" in path else 200

        class R:
            status_code = status
            text = ""

            def json(self_inner):
                return {"state": "active"} if status == 200 else {"detail": "denied"}

        return R()


@pytest.fixture()
def world(tmp_path: Path, monkeypatch):
    db = tmp_path / "operational.db"
    repository = SkillRepository(db)
    repository.save(_record(1, ["verify: command=pytest t.py -q"], ready=True))
    repository.save(_record(2, ["verify: command=pytest u.py -q"], ready=True))
    repository.save(
        _record(3, ["create_file: filepath=x.py", "verify: command=pytest"], ready=True)
    )
    repository.save(_record(4, ["read_file: filepath=a.py"], ready=False))
    monkeypatch.setattr(tool.config, "OPERATIONAL_STATE_DB_PATH", db)
    monkeypatch.delenv("AIOS_OPERATOR_CREDENTIAL", raising=False)
    FakeSession.instances.clear()
    import aios.probe_session as probe

    monkeypatch.setattr(probe, "ProbeSession", FakeSession)
    return repository


def test_the_listing_is_read_only_and_labels_risk(world, capsys) -> None:
    before = [r.model_dump() for r in world.list_skills()]
    assert tool.main([]) == 0
    listing = json.loads(capsys.readouterr().out)
    risk = {row["legacy_id"]: row["risk"] for row in listing["review_ready"]}
    assert risk == {1: "read-only", 2: "read-only", 3: "WRITES"}
    assert listing["other_candidates"] == 1
    assert [r.model_dump() for r in world.list_skills()] == before
    assert not FakeSession.instances, "listing must not open a session"


def test_activation_needs_the_operators_declaration(world) -> None:
    with pytest.raises(SystemExit, match="operator"):
        tool.main(["--activate", "1"])
    assert not FakeSession.instances


def test_without_a_credential_it_stops_and_never_enrolls(world) -> None:
    with pytest.raises(SystemExit, match="never enrolls"):
        tool.main(["--activate", "1", "--i-am-the-operator", "Operator"])
    assert not FakeSession.instances, "no session, so no enrollment attempt"


def test_an_unknown_or_non_candidate_id_is_refused(world, monkeypatch) -> None:
    monkeypatch.setenv("AIOS_OPERATOR_CREDENTIAL", SECRET)
    with pytest.raises(SystemExit, match="not an activatable candidate"):
        tool.main(["--activate", "99", "--i-am-the-operator", "Operator"])


def test_not_review_ready_needs_an_explicit_flag(world, monkeypatch) -> None:
    monkeypatch.setenv("AIOS_OPERATOR_CREDENTIAL", SECRET)
    with pytest.raises(SystemExit, match="not review-ready"):
        tool.main(["--activate", "4", "--i-am-the-operator", "Operator"])


def test_it_drives_the_route_and_stops_at_the_first_refusal(
    world, monkeypatch, capsys
) -> None:
    monkeypatch.setenv("AIOS_OPERATOR_CREDENTIAL", SECRET)
    code = tool.main(["--activate", "1", "2", "3", "--i-am-the-operator", "Operator"])
    out = capsys.readouterr().out
    session = FakeSession.instances[0]
    assert session.bootstrapped
    assert session.posts == [
        "/api/v1/skills/arc-1/versions/1/activate",
        "/api/v1/skills/arc-2/versions/1/activate",
    ], "the refusal for 2 must stop before 3"
    assert code == 1
    assert SECRET not in out, "the credential must never reach output"


def _suspend(repository: SkillRepository, legacy_id: int) -> None:
    """A skill the machine withdrew: active, then suspended (what retiring its
    reflex does since the operator's 2026-09-29 decision)."""
    repository.save(_record(legacy_id, ["verify: command=pytest s.py -q"], ready=True))
    skill_id = f"arc-{legacy_id}"
    for state in ("human_reviewed", "active", "suspended"):
        repository.transition_state(skill_id, 1, state)


def test_the_listing_shows_suspended_skills_with_their_reactivate_key(
    world, capsys
) -> None:
    _suspend(world, 5)
    assert tool.main([]) == 0
    listing = json.loads(capsys.readouterr().out)
    [row] = listing["suspended"]
    assert row["reactivate"] == "arc-5@1" and row["state"] == "suspended"
    assert not FakeSession.instances


def test_reactivation_needs_the_operators_declaration(world) -> None:
    _suspend(world, 5)
    with pytest.raises(SystemExit, match="operator"):
        tool.main(["--reactivate", "arc-5@1"])
    assert not FakeSession.instances


def test_only_a_suspended_skill_can_be_reactivated(world, monkeypatch) -> None:
    monkeypatch.setenv("AIOS_OPERATOR_CREDENTIAL", SECRET)
    with pytest.raises(SystemExit, match="not a suspended skill"):
        tool.main(["--reactivate", "arc-1@1", "--i-am-the-operator", "Operator"])
    assert not FakeSession.instances


def test_reactivation_drives_the_same_capability_route(
    world, monkeypatch, capsys
) -> None:
    _suspend(world, 5)
    monkeypatch.setenv("AIOS_OPERATOR_CREDENTIAL", SECRET)
    code = tool.main(["--reactivate", "arc-5@1", "--i-am-the-operator", "Operator"])
    out = capsys.readouterr().out
    assert FakeSession.instances[0].posts == [
        "/api/v1/skills/arc-5/versions/1/activate"
    ]
    assert code == 0
    assert SECRET not in out
