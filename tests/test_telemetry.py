"""Unit + integration tests for the Phase-1 lap-counter (aios/core/telemetry.py).

Observation-only, fail-open: a telemetry write failure must never abort the
request that triggered it (see GAGOS_SEASON_ONE_KICKOFF.md Phase 1). Every
test uses an isolated tmp_path database -- never the real memory DB.
"""
from __future__ import annotations

from pathlib import Path

from aios.core import telemetry


def test_record_run_writes_one_correctly_labeled_row(tmp_path: Path) -> None:
    db_path = tmp_path / "telemetry.db"
    telemetry.record_run(
        session_id="s1",
        task_signature="sig-a",
        dispatch_path=telemetry.DISPATCH_PLAYBOOK,
        provider="ollama",
        model="llama3.2:3b",
        verified_outcome=telemetry.OUTCOME_PASS,
        latency_ms=42,
        tokens_in=0,
        tokens_out=0,
        max_zone="GREEN",
        db_path=db_path,
    )
    rows = telemetry.fetch_rows(db_path=db_path)
    assert len(rows) == 1
    assert rows[0]["dispatch_path"] == telemetry.DISPATCH_PLAYBOOK
    assert rows[0]["provider"] == "ollama"
    assert rows[0]["verified_outcome"] == telemetry.OUTCOME_PASS


def test_playbook_replay_and_llm_fallback_each_land_one_row(tmp_path: Path) -> None:
    db_path = tmp_path / "telemetry.db"
    telemetry.record_run(
        session_id="s1", task_signature="sig-a",
        dispatch_path=telemetry.DISPATCH_PLAYBOOK,
        verified_outcome=telemetry.OUTCOME_PASS, db_path=db_path,
    )
    telemetry.record_run(
        session_id="s1", task_signature="sig-b",
        dispatch_path=telemetry.DISPATCH_LLM, provider="ollama",
        verified_outcome=telemetry.OUTCOME_PASS, db_path=db_path,
    )
    rows = telemetry.fetch_rows(db_path=db_path)
    assert len(rows) == 2
    paths = sorted(r["dispatch_path"] for r in rows)
    assert paths == [telemetry.DISPATCH_LLM, telemetry.DISPATCH_PLAYBOOK]


def test_record_run_never_raises_on_a_broken_database(tmp_path: Path) -> None:
    # A directory in place of a database file makes sqlite3.connect fail --
    # this simulates a broken telemetry DB. The caller's request must survive.
    broken_path = tmp_path / "not_a_file"
    broken_path.mkdir()
    telemetry.record_run(
        session_id="s1", task_signature="sig-a",
        dispatch_path=telemetry.DISPATCH_LLM, db_path=broken_path,
    )  # must not raise


def test_record_run_never_raises_on_invalid_dispatch_path(tmp_path: Path) -> None:
    db_path = tmp_path / "telemetry.db"
    telemetry.record_run(
        session_id="s1", task_signature="sig-a",
        dispatch_path="not-a-real-path", db_path=db_path,
    )  # CHECK constraint violation -- must not raise
    assert telemetry.fetch_rows(db_path=db_path) == []


def test_sovereign_hit_rate_counts_non_llm_dispatches() -> None:
    rows = [
        {"dispatch_path": "playbook"},
        {"dispatch_path": "native_plan"},
        {"dispatch_path": "llm"},
        {"dispatch_path": "llm"},
    ]
    assert telemetry.sovereign_hit_rate(rows) == 0.5


def test_sovereign_hit_rate_empty_is_zero() -> None:
    assert telemetry.sovereign_hit_rate([]) == 0.0


def test_verified_success_rate_by_path_ignores_unverified_and_aborted() -> None:
    rows = [
        {"dispatch_path": "playbook", "verified_outcome": "pass"},
        {"dispatch_path": "playbook", "verified_outcome": "fail"},
        {"dispatch_path": "playbook", "verified_outcome": "unverified"},
        {"dispatch_path": "llm", "verified_outcome": "pass"},
        {"dispatch_path": "llm", "verified_outcome": "aborted"},
    ]
    rates = telemetry.verified_success_rate_by_path(rows)
    assert rates["playbook"] == 0.5  # 1 pass / (1 pass + 1 fail); unverified excluded
    assert rates["llm"] == 1.0  # 1 pass / (1 pass); aborted excluded


def test_cost_per_verified_success_excludes_ollama_tokens() -> None:
    rows = [
        {"provider": "ollama", "tokens_in": 100, "tokens_out": 100, "verified_outcome": "pass"},
        {"provider": "gemini", "tokens_in": 50, "tokens_out": 50, "verified_outcome": "pass"},
    ]
    # Only the gemini row's 100 tokens count as cost; 2 verified successes total.
    assert telemetry.cost_per_verified_success(rows) == 50.0


def test_cost_per_verified_success_zero_passes_is_zero() -> None:
    rows = [{"provider": "gemini", "tokens_in": 10, "tokens_out": 10, "verified_outcome": "fail"}]
    assert telemetry.cost_per_verified_success(rows) == 0.0


def test_hit_rate_by_session_preserves_session_order() -> None:
    rows = [
        {"session_id": "s1", "dispatch_path": "llm"},
        {"session_id": "s1", "dispatch_path": "llm"},
        {"session_id": "s2", "dispatch_path": "playbook"},
        {"session_id": "s2", "dispatch_path": "llm"},
    ]
    curve = telemetry.hit_rate_by_session(rows)
    assert curve == [("s1", 0.0), ("s2", 0.5)]
