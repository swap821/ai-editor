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
    authority = ApiTokenAuthority(
        db_path=tmp_path / "rotation.db", clock=lambda: now["value"]
    )

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
    authority = ApiTokenAuthority(
        db_path=tmp_path / "rotation.db", clock=lambda: now["value"]
    )

    first = authority.rotate(grace_period_seconds=30.0, current_env_token="original")
    now["value"] = 1040.0  # past the first rotation's grace period
    second = authority.rotate(grace_period_seconds=60.0, current_env_token="original")

    assert authority.is_valid("original") is False  # already expired, never re-extended
    assert (
        authority.is_valid(first) is True
    )  # now the "previous", within its own window
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


# --------------------------------------------------------------------------- #
# Organ 53 C4 — the rotation row is tamper-evident
# --------------------------------------------------------------------------- #
# This row is not bookkeeping: `current_token_digest` IS the material that
# decides whether a bearer token authenticates against the whole API. It used
# to be a bare UPSERT with no integrity, so anyone able to write the SQLite file
# could install the digest of a token they hold and authenticate as the
# operator, with nothing able to detect it. The rotation route's audit entry
# records only THAT a rotation happened, does not bind the digest, and is
# bypassed entirely by editing the file.


def _tamper_current_digest(db_path, digest: str) -> None:
    """Rewrite the credential material directly, as an attacker with file access would."""
    import sqlite3

    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            "UPDATE api_token_rotation SET current_token_digest = ? WHERE singleton_id = 1",
            (digest,),
        )
        conn.commit()


def test_a_directly_rewritten_digest_does_not_authenticate(tmp_path) -> None:
    """The attack, executed rather than described.

    An attacker who installs the digest of a token they know must not be able
    to authenticate with it. Without the row HMAC this assertion fails: the
    forged digest compares equal and `is_valid` returns True.
    """
    from aios.application.security.api_token_authority import (
        InstallationConfigurationAuthority,
        token_digest,
    )

    db = tmp_path / "rotation.db"
    authority = InstallationConfigurationAuthority(db_path=db)
    authority.rotate(current_env_token="env-token")

    attacker_token = "attacker-chosen-token"
    _tamper_current_digest(db, token_digest(attacker_token))

    assert authority.is_valid(attacker_token) is False, (
        "a token whose digest was written straight into the rotation table "
        "authenticated -- the store is trusting unverified credential material"
    )


def test_a_tampered_row_is_reported_by_the_store_not_silently_accepted(
    tmp_path,
) -> None:
    """The store itself must refuse, so the failure is loud one layer down."""
    import pytest as _pytest

    from aios.application.security.api_token_authority import (
        InstallationConfigurationAuthority,
    )
    from aios.infrastructure.security.api_token_store import (
        ApiTokenRotationTampered,
        ApiTokenStore,
    )

    db = tmp_path / "rotation.db"
    InstallationConfigurationAuthority(db_path=db).rotate(current_env_token="env-token")
    _tamper_current_digest(db, "0" * 64)

    with _pytest.raises(ApiTokenRotationTampered, match="HMAC"):
        ApiTokenStore(db).current()


def test_an_unstamped_legacy_row_is_refused_rather_than_trusted(tmp_path) -> None:
    """Rows written before the column existed carry a NULL tag.

    Treating them as valid would leave every pre-existing deployment exactly as
    forgeable as before, so they are refused -- the same posture organ 42 takes
    for pre-chain journal rows.
    """
    import sqlite3

    import pytest as _pytest

    from aios.application.security.api_token_authority import (
        InstallationConfigurationAuthority,
    )
    from aios.infrastructure.security.api_token_store import (
        ApiTokenRotationTampered,
        ApiTokenStore,
    )

    db = tmp_path / "rotation.db"
    InstallationConfigurationAuthority(db_path=db).rotate(current_env_token="env-token")
    with sqlite3.connect(str(db)) as conn:
        conn.execute("UPDATE api_token_rotation SET row_hmac = NULL")
        conn.commit()

    with _pytest.raises(ApiTokenRotationTampered, match="no integrity tag"):
        ApiTokenStore(db).current()


def test_tampering_removes_access_but_never_grants_it(tmp_path) -> None:
    """The failure posture, pinned.

    Refusing everything on a tampered row would let an attacker lock the
    operator out by corrupting one file. The authority therefore treats an
    unverifiable row as NO rotation state: rotated tokens stop working, and
    `config.API_TOKEN` -- which this authority never gated -- is untouched.
    """
    from aios.application.security.api_token_authority import (
        InstallationConfigurationAuthority,
    )

    db = tmp_path / "rotation.db"
    authority = InstallationConfigurationAuthority(db_path=db)
    issued = authority.rotate(current_env_token="env-token")
    assert authority.is_valid(issued) is True

    _tamper_current_digest(db, "0" * 64)

    assert authority.is_valid(issued) is False
    assert authority.is_retired("env-token") is False, (
        "a corrupted row retired the operator's environment token, which would "
        "turn file tampering into a lockout"
    )
