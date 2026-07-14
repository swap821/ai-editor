"""Truthfulness tests for the v1 release declaration."""

from __future__ import annotations

from pathlib import Path

from aios.application.governance import evaluate_release


def test_release_declaration_reports_blocked_executor_and_authority_layers() -> None:
    declaration = evaluate_release(
        Path(__file__).resolve().parents[1],
        profile="production",
        executor_available=False,
    )
    assert declaration.ready is False
    assert {
        "operator_identity",
        "exact_capabilities",
        "executor_runtime_available",
    }.issubset(declaration.failures)
    assert declaration.as_dict()["version"] == "1.0.0-prototype"


def test_release_declaration_can_be_evaluated_for_a_verified_runtime() -> None:
    declaration = evaluate_release(
        Path(__file__).resolve().parents[1],
        profile="production",
        executor_available=True,
    )
    assert declaration.ready is False
    assert "operator_identity" in declaration.failures
    assert "exact_capabilities" in declaration.failures
