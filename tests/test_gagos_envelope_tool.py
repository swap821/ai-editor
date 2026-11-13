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
    return tool.run(tool.parser().parse_args(argv), connect=lambda base: live)


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
