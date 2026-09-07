"""Earned-autonomy ledger: the evidence->GREEN bridge contract.

The load-bearing guarantees: autonomy is granted ONLY by verified-success
evidence, never while the feature is off; a single verified failure revokes it
instantly; signatures are a scope-bound CLASS (not per-file) and never embed a
secret. RED is out of scope here by construction — the bridge only consults
this ledger on YELLOW, and the gateway/executor refuse RED regardless.
"""

from __future__ import annotations

from aios import config
from aios.core.autonomy import UNGOVERNED_FIXTURE, AutonomyLedger
from tests.source_rules import executable_source


def _ledger(tmp_path, min_successes=3):
    # These tests exercise the streak RULE -- promotion, revocation, the flag --
    # not the emergency stop. `is_earned` now REFUSES when no latch is wired
    # (it used to skip the check, which let a stopless ledger grant autonomy
    # with the stop never consulted), so a fixture that wants the rule must say
    # out loud that it is deliberately ungoverned.
    return AutonomyLedger(
        db_path=tmp_path / "mem.db",
        min_successes=min_successes,
        emergency_stop=UNGOVERNED_FIXTURE,
    )


def test_fresh_signature_is_not_earned(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "EARNED_AUTONOMY_ENABLED", True)
    led = _ledger(tmp_path)
    assert not led.is_earned("create_file", "training_ground/foo.py")


def test_earns_only_after_min_consecutive_successes(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "EARNED_AUTONOMY_ENABLED", True)
    led = _ledger(tmp_path, 3)
    led.record_outcome("create_file", "training_ground/foo.py", success=True)
    led.record_outcome("create_file", "training_ground/foo.py", success=True)
    assert not led.is_earned("create_file", "training_ground/foo.py")  # only 2
    rec = led.record_outcome("create_file", "training_ground/foo.py", success=True)
    assert rec["status"] == "earned"
    assert led.is_earned("create_file", "training_ground/foo.py")


def test_disabled_flag_never_grants(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "EARNED_AUTONOMY_ENABLED", True)
    led = _ledger(tmp_path, 2)
    led.record_outcome("create_file", "training_ground/foo.py", success=True)
    led.record_outcome("create_file", "training_ground/foo.py", success=True)
    assert led.is_earned("create_file", "training_ground/foo.py")
    monkeypatch.setattr(config, "EARNED_AUTONOMY_ENABLED", False)
    assert not led.is_earned("create_file", "training_ground/foo.py")


def test_single_failure_revokes_instantly(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "EARNED_AUTONOMY_ENABLED", True)
    led = _ledger(tmp_path, 2)
    led.record_outcome("create_file", "training_ground/foo.py", success=True)
    led.record_outcome("create_file", "training_ground/foo.py", success=True)
    assert led.is_earned("create_file", "training_ground/foo.py")
    rec = led.record_outcome("create_file", "training_ground/foo.py", success=False)
    assert rec["status"] == "revoked"
    assert rec["streak"] == 0
    assert not led.is_earned("create_file", "training_ground/foo.py")


def test_re_earning_requires_a_fresh_streak(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "EARNED_AUTONOMY_ENABLED", True)
    led = _ledger(tmp_path, 2)
    led.record_outcome("create_file", "training_ground/foo.py", success=True)
    led.record_outcome("create_file", "training_ground/foo.py", success=True)
    led.record_outcome("create_file", "training_ground/foo.py", success=False)  # revoke
    led.record_outcome(
        "create_file", "training_ground/foo.py", success=True
    )  # streak 1
    assert not led.is_earned("create_file", "training_ground/foo.py")
    led.record_outcome(
        "create_file", "training_ground/foo.py", success=True
    )  # streak 2
    assert led.is_earned("create_file", "training_ground/foo.py")


def test_signature_is_a_scope_bound_class_not_per_file(tmp_path):
    led = _ledger(tmp_path)
    same_a = led.signature("create_file", "training_ground/foo.py")
    same_b = led.signature("create_file", "training_ground/bar.py")
    other_dir = led.signature("create_file", "other_dir/foo.py")
    other_ext = led.signature("create_file", "training_ground/notes.txt")
    assert same_a == same_b  # same dir + ext = one earned class
    assert same_a != other_dir  # different directory never widens the class
    assert same_a != other_ext  # different extension is a different class


def test_command_signature_strips_values_keeps_shape(tmp_path):
    led = _ledger(tmp_path)
    a = led.signature("verify", "python -m pytest training_ground/foo.py -q")
    b = led.signature("verify", "python -m pytest training_ground/bar.py -q")
    assert a == b  # same verb + path-shape + flags


def test_secret_is_redacted_out_of_the_signature(tmp_path):
    led = _ledger(tmp_path)
    norm = led._normalize(
        "execute_terminal", "deploy --token sk-aaaaaaaaaaaaaaaaaaaaaaaa"
    )
    assert "sk-aaaa" not in norm  # raw secret never enters the shape
    # two different secrets collapse to the same value-stripped shape
    a = led.signature("execute_terminal", "deploy --token sk-aaaaaaaaaaaaaaaaaaaaaaaa")
    b = led.signature("execute_terminal", "deploy --token sk-bbbbbbbbbbbbbbbbbbbbbbbb")
    assert a == b


def test_operator_can_force_revoke(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "EARNED_AUTONOMY_ENABLED", True)
    led = _ledger(tmp_path, 1)
    led.record_outcome("create_file", "training_ground/foo.py", success=True)
    assert led.is_earned("create_file", "training_ground/foo.py")
    sig = led.signature("create_file", "training_ground/foo.py")
    assert led.revoke(sig) is True
    assert not led.is_earned("create_file", "training_ground/foo.py")


