"""The operator's tool for GAGOS's daily envelope (2026-11-13).

He signed three envelopes on 2026-11-13 with a script kept outside the repo;
signing is daily, so it is now a tracked tool beside tools/activate_skills.py,
on the same authenticated path (ProbeSession: login, fresh re-authentication).
"""

from __future__ import annotations

import pytest

from tools import gagos_envelope as tool


class Reply:
    def __init__(self, status=201, body=None) -> None:
        self.status_code = status
        self._body = body or {"envelope": {"live": True}}
        self.text = ""

    def json(self):
        return self._body


class Live:
    def __init__(self, status=201) -> None:
        self.calls = []
        self.status = status

    def post_stream(self, path, payload, timeout):
        self.calls.append(("POST", path, payload))
        return Reply(self.status)

    def get(self, path):
        self.calls.append(("GET", path, None))
        return Reply(200)


def _run(argv, live):
    return tool.run(
        tool.parser().parse_args(argv), connect=lambda base: live, waiting=lambda: []
    )


def test_sign_with_no_flags_signs_the_terms_of_2026_11_13() -> None:
    live = Live()
    assert _run(["sign"], live) == 0
    assert live.calls == [
        (
            "POST",
            "/api/gagos/envelope",
            {
                "folders": ["frontend/src/superbrain/", "frontend/src/workbench/"],
                "kinds": ["code", "tests"],
                "maxMissions": 2,
                "hours": 8,
            },
        )
    ]


def test_sign_takes_his_own_terms() -> None:
    live = Live()
    _run(
        [
            "sign",
            "--folders",
            "frontend/src/superbrain/",
            "--kinds",
            "tests",
            "--missions",
            "1",
            "--hours",
            "4",
        ],
        live,
    )
    assert live.calls[0][2] == {
        "folders": ["frontend/src/superbrain/"],
        "kinds": ["tests"],
        "maxMissions": 1,
        "hours": 4,
    }


def test_status_reads_and_revoke_ends() -> None:
    live = Live()
    assert _run(["status"], live) == 0
    assert _run(["revoke"], live) == 0
    assert live.calls == [
        ("GET", "/api/gagos/envelope", None),
        ("POST", "/api/gagos/envelope/revoke", {}),
    ]


def test_a_refusal_is_a_failed_exit() -> None:
    assert _run(["sign"], Live(status=403)) == 1


def test_no_credential_no_session(monkeypatch) -> None:
    monkeypatch.delenv("AIOS_OPERATOR_CREDENTIAL", raising=False)
    monkeypatch.setattr(tool.sys.stdin, "isatty", lambda: False)
    with pytest.raises(SystemExit, match="never enrolls"):
        tool._credential()


def test_the_skill_envelope_is_signed_read_and_ended_through_his_routes() -> None:
    """2026-11-18, the operator: "only once, not again and again": he signs a
    standing skill envelope, by default for 30 days and 50 activations."""
    live = Live()
    assert _run(["skills-sign"], live) == 0
    assert _run(["skills-sign", "--days", "7", "--activations", "5"], live) == 0
    assert _run(["skills-status"], live) == 0
    assert _run(["skills-revoke"], live) == 0
    assert live.calls == [
        ("POST", "/api/gagos/skill-envelope", {"days": 30, "maxActivations": 50}),
        ("POST", "/api/gagos/skill-envelope", {"days": 7, "maxActivations": 5}),
        ("GET", "/api/gagos/skill-envelope", None),
        ("POST", "/api/gagos/skill-envelope/revoke", {}),
    ]


def test_standing_sign_signs_whole_days_with_missions_a_day() -> None:
    """2026-11-24, the operator: GAGOS should work like Jarvis, on his
    authority, without a fresh signature each morning."""
    live = Live()
    assert _run(["standing-sign"], live) == 0
    assert live.calls == [
        (
            "POST",
            "/api/gagos/envelope",
            {
                "folders": ["frontend/src/superbrain/", "frontend/src/workbench/"],
                "kinds": ["code", "tests"],
                "maxMissions": 2,
                "hours": 24,
                "days": 30,
            },
        )
    ]
    live = Live()
    assert _run(["standing-sign", "--days", "7", "--missions", "3"], live) == 0
    assert live.calls[0][2]["days"] == 7 and live.calls[0][2]["maxMissions"] == 3
    live = Live()
    assert _run(["sign"], live) == 0
    assert "days" not in live.calls[0][2], "sign stays a day envelope"
