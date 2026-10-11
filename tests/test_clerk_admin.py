"""``python -m aios clerk``: the operator admits the clerk; nothing else can.

Pinned: approving and granting are the operator's acts -- refused without his
own terminal, refused unless he types the model id back; revoking (the safe
direction) is never gated; status reads the registry and builds nothing.
"""

from __future__ import annotations

import io
from types import SimpleNamespace

import pytest

from aios.domain.local_workforce.contracts import LocalJobProfile
from aios.operations import clerk_admin


class _Tty(io.StringIO):
    def isatty(self) -> bool:
        return True


def _model(model_id="qwen2.5:3b", **over):
    fields = dict(
        model_id=model_id,
        installed=True,
        operator_approved=True,
        admission_status="approved",
        health="healthy",
        allowed_job_profiles=frozenset({LocalJobProfile.SELECT_SKILL}),
    )
    fields.update(over)
    return SimpleNamespace(**fields)


class _Service:
    def __init__(self, models=()):
        self.registry = SimpleNamespace(list_models=lambda: list(models))
        self.calls: list[tuple] = []

    def approve(self, model_id, approved):
        self.calls.append(("approve", model_id, approved))

    def qualify(self, model_id):
        self.calls.append(("qualify", model_id))
        return {
            "status": "rejected",
            "reason": "Failed qualification suite",
            "qualification": {
                "test_results": [
                    {
                        "test_id": "skill_selection_abstains",
                        "passed": False,
                        "detail": "admitted",
                    },
                    {"test_id": "json_validity", "passed": True},
                ]
            },
        }

    def update_profiles(self, model_id, roles):
        self.calls.append(("grant", model_id, tuple(roles)))
        return _model(
            model_id, allowed_job_profiles=frozenset(LocalJobProfile(r) for r in roles)
        )

    def refresh(self):
        return []


def _run(command, service, *, stdin=None, typed="", **kw):
    lines: list[str] = []
    code = clerk_admin.run(
        command,
        service=service,
        stdin=stdin if stdin is not None else io.StringIO(),
        ask=lambda prompt: typed,
        out=lines.append,
        **kw,
    )
    return code, "\n".join(lines)


def test_approval_needs_the_operators_terminal() -> None:
    service = _Service()
    with pytest.raises(clerk_admin.ClerkAdminError, match="your own terminal"):
        _run("approve", service, model_id="qwen2.5:3b", typed="qwen2.5:3b")
    assert service.calls == []


def test_approval_needs_the_model_id_typed_back() -> None:
    service = _Service()
    with pytest.raises(clerk_admin.ClerkAdminError, match="nothing changed"):
        _run("approve", service, stdin=_Tty(), model_id="qwen2.5:3b", typed="yes")
    assert service.calls == []
    code, _ = _run(
        "approve", service, stdin=_Tty(), model_id="qwen2.5:3b", typed="qwen2.5:3b"
    )
    assert code == 0 and service.calls == [("approve", "qwen2.5:3b", True)]


def test_granting_is_the_operators_act_too() -> None:
    service = _Service()
    with pytest.raises(clerk_admin.ClerkAdminError, match="your own terminal"):
        _run("grant", service, model_id="m", roles=["select_skill"], typed="m")
    code, out = _run(
        "grant", service, stdin=_Tty(), model_id="m", roles=["select_skill"], typed="m"
    )
    assert code == 0 and "select_skill" in out


def test_revoking_is_never_gated() -> None:
    service = _Service()
    code, _ = _run("revoke", service, model_id="qwen2.5:3b")
    assert code == 0 and service.calls == [("approve", "qwen2.5:3b", False)]


def test_qualify_reports_each_failed_test() -> None:
    code, out = _run("qualify", _Service(), model_id="qwen2.5:3b")
    assert code == 1
    assert "skill_selection_abstains" in out and "json_validity" not in out


def test_status_asks_the_dispatchers_question() -> None:
    eligible = _model("ok:1b")
    rejected = _model("no:1b", admission_status="rejected")
    code, out = _run("status", _Service([eligible, rejected]))
    assert code == 0
    assert "ok:1b" in out and "select_skill" in out
    assert "1 of 2 models may take a job" in out
    code, _ = _run("status", _Service([rejected]))
    assert code == 1


def test_status_never_builds_the_service(monkeypatch) -> None:
    def no_service():
        raise AssertionError("status built the service (and its provenance store)")

    monkeypatch.setattr(clerk_admin, "default_service", no_service)
    monkeypatch.setattr(
        clerk_admin,
        "default_registry",
        lambda: SimpleNamespace(list_models=lambda: []),
    )
    assert clerk_admin.run("status", out=lambda line: None) == 1


def test_the_cli_routes_to_the_clerk(monkeypatch, capsys) -> None:
    from aios import __main__ as cli

    seen = {}

    def fake_run(command, **kw):
        seen.update(command=command, **kw)
        return 0

    monkeypatch.setattr(clerk_admin, "run", fake_run)
    assert cli.main(["clerk", "grant", "qwen2.5:3b", "select_skill", "classify"]) == 0
    assert seen == {
        "command": "grant",
        "model_id": "qwen2.5:3b",
        "roles": ["select_skill", "classify"],
    }
