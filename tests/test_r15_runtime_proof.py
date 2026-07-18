"""Executable R15 runtime-proof contract tests."""

from __future__ import annotations

from pathlib import Path

from aios.application.governance.r15_runtime_proof import (
    R15_REQUIRED_PROOFS,
    run_r15_runtime_proofs,
)


def test_r15_runtime_proof_runner_exposes_the_complete_matrix(tmp_path: Path) -> None:
    report = run_r15_runtime_proofs(tmp_path)

    assert set(R15_REQUIRED_PROOFS).issubset(report.proofs)
    assert set(R15_REQUIRED_PROOFS) == set(report.proofs)
    assert all(report.proofs[name].evidence for name in R15_REQUIRED_PROOFS)
    assert report.as_dict()["all_passed"] is True

def test_r15_runtime_proof_report_has_boolean_map_and_failures(tmp_path: Path) -> None:
    report = run_r15_runtime_proofs(tmp_path)

    assert set(report.boolean_map()) == set(R15_REQUIRED_PROOFS)
    assert all(isinstance(value, bool) for value in report.boolean_map().values())
    assert not report.failures
    assert report.as_dict()["failures"] == []
