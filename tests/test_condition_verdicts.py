"""Tests for Phase 3 condition_verdicts enforcement."""

from __future__ import annotations

from pathlib import Path

from aios.application.governance.organ_ledger import (
    REQUIRED_CONDITION_VERDICT_KEYS,
    load_ledger,
    validate_ledger,
)
from aios.domain.governance.contracts import OrganRecord

REPO_ROOT = Path(__file__).resolve().parents[1]
LEDGER = REPO_ROOT / ".aios" / "state" / "ORGAN_GREEN_LEDGER.json"


def _complete_verdicts() -> dict[str, str]:
    return {key: f"PASS — fixture verdict for {key}" for key in REQUIRED_CONDITION_VERDICT_KEYS}


def test_shipped_ledger_has_complete_condition_verdicts() -> None:
    records = load_ledger(LEDGER)
    assert len(records) == 54
    for record in records:
        assert set(record.condition_verdicts) >= set(REQUIRED_CONDITION_VERDICT_KEYS)
        for key in REQUIRED_CONDITION_VERDICT_KEYS:
            assert len(str(record.condition_verdicts[key]).strip()) >= 8


def test_validate_ledger_fails_closed_without_condition_verdicts() -> None:
    records = list(load_ledger(LEDGER))
    stripped = records[0].model_copy(update={"condition_verdicts": {}})
    violations = validate_ledger(
        [stripped, *records[1:]],
        enforce_condition_verdicts=True,
    )
    assert any("condition_verdicts" in v and "organ_id 1" in v for v in violations)


def test_validate_ledger_fails_closed_on_short_verdict() -> None:
    records = list(load_ledger(LEDGER))
    bad = dict(records[0].condition_verdicts)
    bad["C3"] = "PASS"
    stripped = records[0].model_copy(update={"condition_verdicts": bad})
    violations = validate_ledger(
        [stripped, *records[1:]],
        enforce_condition_verdicts=True,
    )
    assert any("C3" in v and "too short" in v for v in violations)


def test_organ_record_accepts_condition_verdicts_field() -> None:
    record = OrganRecord(
        organ_id=1,
        name="Security Gateway",
        status="yellow",
        authority_owner="SecurityGatewayAuthority",
        known_blockers=("frozen spine",),
        condition_verdicts=_complete_verdicts(),
    )
    assert record.condition_verdicts["C1"].startswith("PASS")
