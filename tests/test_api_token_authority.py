"""Unit tests for aios.application.security.api_token_authority.ApiTokenAuthority.

Organ 53: API bearer-token rotation with a grace-period overlap
(operator-confirmed design) -- the previous token keeps working for a
bounded window after a new one is issued, so an already-running process
holding the old value is not broken the instant rotation happens.
"""

from __future__ import annotations

from aios.application.security.api_token_authority import (
    ApiTokenAuthority,
    token_digest,
)


def test_construction_writes_no_rotation_state(tmp_path):
    """Constructing an instance may create the (empty) schema, matching
    every other store in this codebase, but must never write a bootstrap
    row -- only an explicit rotate() call should establish real state.
    This is the exact regression this test guards: an earlier draft
    bootstrapped from config.API_TOKEN inside __init__ itself, which meant
    a long-lived cached authority silently latched onto whatever value
    config.API_TOKEN happened to hold at first construction and never
    noticed later changes."""
    authority = ApiTokenAuthority(db_path=tmp_path / "rotation.db")
    assert authority.current_state() is None
    assert authority.is_configured() is False


def test_rotate_returns_a_fresh_valid_token(tmp_path):
    authority = ApiTokenAuthority(db_path=tmp_path / "rotation.db")
    token = authority.rotate()
    assert token
    assert authority.is_valid(token) is True
    assert authority.is_valid("something-else") is False


def test_first_rotation_retires_the_live_env_token_after_grace_period(tmp_path):
    now = {"value": 1000.0}
    authority = ApiTokenAuthority(db_path=tmp_path / "rotation.db", clock=lambda: now["value"])

    new_token = authority.rotate(
        grace_period_seconds=60.0, current_env_token="original-env-token"
    )

    assert authority.is_valid("original-env-token") is True
    assert authority.is_valid(new_token) is True

    now["value"] = 1061.0  # past the 60s grace period
    assert authority.is_valid("original-env-token") is False
    assert authority.is_valid(new_token) is True


def test_second_rotation_retires_the_first_rotated_token_not_the_original_env(tmp_path):
    now = {"value": 1000.0}
    authority = ApiTokenAuthority(db_path=tmp_path / "rotation.db", clock=lambda: now["value"])

    first = authority.rotate(grace_period_seconds=30.0, current_env_token="original")
    now["value"] = 1040.0  # past the first rotation's grace period
    second = authority.rotate(grace_period_seconds=60.0, current_env_token="original")

    assert authority.is_valid("original") is False  # already expired, never re-extended
    assert authority.is_valid(first) is True  # now the "previous", within its own window
    assert authority.is_valid(second) is True

    now["value"] = 1101.0  # past the second rotation's grace period
    assert authority.is_valid(first) is False
    assert authority.is_valid(second) is True


def test_rotate_without_any_prior_state_or_env_token_has_no_previous(tmp_path):
    authority = ApiTokenAuthority(db_path=tmp_path / "rotation.db")
    token = authority.rotate()
    state = authority.current_state()
    assert state is not None
    assert state.previous_token_digest is None
    assert state.previous_expires_at is None
    assert state.current_token_digest == token_digest(token)


def test_is_configured_reflects_env_token_or_durable_state(tmp_path):
    authority = ApiTokenAuthority(db_path=tmp_path / "rotation.db")
    assert authority.is_configured() is False
    assert authority.is_configured(current_env_token="x") is True

    authority.rotate()
    assert authority.is_configured() is True


def test_rotate_rejects_negative_grace_period(tmp_path):
    authority = ApiTokenAuthority(db_path=tmp_path / "rotation.db")
    try:
        authority.rotate(grace_period_seconds=-1.0)
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_durable_state_survives_a_fresh_instance_over_the_same_db(tmp_path):
    """Two separate instances sharing one db file -- like two requests in a
    real process -- must see the same rotation state."""
    db_path = tmp_path / "rotation.db"
    first_instance = ApiTokenAuthority(db_path=db_path)
    token = first_instance.rotate()

    second_instance = ApiTokenAuthority(db_path=db_path)
    assert second_instance.is_valid(token) is True
