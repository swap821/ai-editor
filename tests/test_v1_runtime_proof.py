"""Executable R14 runtime-proof contract tests."""

from __future__ import annotations

from pathlib import Path

from aios.application.governance.runtime_proof import (
    REQUIRED_PROOFS,
    run_runtime_proofs,
)


def test_runtime_proof_runner_exposes_the_complete_r14_matrix(tmp_path: Path) -> None:
    report = run_runtime_proofs(tmp_path)

    assert set(REQUIRED_PROOFS).issubset(report.proofs)
    assert set(REQUIRED_PROOFS) == set(report.proofs)
    assert all(report.proofs[name].evidence for name in REQUIRED_PROOFS)
    assert report.as_dict()["all_passed"] is False
    assert report.proofs["executor_runtime_available"].passed is False


def test_runtime_proof_report_has_boolean_map_and_failures(tmp_path: Path) -> None:
    report = run_runtime_proofs(tmp_path)

    assert set(report.boolean_map()) == set(REQUIRED_PROOFS)
    assert all(isinstance(value, bool) for value in report.boolean_map().values())
    assert report.failures
    assert report.as_dict()["failures"] == list(report.failures)
