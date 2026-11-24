"""GAGOS speaks first: the brief it gives the operator when he opens the face.

2026-11-24, the operator: "remember GAGOS ~ jarvis, it should honestly behave
like one". Pinned here: the brief is facts read from GAGOS's own stores (what
it did since he last looked, what waits on him, what broke), composed without a
model; it reads and never writes; a signed-in operator reads it without a fresh
re-authentication, and nobody else reads it at all.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from aios.api.main import app
from aios.api.routes import gagos_tasks
from aios.application.observability.brief import (
    MAX_LINES,
    Facts,
    attestation_waits,
    compose,
    ledger_facts,
)
from aios.maintenance.daily_work import DailyLedger

NOW = datetime(2026, 11, 24, 9, 0, tzinfo=timezone.utc)
SINCE = NOW - timedelta(hours=12)
PR = "https://github.com/swap821/ai-editor/pull/{}"
LIVE = {"live": True}


def _facts(**kw) -> Facts:
    base = dict(
        since=SINCE,
        now=NOW,
        mission_envelope=LIVE,
        skill_envelope=LIVE,
        hours=(
            {
                "day": "2026-11-24T08",
                "status": "ran",
                "reason": None,
                "updated_at": (NOW - timedelta(minutes=10)).isoformat(),
            },
        ),
    )
    return Facts(**{**base, **kw})


def test_nothing_to_say_is_a_quiet_brief() -> None:
    told = compose(_facts())
    assert told.quiet
    assert (told.did, told.waiting, told.broke) == ((), (), ())


def test_what_it_did_since_he_last_looked() -> None:
    told = compose(
        _facts(
            deliveries=(
                {
                    "pr_url": PR.format(741),
                    "created_at": (NOW - timedelta(hours=2)).isoformat(),
                },
                {
                    "pr_url": PR.format(741),
                    "created_at": (NOW - timedelta(hours=2)).isoformat(),
                },
                {
                    "pr_url": PR.format(700),
                    "created_at": (NOW - timedelta(days=3)).isoformat(),
                },
            ),
            merged=frozenset({PR.format(700), PR.format(741)}),
            proposal_statuses=(
                "delivered",
                "delivered",
                "rejected",
                "refused",
                "refused",
            ),
            goals_taken=1,
        )
    )
    assert told.did == (
        "Delivered 1 pull request: #741.",
        "Its changes: 2 accepted, 1 rejected by its reviewer, 2 refused before review.",
        "Took 1 goal.",
    ), "only what happened since he last looked"
    assert told.waiting == ()


def test_what_waits_on_him() -> None:
    told = compose(
        _facts(
            deliveries=(
                {"pr_url": PR.format(752), "created_at": SINCE.isoformat()},
                {"pr_url": PR.format(749), "created_at": SINCE.isoformat()},
                {"pr_url": PR.format(700), "created_at": SINCE.isoformat()},
            ),
            merged=frozenset({PR.format(700)}),
            mission_envelope={"live": False, "reason": "the envelope has expired"},
            skill_envelope={
                "live": False,
                "reason": "the operator has not signed an envelope",
            },
            attestation_waits=((44, "Golden Mission and Endurance Evaluation"),),
        )
    )
    assert told.waiting == (
        "GAGOS's pull request #749 is not yet seen merged.",
        "GAGOS's pull request #752 is not yet seen merged.",
        "No mission envelope is live (the envelope has expired), so GAGOS starts no council missions.",
        "No skill envelope is live (the operator has not signed an envelope), so GAGOS activates no skills.",
        "Organ 44 (Golden Mission and Endurance Evaluation) waits on your attestation.",
    )


def test_what_broke() -> None:
    hours = (
        {
            "day": "2026-11-24T05",
            "status": "blocked",
            "reason": "C:\\gdw has uncommitted changes",
            "updated_at": (NOW - timedelta(hours=4)).isoformat(),
        },
        {
            "day": "2026-11-24T04",
            "status": "ran",
            "reason": "propose exited 1",
            "updated_at": (NOW - timedelta(hours=5)).isoformat(),
        },
        {
            "day": "2026-11-23T10",
            "status": "blocked",
            "reason": "before he last looked",
            "updated_at": (NOW - timedelta(days=1)).isoformat(),
        },
    )
    told = compose(_facts(stop_engaged=True, hours=hours))
    assert told.broke == (
        "The emergency stop is engaged; GAGOS does nothing until you clear it.",
        "Hour 2026-11-24T05 was blocked: C:\\gdw has uncommitted changes.",
        "Hour 2026-11-24T04 failed: propose exited 1.",
        "GAGOS's hourly job has been silent for 4 hours (last at 2026-11-24 05:00 UTC).",
    )


def test_a_job_that_never_ran_says_so() -> None:
    assert compose(_facts(hours=())).broke == (
        "GAGOS's hourly job has no recorded hour.",
    )


def test_a_long_list_is_counted_never_dropped() -> None:
    deliveries = tuple(
        {"pr_url": PR.format(n), "created_at": SINCE.isoformat()}
        for n in range(700, 710)
    )
    waiting = compose(_facts(deliveries=deliveries)).waiting
    assert len(waiting) == MAX_LINES
    assert waiting[-1] == f"and {10 - (MAX_LINES - 1)} more"


def test_only_organs_waiting_on_his_attestation_are_named() -> None:
    organs = [
        {
            "organ_id": 44,
            "name": "Golden",
            "status": "yellow",
            "condition_verdicts": {
                "C10": "WAITING - operator attestation: the cohort ..."
            },
        },
        {
            "organ_id": 46,
            "name": "Learning",
            "status": "yellow",
            "condition_verdicts": {"C10": "PASS - live evidence present"},
        },
        {
            "organ_id": 9,
            "name": "Caps",
            "status": "green",
            "condition_verdicts": {"C10": "WAITING - operator attestation"},
        },
    ]
    assert attestation_waits(organs) == ((44, "Golden"),)


def test_the_ledger_is_read_read_only(tmp_path) -> None:
    led = DailyLedger(tmp_path / "ledger.db")
    led.record_delivery(
        "gd-1", branch="gagos/daily", outcome="delivered", pr_url=PR.format(751)
    )
    led.record_merged(PR.format(700))
    led.record_day("2026-11-24T08", "ran")
    before = (tmp_path / "ledger.db").read_bytes()
    found = ledger_facts(
        tmp_path / "ledger.db", datetime.now(timezone.utc) - timedelta(hours=1)
    )
    assert [d["pr_url"] for d in found["deliveries"]] == [PR.format(751)]
    assert found["merged"] == frozenset({PR.format(700)})
    assert found["hours"][0]["day"] == "2026-11-24T08"
    assert (tmp_path / "ledger.db").read_bytes() == before, "the brief never writes"
    assert ledger_facts(tmp_path / "missing.db", NOW) == {}


# -- the route -------------------------------------------------------------------


class _Envelope:
    def __init__(self, status) -> None:
        self._status = status

    def status(self):
        return self._status


@pytest.fixture()
def brief_env(tmp_path):
    led = DailyLedger(tmp_path / "ledger.db")
    led.record_delivery(
        "gd-1", branch="gagos/daily", outcome="delivered", pr_url=PR.format(752)
    )
    led.record_day("2026-11-24T08", "ran")
    organs = tmp_path / "organs.json"
    organs.write_text(
        json.dumps(
            [
                {
                    "organ_id": 44,
                    "name": "Golden",
                    "status": "yellow",
                    "condition_verdicts": {"C10": "WAITING - operator attestation"},
                },
            ]
        ),
        encoding="utf-8",
    )
    overrides = {
        gagos_tasks.get_gagos_task_ledger: lambda: led,
        gagos_tasks.get_gagos_envelope_authority: lambda: _Envelope(
            {"live": False, "reason": "the envelope has expired"}
        ),
        gagos_tasks.get_gagos_skill_envelope_authority: lambda: _Envelope(
            {"live": True}
        ),
        gagos_tasks.get_organ_ledger_path: lambda: organs,
        gagos_tasks._stop_engaged: lambda: False,
    }
    app.dependency_overrides.update(overrides)
    try:
        with TestClient(app, client=("127.0.0.1", 12345)) as client:
            yield client
    finally:
        for key in overrides:
            app.dependency_overrides.pop(key, None)


def test_the_operator_reads_his_brief(brief_env) -> None:
    response = brief_env.get("/api/gagos/brief")
    assert response.status_code == 200, response.text
    told = response.json()["brief"]
    assert told["did"] == ["Delivered 1 pull request: #752."]
    assert told["waiting"][0] == "GAGOS's pull request #752 is not yet seen merged."
    assert (
        "No mission envelope is live (the envelope has expired)" in told["waiting"][1]
    )
    assert told["waiting"][2] == "Organ 44 (Golden) waits on your attestation."
    assert told["broke"] == [] and told["quiet"] is False


def test_a_signed_in_operator_needs_no_fresh_re_authentication(brief_env) -> None:
    """The brief only reads: a plain sign-in is enough, unlike every route that
    changes something."""
    from aios.api.deps import get_identity_service
    from tests import conftest

    identity = get_identity_service()
    plain = identity.authenticate_credential(conftest._TEST_OPERATOR_CREDENTIAL)
    brief_env.cookies.set("session_id", plain.session_cookie)
    assert brief_env.get("/api/gagos/brief").status_code == 200
    assert brief_env.get("/api/gagos/tasks").status_code == 403, (
        "changes stay privileged"
    )


def test_nobody_else_reads_it(brief_env) -> None:
    brief_env.cookies.clear()
    assert brief_env.get("/api/gagos/brief").status_code in (401, 403)


def test_since_is_a_time_and_never_reaches_too_far_back(brief_env) -> None:
    assert (
        brief_env.get("/api/gagos/brief", params={"since": "yesterday"}).status_code
        == 422
    )
    told = brief_env.get(
        "/api/gagos/brief", params={"since": "2020-01-01T00:00:00+00:00"}
    ).json()["brief"]
    since = datetime.fromisoformat(told["since"])
    assert datetime.now(timezone.utc) - since <= timedelta(days=30, minutes=1)
