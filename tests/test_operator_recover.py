"""The operator recovers from losing BOTH secrets without losing his identity.

2026-10-19: the operator credential was lost, and the recovery code enrollment
issued had never been wired to anything. Re-enrolling would mint a new operator
id and orphan everything scoped to the old one. `reset_secrets_locally` and
`tools/operator_recover.py` replace the secrets and keep the id.
"""

from __future__ import annotations

import importlib.util
import sqlite3
import sys
from pathlib import Path

import pytest

from aios.application.identity.service import (
    IdentityError,
    IdentityService,
    InvalidCredential,
)
from aios.infrastructure.identity.sqlite_store import credential_digest

REPO_ROOT = Path(__file__).resolve().parents[1]
NEW_CREDENTIAL = "correct horse battery staple 2026"
NEW_RECOVERY = "a different long recovery phrase 77"


def _load_tool():
    spec = importlib.util.spec_from_file_location(
        "_operator_recover", REPO_ROOT / "tools" / "operator_recover.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _service(tmp_path):
    return IdentityService(
        identity_db_path=tmp_path / "identity.db",
        session_db_path=tmp_path / "sessions.db",
    )


# --------------------------------------------------------------------------- #
# The service
# --------------------------------------------------------------------------- #
def test_a_reset_keeps_the_operator_id_and_swaps_the_secrets(tmp_path) -> None:
    service = _service(tmp_path)
    enrollment = service.enroll_operator(display_name="Kumar")

    kept = service.reset_secrets_locally(NEW_CREDENTIAL, NEW_RECOVERY)

    assert kept == enrollment.operator_id
    assert service.store.operator()["operator_id"] == enrollment.operator_id
    with pytest.raises(InvalidCredential):
        service.authenticate_credential(enrollment.enrollment_credential)
    again = service.authenticate_credential(NEW_CREDENTIAL)
    assert again.principal.principal_id == enrollment.operator_id
    assert service.store.operator()["recovery_digest"] == credential_digest(
        NEW_RECOVERY
    )


def test_a_reset_logs_out_every_existing_session(tmp_path) -> None:
    service = _service(tmp_path)
    enrollment = service.enroll_operator(display_name="Kumar")
    before = service.authenticate_credential(enrollment.enrollment_credential)
    assert service.get_authenticated_principal(before.session_cookie) is not None

    service.reset_secrets_locally(NEW_CREDENTIAL, NEW_RECOVERY)

    assert service.get_authenticated_principal(before.session_cookie) is None


def test_a_reset_is_recorded_and_stores_no_secret(tmp_path) -> None:
    service = _service(tmp_path)
    service.enroll_operator(display_name="Kumar")
    service.reset_secrets_locally(NEW_CREDENTIAL, NEW_RECOVERY)

    db = tmp_path / "identity.db"
    with sqlite3.connect(str(db)) as conn:
        kinds = [
            r[0] for r in conn.execute("SELECT event_type FROM authentication_events")
        ]
    assert "local_secret_reset" in kinds
    stored = db.read_bytes()
    assert NEW_CREDENTIAL.encode() not in stored and NEW_RECOVERY.encode() not in stored


@pytest.mark.parametrize(
    "credential, recovery",
    [
        ("too short", NEW_RECOVERY),
        (NEW_CREDENTIAL, "short"),
        (NEW_CREDENTIAL, NEW_CREDENTIAL),
        ("                         ", NEW_RECOVERY),
    ],
    ids=["short-credential", "short-recovery", "same-secret", "blank"],
)
def test_a_refused_reset_changes_nothing(tmp_path, credential, recovery) -> None:
    service = _service(tmp_path)
    enrollment = service.enroll_operator(display_name="Kumar")
    with pytest.raises(ValueError):
        service.reset_secrets_locally(credential, recovery)
    assert service.authenticate_credential(enrollment.enrollment_credential)


def test_no_operator_means_enroll_not_reset(tmp_path) -> None:
    with pytest.raises(IdentityError):
        _service(tmp_path).reset_secrets_locally(NEW_CREDENTIAL, NEW_RECOVERY)


# --------------------------------------------------------------------------- #
# The tool
# --------------------------------------------------------------------------- #
def _run(tmp_path, answers, confirm_word, capsys):
    tool = _load_tool()
    prompts = iter(answers)
    audited: list[tuple[str, str]] = []
    code = tool.reset(
        identity_db_path=tmp_path / "identity.db",
        session_db_path=tmp_path / "sessions.db",
        prompt=lambda _p: next(prompts),
        confirm=lambda _p: confirm_word,
        audit=lambda a, p: audited.append((a, p)),
    )
    out = capsys.readouterr()
    return code, audited, out.out + out.err


def test_the_tool_resets_with_typed_secrets_and_prints_none(tmp_path, capsys) -> None:
    enrollment = _service(tmp_path).enroll_operator(display_name="Kumar")
    code, audited, output = _run(
        tmp_path,
        [NEW_CREDENTIAL, NEW_CREDENTIAL, NEW_RECOVERY, NEW_RECOVERY],
        "reset",
        capsys,
    )
    assert code == 0
    assert NEW_CREDENTIAL not in output and NEW_RECOVERY not in output
    assert len(audited) == 1 and enrollment.operator_id in audited[0][1]
    assert _service(tmp_path).authenticate_credential(NEW_CREDENTIAL)


def test_mismatched_entries_change_nothing(tmp_path, capsys) -> None:
    enrollment = _service(tmp_path).enroll_operator(display_name="Kumar")
    with pytest.raises(SystemExit):
        _run(tmp_path, [NEW_CREDENTIAL, NEW_CREDENTIAL + "x"], "reset", capsys)
    assert _service(tmp_path).authenticate_credential(enrollment.enrollment_credential)


def test_anything_but_reset_changes_nothing(tmp_path, capsys) -> None:
    enrollment = _service(tmp_path).enroll_operator(display_name="Kumar")
    code, audited, _ = _run(
        tmp_path,
        [NEW_CREDENTIAL, NEW_CREDENTIAL, NEW_RECOVERY, NEW_RECOVERY],
        "yes",
        capsys,
    )
    assert code == 1 and audited == []
    assert _service(tmp_path).authenticate_credential(enrollment.enrollment_credential)


def test_the_tool_refuses_without_a_terminal(monkeypatch) -> None:
    tool = _load_tool()
    monkeypatch.delenv(tool._ALLOW_NONTTY_ENV, raising=False)
    monkeypatch.setattr(tool, "_interactive", lambda: False)
    assert tool.main(["--reset"]) == 2
