"""Earned-autonomy ledger: the evidence->GREEN bridge contract.

The load-bearing guarantees: autonomy is granted ONLY by verified-success
evidence, never while the feature is off; a single verified failure revokes it
instantly; signatures are a scope-bound CLASS (not per-file) and never embed a
secret. RED is out of scope here by construction — the bridge only consults
this ledger on YELLOW, and the gateway/executor refuse RED regardless.
"""
from __future__ import annotations

from aios import config
from aios.core.autonomy import AutonomyLedger


def _ledger(tmp_path, min_successes=3):
    return AutonomyLedger(db_path=tmp_path / "mem.db", min_successes=min_successes)


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
    led.record_outcome("create_file", "training_ground/foo.py", success=True)  # streak 1
    assert not led.is_earned("create_file", "training_ground/foo.py")
    led.record_outcome("create_file", "training_ground/foo.py", success=True)  # streak 2
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
    norm = led._normalize("execute_terminal", "deploy --token sk-aaaaaaaaaaaaaaaaaaaaaaaa")
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
    led.record_outcome("verify", "python -m pytest training_ground/foo.py -q", success=False)
    snapshot = led.ledger_map()
    assert snapshot["enabled"] is True
    assert snapshot["summary"]["earned"] == 1
    assert snapshot["summary"]["revoked"] == 1
    assert len(snapshot["entries"]) == 2
