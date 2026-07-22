"""Slice 25: Organ Truth Ledger and Release Baseline conformance tests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from aios import launcher
from aios.application.governance.organ_ledger import (
    CANONICAL_ORGANS,
    REQUIRED_ORGAN_COUNT,
    TARGET_ORGAN_IDS,
    load_ledger,
    validate_ledger,
)
from aios.domain.governance.contracts import OrganEvidence, OrganRecord

REPO_ROOT = Path(__file__).resolve().parents[1]
LEDGER_PATH = REPO_ROOT / ".aios" / "state" / "ORGAN_GREEN_LEDGER.json"
MANIFEST_PATH = REPO_ROOT / "release" / "organ-proof-manifest.json"
DOC_PATH = REPO_ROOT / "docs" / "architecture" / "GAGOS_54_ORGANS.md"


def _baseline_records() -> list[OrganRecord]:
    """A minimal, individually-conformant 54-record baseline for fixture tests."""
    return [
        OrganRecord(
            organ_id=organ_id,
            name=name,
            status="yellow",
            authority_owner=owner,
            known_blockers=("placeholder blocker",),
        )
        for organ_id, (name, owner) in sorted(CANONICAL_ORGANS.items())
    ]


def _make_green(record: OrganRecord, **overrides: object) -> OrganRecord:
    payload = {
        "status": "green",
        "known_blockers": (),
        "focused_tests": ("tests/test_x.py",),
        "integration_tests": ("tests/test_y.py",),
    }
    payload.update(overrides)
    return record.model_copy(update=payload)


# --- registry shape -----------------------------------------------------


def test_canonical_registry_has_exactly_54_organs() -> None:
    assert len(CANONICAL_ORGANS) == REQUIRED_ORGAN_COUNT == 54


def test_target_organ_ids_are_exactly_32_and_within_range() -> None:
    assert len(TARGET_ORGAN_IDS) == 32
    assert set(TARGET_ORGAN_IDS) <= set(CANONICAL_ORGANS)


def test_baseline_records_validate_clean() -> None:
    assert validate_ledger(_baseline_records()) == ()


def test_out_of_range_organ_id_is_rejected_at_construction() -> None:
    with pytest.raises(ValidationError):
        OrganRecord(
            organ_id=55,
            name="Not A Real Organ",
            status="yellow",
            authority_owner="NobodyAuthority",
        )


# --- the seven Slice 25 conformance behaviors ----------------------------


def test_duplicate_authority_owner_fails() -> None:
    records = _baseline_records()
    records[1] = records[1].model_copy(
        update={"authority_owner": records[0].authority_owner}
    )
    violations = validate_ledger(records)
    assert any("duplicate authority owner" in v for v in violations)


def test_green_without_tests_fails() -> None:
    records = _baseline_records()
    records[0] = records[0].model_copy(
        update={"status": "green", "known_blockers": ()}
    )
    violations = validate_ledger(records)
    assert any("green without tests" in v for v in violations)


def test_green_without_live_evidence_fails_where_required() -> None:
    records = _baseline_records()
    records[0] = _make_green(records[0], requires_live_evidence=True)
    violations = validate_ledger(records)
    assert any("requires live evidence, but none is present" in v for v in violations)


def test_evidence_from_another_commit_sha_fails() -> None:
    records = _baseline_records()
    records[0] = _make_green(
        records[0],
        requires_live_evidence=True,
        live_evidence=(
            OrganEvidence(
                description="real run at an old tip",
                commit_sha="0" * 40,
                proof_level="live",
            ),
        ),
    )
    violations = validate_ledger(records, current_sha="1" * 40)
    assert any("not the evaluated commit" in v for v in violations)


def test_evidence_from_the_evaluated_commit_sha_passes() -> None:
    records = _baseline_records()
    records[0] = _make_green(
        records[0],
        requires_live_evidence=True,
        live_evidence=(
            OrganEvidence(
                description="real run at the evaluated tip",
                commit_sha="1" * 40,
                proof_level="live",
            ),
        ),
    )
    assert validate_ledger(records, current_sha="1" * 40) == ()


def test_fixture_labelled_evidence_cannot_satisfy_live_gate() -> None:
    records = _baseline_records()
    records[0] = _make_green(
        records[0],
        requires_live_evidence=True,
        live_evidence=(
            OrganEvidence(
                description="synthetic run",
                commit_sha="1" * 40,
                proof_level="fixture",
            ),
        ),
    )
    violations = validate_ledger(records, current_sha="1" * 40)
    assert any(
        "requires live evidence but evidence is labelled" in v for v in violations
    )


def test_missing_organ_fails() -> None:
    records = _baseline_records()[:-1]
    violations = validate_ledger(records)
    assert any("missing organ_id 54" in v for v in violations)


def test_unknown_organ_fails() -> None:
    records = _baseline_records()
    records[0] = records[0].model_copy(update={"name": "Not A Real Organ"})
    violations = validate_ledger(records)
    assert any("unknown organ" in v for v in violations)


# --- the shipped ledger itself -------------------------------------------


def test_shipped_ledger_has_all_54_organs_and_zero_violations() -> None:
    records = load_ledger(LEDGER_PATH)
    assert len(records) == 54
    assert {r.organ_id for r in records} == set(range(1, 55))
    assert validate_ledger(records) == ()


def test_shipped_ledger_32_target_organs_are_yellow_with_blockers_or_genuinely_green() -> None:
    """Every one of the 32 organs the plan targets must be in one of exactly
    two truthful states: yellow with a real blocker describing exactly what
    remains (never an empty blocker that would look like an oversight of a
    finished organ), or green -- and a green claim is only ever trusted
    because `test_shipped_ledger_green_organs_have_tests_and_no_blockers`
    (below) independently verifies it carries real tests and no blockers.
    This intentionally does not assert every target organ stays yellow
    forever: as of the Tier-1 closure pass, organs 29 and 35 are genuinely
    green (see `.aios/state/RESUME.md`), and this test must keep passing as
    more close -- what must never happen is a target organ in any other
    state (missing, or green without tests)."""
    records = {r.organ_id: r for r in load_ledger(LEDGER_PATH)}
    for organ_id in TARGET_ORGAN_IDS:
        record = records[organ_id]
        assert record.status in ("yellow", "green"), (
            f"organ {organ_id} has an unrecognised status {record.status!r}"
        )
        if record.status == "yellow":
            assert record.known_blockers, f"organ {organ_id} has no truthful blocker"


def test_shipped_ledger_green_organs_have_tests_and_no_blockers() -> None:
    for record in load_ledger(LEDGER_PATH):
        if record.status == "green":
            assert record.focused_tests, record.name
            assert record.integration_tests, record.name
            assert not record.known_blockers, record.name


def test_gagos_54_organs_doc_lists_every_authority_owner() -> None:
    doc = DOC_PATH.read_text(encoding="utf-8")
    for organ_id, (_name, owner) in CANONICAL_ORGANS.items():
        assert owner in doc, f"organ {organ_id} owner missing from doc"


def test_organ_proof_manifest_hash_pins_the_ledger() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    ledger_bytes = LEDGER_PATH.read_bytes()
    assert manifest["ledger_sha256"] == hashlib.sha256(ledger_bytes).hexdigest()
    records = load_ledger(LEDGER_PATH)
    expected_summary = {
        "total": len(records),
        "green": sum(1 for r in records if r.status == "green"),
        "yellow": sum(1 for r in records if r.status == "yellow"),
    }
    assert expected_summary["total"] == 54
    assert manifest["organ_summary"] == expected_summary


# --- CLI wiring -----------------------------------------------------------


def test_launcher_organ_check_strict_fails_until_all_organs_green(
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = launcher.LauncherConfig.from_environment(profile="development")
    assert launcher.organ_check(config, strict=True, as_json=True) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["all_green"] is False
    assert payload["yellow_count"] == sum(
        1 for r in load_ledger(LEDGER_PATH) if r.status == "yellow"
    )
    assert payload["conformant"] is True


def test_launcher_organ_check_non_strict_passes_with_truthful_yellow_baseline(
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = launcher.LauncherConfig.from_environment(profile="development")
    assert launcher.organ_check(config, strict=False, as_json=True) == 0
