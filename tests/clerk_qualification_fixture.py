"""Qualification results for tests, built from the suite's own test ids.

Per-job admission (2026-11-12) reads a result's gates -- every test that
backs no job -- so a stand-in "passed" result must carry them: a result that
never ran the safety tests earns no job. MagicMock registries used to hand the
dispatcher a MagicMock whose ``.passed`` was merely truthy.
"""

from __future__ import annotations

from collections.abc import Iterable

from aios.application.local_workforce.qualification_evidence import (
    TEST_ID_TO_JOB_PROFILE,
)
from aios.domain.local_workforce.qualifier import (
    QualificationResult,
    QualificationTestResult,
    suite_test_ids,
)


def gate_ids() -> tuple[str, ...]:
    return tuple(t for t in suite_test_ids() if t not in TEST_ID_TO_JOB_PROFILE)


def qualification(
    passing: Iterable[str] | None = None, *, failed: Iterable[str] = ()
) -> QualificationResult:
    """Every gate passed, plus *passing* job tests (all of them when None),
    minus *failed*; ``passed`` is true only when nothing failed or is missing."""
    failed = set(failed)
    ran = list(suite_test_ids()) if passing is None else [*gate_ids(), *passing]
    ran = list(dict.fromkeys([*ran, *failed]))
    complete = passing is None and not failed
    return QualificationResult(
        passed=complete,
        schema_validity=1.0,
        identifier_preservation=1.0,
        authority_mutation_attempts=0,
        tool_requests_accepted=0,
        secret_reproduction=0,
        unsupported_claim_rate=0.0,
        timeout_rate=0.0,
        test_results=tuple(
            QualificationTestResult(
                test_id=t,
                status="failed" if t in failed else "passed",
                passed=t not in failed,
                attempts=1,
            )
            for t in ran
        ),
    )


def passed_everything() -> QualificationResult:
    return qualification()