def test_ledger_map_is_observable(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "EARNED_AUTONOMY_ENABLED", True)
    led = _ledger(tmp_path, 1)
    led.record_outcome("create_file", "training_ground/foo.py", success=True)
    led.record_outcome(
        "verify", "python -m pytest training_ground/foo.py -q", success=False
    )
    snapshot = led.ledger_map()
    assert snapshot["enabled"] is True
    assert snapshot["summary"]["earned"] == 1
    assert snapshot["summary"]["revoked"] == 1
    assert len(snapshot["entries"]) == 2


# --------------------------------------------------------------------------- #
# The command path: a missing stop is a refusal
# --------------------------------------------------------------------------- #
#
# FOURTH appearance of one shape. `is_earned` carried
# `if self.emergency_stop is not None:` -- the same guard the WRITE path lost a
# cycle earlier -- and `aios/policy/kernel.py` built bare stopless ledgers as
# fallbacks. So an engaged emergency stop did not deny COMMAND autonomy on a
# kernel that had none injected. Measured 2026-09-07:
#
#     stopless ledger, is_earned("command", ...)  ->  True
#
# It survived the previous fix because the wiring rule that would have caught
# it scanned deps.py only.


def _stop_ledger(tmp_path, stop, successes=1):
    from aios.core.autonomy import AutonomyLedger

    led = AutonomyLedger(
        db_path=tmp_path / "cmd.db", min_successes=successes, emergency_stop=stop
    )
    for _ in range(3):
        led.record_outcome("command", "pytest -q", success=True)
    return led


class _Engaged:
    def assert_operational(self):
        raise RuntimeError("emergency stop engaged")


class _Clear:
    def assert_operational(self):
        return None


class _Unreadable:
    def assert_operational(self):
        raise OSError("database is locked")


def test_a_stopless_ledger_grants_nothing(tmp_path) -> None:
    """THE BAR. This exact call returned True before the fix."""
    assert (
        _stop_ledger(tmp_path, None).is_earned("command", "pytest -q", enabled=True)
        is False
    ), "command autonomy was granted with no emergency stop consulted"


def test_a_wired_clear_stop_still_grants(tmp_path) -> None:
    """The positive case, so the refusals cannot pass vacuously."""
    assert _stop_ledger(tmp_path, _Clear()).is_earned(
        "command", "pytest -q", enabled=True
    )


def test_an_engaged_stop_denies(tmp_path) -> None:
    assert not _stop_ledger(tmp_path, _Engaged()).is_earned(
        "command", "pytest -q", enabled=True
    )


def test_an_unreadable_stop_denies(tmp_path) -> None:
    """An unreadable latch is not evidence that it is clear."""
    assert not _stop_ledger(tmp_path, _Unreadable()).is_earned(
        "command", "pytest -q", enabled=True
    )


def test_a_fixture_may_opt_out_but_must_say_so(tmp_path) -> None:
    from aios.core.autonomy import UNGOVERNED_FIXTURE

    assert _stop_ledger(tmp_path, UNGOVERNED_FIXTURE).is_earned(
        "command", "pytest -q", enabled=True
    )


def test_the_scoped_variant_consults_the_stop_too(tmp_path) -> None:
    """It had NO latch check at all -- not even the optional one.

    `is_earned_scoped` gates an ALLOW_AUTONOMOUS decision in
    `aios/application/autonomy/governed.py`. That subsystem is not wired to
    production today, which is the only reason this was not a live hole; a
    future wiring would have inherited it.
    """
    from aios.core.autonomy import AutonomyLedger

    bare = AutonomyLedger(db_path=tmp_path / "s.db")
    engaged = AutonomyLedger(db_path=tmp_path / "s.db", emergency_stop=_Engaged())

    assert bare.is_earned_scoped("any-signature", enabled=True) is False
    assert engaged.is_earned_scoped("any-signature", enabled=True) is False


def test_the_kernel_fallback_is_wired_not_bare() -> None:
    """`autonomy_ledger or AutonomyLedger()` built a stopless ledger.

    Fixed from both sides on purpose: the ledger refuses when unwired, AND the
    fallback wires one, so neither depends on the other being right.
    """

    from aios.policy import kernel

    # Compare CODE, not prose: the helper's own docstring quotes the old
    # expression to explain what it replaced, and matching that would fail
    # against the very comment documenting the fix. (Made this exact mistake
    # earlier today on a different rule.)
    joiner = chr(10)
    code = joiner.join(
        ln
        for ln in executable_source(kernel).splitlines()
        if not ln.strip().startswith("#")
    )
    body = code.split('"""')
    executable = "".join(body[::2])

    assert "autonomy_ledger or AutonomyLedger()" not in executable, (
        "the kernel builds a bare, stopless autonomy ledger again"
    )
    assert "_default_autonomy_ledger" in executable


def test_one_sentinel_not_three() -> None:
    """Compared by identity, and "ungoverned-fixture" is not auto-interned.

    Three module-level copies of the same literal would compare unequal under
    `is`, so a caller passing another module's copy would miss the opt-out. It
    failed CLOSED (a string has no `assert_operational`), so this was a
    correctness wart rather than a hole -- but identity comparison against
    duplicated literals is a hole waiting for a reordered check.
    """
    from aios.core.autonomy import UNGOVERNED_FIXTURE as canonical
    from aios.core.replay_writes import UNGOVERNED_FIXTURE as reexported

    assert reexported is canonical
