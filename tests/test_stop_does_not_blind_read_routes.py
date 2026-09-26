"""An engaged emergency stop must not blind the operator.

#373 made every learning write ask the latch, including
`Cerebellum.try_compile_all`. `get_cerebellum` ran that sweep on EVERY request,
and `get_skill_memory` depends on `get_cerebellum` -- so while the stop was
engaged, three READ-only routes that depend on the skill store answered 503:
the skills and trails pages and the mirror snapshot the UI renders from. The
operator lost sight of learned state exactly when inspecting it matters most.

These tests use the real dependency chain (no `get_skill_memory` override --
the existing route tests all faked it, which is how the regression passed a
6,710-test suite) and freeze only the LEARNING latch, so nothing else in the
session sees an engaged stop.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from aios.api import deps
from aios.api.main import app
from aios.application.governance.emergency_stop import (
    EmergencyStopController,
    EmergencyStopHooks,
)
from aios.domain.governance.contracts import EmergencyStopRequest
from aios.memory import learning_freeze


def _noop(*_a, **_k):
    return None


@pytest.fixture()
def frozen_learning(tmp_path, monkeypatch):
    """Engage a throwaway latch that only the learning freeze reads."""
    latch = tmp_path / "emergency_stop.db"
    monkeypatch.setattr(learning_freeze, "_latch_path", lambda: latch)
    monkeypatch.setattr(learning_freeze, "_controllers", {})
    controller = EmergencyStopController(
        latch,
        hooks=EmergencyStopHooks(
            revoke_capabilities=_noop,
            cancel_queued_missions=_noop,
            kill_active_workers=_noop,
            disable_autonomy=_noop,
            preserve_evidence=_noop,
        ),
    )
    controller.engage(
        EmergencyStopRequest(
            operator_id="operator:test",
            authentication_event_id="event:test",
            reason="read routes under a frozen learning latch",
        )
    )
    assert not learning_freeze.learning_permitted()
    return controller


@pytest.fixture()
def client():
    app.dependency_overrides.clear()
    with TestClient(app, client=("127.0.0.1", 12345)) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/development/skills",
        "/api/v1/development/trails",
        "/api/v1/mirror/snapshot",
    ],
)
def test_read_routes_still_answer_while_learning_is_frozen(
    frozen_learning, client, path
) -> None:
    response = client.get(path)
    assert response.status_code == 200, (
        f"{path} answered {response.status_code} while learning was frozen: "
        f"{response.text[:200]}"
    )


def test_the_per_request_compile_sweep_is_skipped_not_raised(frozen_learning) -> None:
    """The provider every one of those routes depends on resolves while frozen."""
    assert deps.get_cerebellum() is not None


def test_the_sweep_skips_only_while_frozen(tmp_path, monkeypatch) -> None:
    """The positive control: a sweep compiles when learning is permitted, and
    compiles nothing -- without raising -- when it is frozen. The fix lives in
    the cerebellum, not in `deps.py`, which is an entrypoint of eight green
    organs."""
    from aios.core.cerebellum import Cerebellum
    from aios.core.verification_strength import VerificationStrength
    from aios.memory.db import init_memory_db
    from aios.memory.skills import SkillMemory

    db = tmp_path / "memory.db"
    init_memory_db(db)
    skills = SkillMemory(db_path=db)
    for _ in range(3):
        skills.record_attempt(
            "run the pin tests",
            ["verify: command=pytest x -q"],
            success=True,
            strength=VerificationStrength.STRONG,
        )
    import aios.core.cerebellum as cerebellum_module

    monkeypatch.setattr(cerebellum_module, "learning_permitted", lambda: False)
    assert Cerebellum(db).try_compile_all() == 0, "a frozen sweep compiled something"
    monkeypatch.setattr(cerebellum_module, "learning_permitted", lambda: True)
    assert Cerebellum(db).try_compile_all() == 1, "a permitted sweep compiled nothing"
