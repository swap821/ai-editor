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

    gates = {gate.name: gate for gate in declaration.gates}
    isolated_executor = gates["isolated_executor"]
    assert isolated_executor.source_present is True
    assert isolated_executor.runtime_proven is False
    assert isolated_executor.passed is False
    assert isolated_executor.status == "PARTIAL"

    payload_gates = {gate["name"]: gate for gate in declaration.as_dict()["gates"]}
    assert payload_gates["isolated_executor"]["source_present"] is True
    assert payload_gates["isolated_executor"]["runtime_proven"] is False
    assert payload_gates["isolated_executor"]["status"] == "PARTIAL"


def test_release_declaration_can_be_evaluated_for_a_verified_runtime() -> None:
    declaration = evaluate_release(
        Path(__file__).resolve().parents[1],
        profile="production",
        executor_available=True,
    )
    assert declaration.ready is False
    assert "operator_identity" in declaration.failures
    assert "exact_capabilities" in declaration.failures


def test_source_presence_never_counts_as_runtime_proof() -> None:
    declaration = evaluate_release(
        Path(__file__).resolve().parents[1],
        profile="production",
        executor_available=True,
    )
    gates = {gate.name: gate for gate in declaration.gates}

    for name in (
        "isolated_executor",
        "promotion_authority",
        "emergency_stop_controller",
        "turn_coordinator",
    ):
        assert gates[name].source_present is True
        assert gates[name].runtime_proven is False
        assert gates[name].passed is False
        assert gates[name].status == "PARTIAL"


def test_explicit_runtime_proofs_can_verify_a_source_present_gate() -> None:
    declaration = evaluate_release(
        Path(__file__).resolve().parents[1],
        profile="production",
        executor_available=True,
        runtime_proofs={"isolated_executor": True},
    )
    gate = {item.name: item for item in declaration.gates}["isolated_executor"]

    assert gate.source_present is True
    assert gate.runtime_proven is True
    assert gate.passed is True
    assert gate.status == "VERIFIED"
    assert declaration.ready is False
