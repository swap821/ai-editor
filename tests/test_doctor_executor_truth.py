"""`doctor`'s executor check asks the backend's own question, not whether a CLI is on PATH.

Measured 2026-10-19 (rebuild drill): `doctor` said "docker runtime is
available" because `docker` was on PATH, while the daemon was stopped and the
backend's startup check said approved execution would FAIL CLOSED -- which it
did. One question, one answer: `validate_approved_execution_backend`.
"""

from __future__ import annotations


from aios.core import executor
from aios.operations import doctor


def test_a_ready_backend_is_reported_ready(monkeypatch) -> None:
    monkeypatch.setattr(executor, "validate_approved_execution_backend", lambda: None)
    assert doctor._approved_execution_probe() == (
        True,
        "approved execution backend is ready",
    )


def test_a_stopped_daemon_is_reported_unavailable_with_the_backends_words(
    monkeypatch,
) -> None:
    warning = "container execution backend unavailable (daemon stopped); approved ... FAIL CLOSED"
    monkeypatch.setattr(
        executor, "validate_approved_execution_backend", lambda: warning
    )
    monkeypatch.setattr(executor, "approved_runner_from_config", lambda: object())
    assert doctor._approved_execution_probe() == (False, warning)


def test_host_mode_runs_and_says_it_is_development_only(monkeypatch) -> None:
    warning = "host execution backend selected: ... DEVELOPMENT ONLY"
    monkeypatch.setattr(
        executor, "validate_approved_execution_backend", lambda: warning
    )
    monkeypatch.setattr(executor, "approved_runner_from_config", lambda: None)
    assert doctor._approved_execution_probe() == (True, warning)


def test_a_misconfigured_backend_is_a_failure_not_a_crash(monkeypatch) -> None:
    def boom():
        raise RuntimeError("unsupported AIOS_APPROVED_EXECUTION_BACKEND: x")

    monkeypatch.setattr(executor, "validate_approved_execution_backend", boom)
    ok, message = doctor._approved_execution_probe()
    assert ok is False and "misconfigured" in message


def test_doctor_report_uses_the_backend_answer_by_default(
    tmp_path, monkeypatch
) -> None:
    """No probe injected: the executor check is the backend's verdict, so a
    stopped daemon reads as unavailable even with `docker` on PATH."""
    from aios import config

    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "AUDIT_DB_PATH", tmp_path / "audit.db")
    monkeypatch.setattr(config, "BACKUP_DIR", tmp_path / "data" / "backups")
    warning = "container execution backend unavailable (daemon stopped)"
    monkeypatch.setattr(
        executor, "validate_approved_execution_backend", lambda: warning
    )
    monkeypatch.setattr(executor, "approved_runner_from_config", lambda: object())
    report = doctor.doctor_report(
        profile="development",
        project_roots=(tmp_path,),
        model_runtime_probe=lambda: (True, ("m",)),
    )
    [check] = [c for c in report.checks if c.name == "executor"]
    assert check.message == warning and check.status != "measured"
