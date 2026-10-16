"""Plan Phase 8b: the reel's CI gate fails on a structural breach, on a
structural mission not reached, and on one never run -- and never on a
behavioural mission blocked for want of a model."""

from __future__ import annotations

from scripts import learning_reel_gate as gate
from tools.learning_redteam_runner import MISSIONS_BY_KEY

RUNNABLE = sorted(
    k
    for k, m in MISSIONS_BY_KEY.items()
    if m.kind == "structural" and m.blocked_reason is None
)
BEHAVIOURAL = sorted(k for k, m in MISSIONS_BY_KEY.items() if m.kind == "behavioural")


def _report(**outcomes: str) -> dict:
    verdicts = [{"mission": k, "outcome": "held", "reason": "ok"} for k in RUNNABLE]
    verdicts += [
        {"mission": k, "outcome": "blocked", "reason": "no model"} for k in BEHAVIOURAL
    ]
    for v in verdicts:
        if v["mission"] in outcomes:
            v["outcome"] = outcomes[v["mission"]]
    return {"verdicts": verdicts, "counts": {}}


def test_every_structural_mission_held_passes() -> None:
    assert RUNNABLE and BEHAVIOURAL
    assert gate.failures(_report()) == []


def test_a_structural_breach_fails() -> None:
    assert gate.failures(_report(**{RUNNABLE[0]: "breached"}))


def test_a_structural_mission_not_reached_fails() -> None:
    assert gate.failures(_report(**{RUNNABLE[0]: "not_reached"}))


def test_a_mission_never_run_fails() -> None:
    report = _report()
    report["verdicts"] = [v for v in report["verdicts"] if v["mission"] != RUNNABLE[0]]
    assert any("never run" in line for line in gate.failures(report))


def test_a_blocked_behavioural_mission_is_not_gated() -> None:
    assert gate.failures(_report(**{BEHAVIOURAL[0]: "blocked"})) == []


def test_the_cli_exit_codes(tmp_path) -> None:
    import json

    ok = tmp_path / "ok.json"
    ok.write_text(json.dumps(_report()), encoding="utf-8")
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(_report(**{RUNNABLE[0]: "breached"})), encoding="utf-8")
    assert gate.main([str(ok)]) == 0
    assert gate.main([str(bad)]) == 1
