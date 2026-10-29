"""``Cerebellum.readiness``: would each reflex serve its own request here, now?

Added 2026-10-29 ("make the daily animal boring"). A reflex stops serving
silently: a restart under another scope binding, replay of approved commands
switched off, an approval missing in this workspace, or a changed file the skill
touches each leave the playbook compiled while every matching turn goes to the
model. A changed file also withdraws the reflex on the first turn that matches
it, and only the operator's re-activation brings it back. Pinned:

* each of those is reported, with its reason, and a reflex with none is ready;
* the check is read-only: a stale reflex it reports is still compiled and its
  skill still active afterwards, where ``match`` withdraws both;
* it agrees with ``match``: ready means the reflex is matched, and the reasons
  it gives are the ones ``match`` refuses on.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from aios import config
from aios.core import replay_commands
from aios.core.autonomy import UNGOVERNED_FIXTURE
from aios.memory.db import get_connection
from aios.security import scope_lock
from tests.test_phase2_reflex_gate import _activate, build_world

PRINCIPAL = "principal:test"
GOAL = "run the readiness probe tests and report the result"


@pytest.fixture()
def reflex(tmp_path: Path, monkeypatch):
    """One activated, compiled reflex whose command the principal approved.

    Its command runs a real test file inside a declared root, so it is YELLOW
    (approvable) and its verification plan is executable, as a live one is."""
    probe = (
        Path(config.PROJECT_ROOT)
        / "training_ground"
        / f"_readiness_{tmp_path.name}_test.py"
    )
    probe.write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    command = f"pytest training_ground/{probe.name} -q"
    try:
        legacy_db, cerebellum, _bus, repository, slot = build_world(
            tmp_path, monkeypatch
        )
        with get_connection(legacy_db) as conn:
            conn.execute("DELETE FROM compiled_playbooks")
        slot.record_attempt(
            GOAL, [f"verify: command={command}"], success=True, principal=PRINCIPAL
        )
        record = next(
            r for r in repository.list_skills() if r.provenance.get("source") == "live"
        )
        _activate(repository, record)
        cerebellum.attach_reflex_gate(slot)
        assert cerebellum.try_compile_all() == 1
        monkeypatch.setattr(config, "REPLAY_APPROVED_COMMANDS_ENABLED", True)
        assert replay_commands.record_command_approval(
            command,
            principal=PRINCIPAL,
            db_path=legacy_db,
            emergency_stop=UNGOVERNED_FIXTURE,
        )
        yield legacy_db, cerebellum, repository, record, command, probe
    finally:
        probe.unlink(missing_ok=True)


def _only(cerebellum) -> dict:
    [row] = cerebellum.readiness(emergency_stop=UNGOVERNED_FIXTURE)
    return row


def _status(legacy_db: Path) -> list[str]:
    with get_connection(legacy_db) as conn:
        return [
            r["status"] for r in conn.execute("SELECT status FROM compiled_playbooks")
        ]


def test_an_activated_approved_fresh_reflex_is_ready(reflex) -> None:
    _, cerebellum, *_ = reflex
    row = _only(cerebellum)
    assert row["ready"] is True, row["reasons"]
    assert row["reasons"] == []
    assert row["principal"] == PRINCIPAL
    assert row["goal"] == GOAL
    # It agrees with the live path: the same reflex is matched.
    assert cerebellum.match(GOAL, principal=PRINCIPAL) is not None


def test_no_approval_in_this_workspace_is_reported(reflex) -> None:
    legacy_db, cerebellum, _, _, command, _ = reflex
    assert replay_commands.revoke_command_decision(
        command, principal=PRINCIPAL, db_path=legacy_db
    )
    row = _only(cerebellum)
    assert row["ready"] is False
    assert any(
        "would ask for approval" in r and "no approval" in r for r in row["reasons"]
    )


def test_replay_switched_off_is_named_as_the_reason(reflex, monkeypatch) -> None:
    _, cerebellum, *_ = reflex
    monkeypatch.setattr(config, "REPLAY_APPROVED_COMMANDS_ENABLED", False)
    row = _only(cerebellum)
    assert row["ready"] is False
    assert any("replay of approved commands is off" in r for r in row["reasons"])


def test_another_scope_binding_is_reported(reflex) -> None:
    """The restart hazard: the same store, launched without the binding the
    reflex was earned under. The scope identity differs, so it would not serve."""
    _, cerebellum, *_ = reflex
    other = Path(config.PROJECT_ROOT) / "lab"
    with scope_lock.scope_context([other]):
        row = _only(cerebellum)
        assert cerebellum.match(GOAL, principal=PRINCIPAL) is None
    assert row["ready"] is False
    assert any(r.startswith("not applicable:") for r in row["reasons"])


def test_an_inactive_skill_is_reported(reflex) -> None:
    _, cerebellum, repository, record, *_ = reflex
    repository.transition_state(record.skill_id, record.version, "suspended")
    row = _only(cerebellum)
    assert row["ready"] is False
    assert any("not active" in r for r in row["reasons"])


def test_a_stale_reflex_is_reported_and_left_alone(reflex) -> None:
    """The file the skill touches is not a version it was validated on. The
    check says so, and that the first matching turn will withdraw it, and
    withdraws nothing itself. ``match`` then does exactly what it warned of."""
    legacy_db, cerebellum, repository, record, _, probe = reflex
    probe.write_text("def test_ok():\n    assert 1 == 1\n", encoding="utf-8")

    row = _only(cerebellum)
    assert row["ready"] is False
    assert any(
        r.startswith("stale, and the first matching turn") for r in row["reasons"]
    )
    # Read-only.
    assert _status(legacy_db) == ["compiled"]
    assert repository.get(record.skill_id, record.version).state == "active"

    # The live path, for contrast: the warning was right.
    assert cerebellum.match(GOAL, principal=PRINCIPAL) is None
    assert _status(legacy_db) == ["retired"]
    assert repository.get(record.skill_id, record.version).state == "suspended"


def test_a_red_command_is_never_ready_even_if_approved(reflex, monkeypatch) -> None:
    """The check reads the gateway's own classifier, as the replay preflight
    does; a command it calls RED is refused whatever was approved."""
    from types import SimpleNamespace

    from aios.security import gateway

    _, cerebellum, *_ = reflex
    monkeypatch.setattr(
        gateway,
        "classify",
        lambda command, *a, **k: SimpleNamespace(zone=gateway.Zone.RED),
    )
    row = _only(cerebellum)
    assert row["ready"] is False
    assert any("is RED here" in r for r in row["reasons"])
