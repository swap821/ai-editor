"""Organ 53: a retirable env token, and a doctor that can see the runtime.

Two gaps this pins:

  * `config.API_TOKEN` was accepted UNCONDITIONALLY, before the rotation
    authority was consulted at all -- a bearer credential that could not be
    revoked without restarting the process, which the plan forbids ("no
    permanent unrevocable bearer credential"). Rotation made it worse, not
    better: an operator who rotated reasonably believed the old credential was
    gone. The mechanism to retire it already existed and was simply bypassed --
    `rotate()` records the live env token as `previous_token_digest` with a
    grace expiry, and the short-circuit meant that expiry never applied to it.

  * `doctor` had NO model-runtime check at all, so it could not report Ollama
    as reachable or not either way. An operator reading a clean report would
    reasonably infer the runtime was fine when nothing had looked.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from aios import config
from aios.application.security.api_token_authority import ApiTokenAuthority
from aios.operations.doctor import doctor_report


class _Clock:
    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now


def _authority(tmp_path: Path, clock: _Clock) -> ApiTokenAuthority:
    return ApiTokenAuthority(db_path=tmp_path / "api_token.db", clock=clock)


# --------------------------------------------------------------------------- #
# The env token is retirable
# --------------------------------------------------------------------------- #


def test_the_env_token_stops_working_once_its_grace_period_elapses(
    tmp_path: Path,
) -> None:
    clock = _Clock()
    authority = _authority(tmp_path, clock)
    env_token = "env-token-value"

    rotated = authority.rotate(grace_period_seconds=600.0, current_env_token=env_token)

    # During the grace window both work -- an already-running client is not
    # broken the instant rotation happens.
    assert authority.is_valid(rotated) is True
    assert authority.is_valid(env_token) is True

    clock.now += 601.0

    assert authority.is_valid(rotated) is True
    assert authority.is_valid(env_token) is False, (
        "the env token must be retirable without a restart"
    )


def test_the_edge_check_defers_to_the_authority_once_a_rotation_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The actual bug: `check_bearer_token` short-circuited on config.API_TOKEN
    BEFORE consulting the authority, so the recorded expiry never applied."""
    from aios.interfaces.http import edge_security

    clock = _Clock()
    authority = _authority(tmp_path, clock)
    env_token = "env-token-value"
    monkeypatch.setattr(config, "API_TOKEN", env_token)
    monkeypatch.setattr(edge_security, "get_api_token_authority", lambda: authority)

    class _Req:
        def __init__(self, token: str) -> None:
            self.headers = {"authorization": f"Bearer {token}"}

    # Before any rotation the env token is the only credential and must work.
    assert edge_security.check_bearer_token(_Req(env_token)) is True

    rotated = authority.rotate(grace_period_seconds=600.0, current_env_token=env_token)
    assert edge_security.check_bearer_token(_Req(rotated)) is True
    assert edge_security.check_bearer_token(_Req(env_token)) is True  # grace

    clock.now += 601.0

    assert edge_security.check_bearer_token(_Req(rotated)) is True
    assert edge_security.check_bearer_token(_Req(env_token)) is False, (
        "config.API_TOKEN must not be a permanent unrevocable credential"
    )


def test_a_fresh_install_is_never_locked_out(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With no rotation ever performed there is nothing else to authenticate
    with, so the env token must still be accepted directly."""
    from aios.interfaces.http import edge_security

    authority = _authority(tmp_path, _Clock())
    monkeypatch.setattr(config, "API_TOKEN", "only-credential")
    monkeypatch.setattr(edge_security, "get_api_token_authority", lambda: authority)

    class _Req:
        def __init__(self, token: str) -> None:
            self.headers = {"authorization": f"Bearer {token}"}

    assert authority.current_state() is None
    assert edge_security.check_bearer_token(_Req("only-credential")) is True
    assert edge_security.check_bearer_token(_Req("wrong")) is False


# --------------------------------------------------------------------------- #
# doctor can see the model runtime
# --------------------------------------------------------------------------- #


def _runtime_check(**kwargs):
    report = doctor_report(**kwargs)
    return next(c for c in report.checks if c.name == "model_runtime")


def test_an_unavailable_runtime_is_never_reported_healthy() -> None:
    check = _runtime_check(model_runtime_probe=lambda: (False, ()))

    assert check.status != "measured"
    assert "unavailable" in check.message


def test_a_reachable_but_empty_runtime_is_degraded_not_healthy() -> None:
    """The engine answered, but there is nothing installed to run. Reporting
    that as healthy would be the same class of lie as reporting it absent."""
    check = _runtime_check(model_runtime_probe=lambda: (True, ()))

    assert check.status != "measured"
    assert "no model is installed" in check.message


def test_a_working_runtime_is_reported_with_its_real_model_count() -> None:
    check = _runtime_check(
        model_runtime_probe=lambda: (True, ("llama3.2:3b", "qwen2.5:7b"))
    )

    assert check.status == "measured"
    assert "2 installed model(s)" in check.message


def test_a_probe_that_raises_is_reported_unavailable_not_swallowed() -> None:
    def _boom() -> tuple[bool, tuple[str, ...]]:
        raise ConnectionError("connection refused")

    check = _runtime_check(model_runtime_probe=_boom)

    assert check.status != "measured"
    assert "connection refused" in check.message
