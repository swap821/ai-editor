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
    validate_manifest,
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
    records[0] = records[0].model_copy(update={"status": "green", "known_blockers": ()})
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


# --- PR 0: green-contract enforcement rules ------------------------------


def test_green_with_known_blockers_fails() -> None:
    """A green claim that still lists a blocker is a self-contradiction --
    previously this was only checked ad hoc against the shipped ledger, not
    by validate_ledger() itself, so nothing caught it for a caller-supplied
    ledger (e.g. a future CI check on someone else's fork or draft PR)."""
    records = _baseline_records()
    records[0] = _make_green(records[0], known_blockers=("still not wired up",))
    violations = validate_ledger(records)
    assert any("still lists known_blockers" in v for v in violations)


def test_referenced_file_that_does_not_exist_fails_when_repo_root_given() -> None:
    records = _baseline_records()
    records[0] = records[0].model_copy(
        update={"production_entrypoints": ("aios/no/such/file.py",)}
    )
    violations = validate_ledger(records, repo_root=REPO_ROOT)
    assert any(
        "references production_entrypoints path" in v and "does not exist" in v
        for v in violations
    )


def test_referenced_file_that_exists_passes_when_repo_root_given() -> None:
    records = _baseline_records()
    records[0] = records[0].model_copy(
        update={"production_entrypoints": ("tests/test_organ_release_conformance.py",)}
    )
    assert validate_ledger(records, repo_root=REPO_ROOT) == ()


def test_referenced_file_check_is_skipped_without_repo_root() -> None:
    """No filesystem to check against means no fabricated failure -- matches
    current_sha's own established opt-in pattern."""
    records = _baseline_records()
    records[0] = records[0].model_copy(
        update={"production_entrypoints": ("aios/no/such/file.py",)}
    )
    assert validate_ledger(records) == ()


def test_strict_last_verified_rejects_a_stale_or_missing_sha() -> None:
    records = _baseline_records()
    records[0] = _make_green(records[0], last_verified_sha="0" * 40)
    violations = validate_ledger(
        records, current_sha="1" * 40, strict_last_verified=True
    )
    assert any("does not match the evaluated commit" in v for v in violations)


def test_strict_last_verified_passes_when_sha_matches_exactly() -> None:
    records = _baseline_records()
    records[0] = _make_green(records[0], last_verified_sha="1" * 40)
    assert (
        validate_ledger(records, current_sha="1" * 40, strict_last_verified=True) == ()
    )


def test_strict_last_verified_is_off_by_default() -> None:
    """Most commits legitimately don't re-verify every green organ -- this
    is the Organ 23 / release-tagging gate, not every ordinary CI run's."""
    records = _baseline_records()
    records[0] = _make_green(records[0], last_verified_sha=None)
    assert validate_ledger(records, current_sha="1" * 40) == ()


def test_frontend_error_state_organ_without_keyword_coverage_fails(tmp_path) -> None:
    test_file = tmp_path / "test_only_happy_path.py"
    test_file.write_text(
        "def test_renders_data():\n    assert True\n", encoding="utf-8"
    )
    records = _baseline_records()
    records[0] = _make_green(
        records[0],
        requires_frontend_error_states=True,
        focused_tests=(str(test_file.relative_to(tmp_path)),),
        integration_tests=(str(test_file.relative_to(tmp_path)),),
    )
    violations = validate_ledger(records, repo_root=tmp_path)
    assert any("no unavailable/error/stale-state coverage" in v for v in violations)


def test_frontend_error_state_organ_with_keyword_coverage_passes(tmp_path) -> None:
    test_file = tmp_path / "test_error_states.py"
    test_file.write_text(
        "def test_shows_unavailable_when_source_is_unreachable():\n    assert True\n"
        "def test_shows_stale_badge_past_the_freshness_threshold():\n    assert True\n",
        encoding="utf-8",
    )
    records = _baseline_records()
    records[0] = _make_green(
        records[0],
        requires_frontend_error_states=True,
        focused_tests=(str(test_file.relative_to(tmp_path)),),
        integration_tests=(str(test_file.relative_to(tmp_path)),),
    )
    assert validate_ledger(records, repo_root=tmp_path) == ()


def test_frontend_error_state_check_is_skipped_without_repo_root() -> None:
    records = _baseline_records()
    records[0] = _make_green(records[0], requires_frontend_error_states=True)
    assert validate_ledger(records) == ()


# --- PR 0: release-manifest validator -------------------------------------


def _manifest_for(records: list[OrganRecord], *, repo_root: Path) -> dict[str, object]:
    ledger_file = repo_root / ".aios" / "state" / "ledger.json"
    ledger_file.parent.mkdir(parents=True, exist_ok=True)
    ledger_file.write_text(json.dumps([r.as_dict() for r in records]), encoding="utf-8")
    tracked = repo_root / "tracked.txt"
    tracked.write_text("tracked content", encoding="utf-8")
    return {
        "ledger_path": ".aios/state/ledger.json",
        "ledger_sha256": hashlib.sha256(ledger_file.read_bytes()).hexdigest(),
        "organ_summary": {
            "total": len(records),
            "green": sum(1 for r in records if r.status == "green"),
            "yellow": sum(1 for r in records if r.status == "yellow"),
        },
        "source_commit_sha": "1" * 40,
        "files": {"tracked.txt": hashlib.sha256(tracked.read_bytes()).hexdigest()},
    }


def test_validate_manifest_accepts_a_correct_manifest(tmp_path) -> None:
    records = _baseline_records()
    manifest = _manifest_for(records, repo_root=tmp_path)
    assert (
        validate_manifest(manifest, records, repo_root=tmp_path, current_sha="1" * 40)
        == ()
    )


def test_validate_manifest_rejects_stale_source_commit_sha(tmp_path) -> None:
    records = _baseline_records()
    manifest = _manifest_for(records, repo_root=tmp_path)
    violations = validate_manifest(
        manifest, records, repo_root=tmp_path, current_sha="2" * 40
    )
    assert any("does not match the evaluated commit" in v for v in violations)


def test_validate_manifest_rejects_wrong_ledger_hash(tmp_path) -> None:
    records = _baseline_records()
    manifest = _manifest_for(records, repo_root=tmp_path)
    manifest["ledger_sha256"] = "0" * 64
    violations = validate_manifest(manifest, records, repo_root=tmp_path)
    assert any("does not match the actual ledger file hash" in v for v in violations)


def test_validate_manifest_rejects_wrong_organ_summary(tmp_path) -> None:
    records = _baseline_records()
    manifest = _manifest_for(records, repo_root=tmp_path)
    manifest["organ_summary"] = {"total": 54, "green": 999, "yellow": 0}
    violations = validate_manifest(manifest, records, repo_root=tmp_path)
    assert any("organ counts must never be handwritten" in v for v in violations)


def test_validate_manifest_rejects_a_stale_tracked_file_hash(tmp_path) -> None:
    records = _baseline_records()
    manifest = _manifest_for(records, repo_root=tmp_path)
    (tmp_path / "tracked.txt").write_text(
        "changed since the manifest was built", encoding="utf-8"
    )
    violations = validate_manifest(manifest, records, repo_root=tmp_path)
    assert any("is stale" in v for v in violations)


def test_validate_manifest_rejects_a_missing_tracked_file(tmp_path) -> None:
    records = _baseline_records()
    manifest = _manifest_for(records, repo_root=tmp_path)
    (tmp_path / "tracked.txt").unlink()
    violations = validate_manifest(manifest, records, repo_root=tmp_path)
    assert any("references missing file" in v for v in violations)


# --- the shipped ledger itself -------------------------------------------


def test_shipped_ledger_has_all_54_organs_and_zero_violations() -> None:
    records = load_ledger(LEDGER_PATH)
    assert len(records) == 54
    assert {r.organ_id for r in records} == set(range(1, 55))
    assert validate_ledger(records) == ()


def test_shipped_ledger_32_target_organs_are_yellow_with_blockers_or_genuinely_green() -> (
    None
):
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


def test_shipped_manifest_is_a_fully_honest_pin_at_the_evaluated_commit() -> None:
    """Regression test for a real, shipped bug this pass found by hand:
    source_commit_sha pointed at a commit that no longer existed after a
    squash-merge conflict was resolved by rebase, and the `files` hash map
    for both tracked files was stale relative to their actual content --
    validate_ledger()'s own manifest test above only ever checked
    `ledger_sha256`/`organ_summary`, never `source_commit_sha` or `files`,
    so neither drift was ever caught mechanically. validate_manifest() now
    checks all four; this proves the shipped manifest passes every one of
    them against HEAD, not just the two that were already covered."""
    from aios.application.governance.organ_ledger import current_commit_sha

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    records = load_ledger(LEDGER_PATH)
    current_sha = current_commit_sha(REPO_ROOT)
    violations = validate_manifest(
        manifest, records, repo_root=REPO_ROOT, current_sha=current_sha
    )
    assert violations == (), violations


# --- PR 0: the manifest generator + verifier scripts ----------------------


def test_build_release_manifest_check_passes_against_the_shipped_manifest() -> None:
    import subprocess
    import sys

    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "build_release_manifest.py"),
            "--check",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_verify_organ_contracts_passes_on_the_shipped_ledger_and_manifest() -> None:
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "verify_organ_contracts.py")],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "no contract violations" in result.stdout


def test_verify_organ_contracts_strict_release_reports_organs_not_yet_release_grade() -> (
    None
):
    """Documents the real, current state rather than asserting a target:
    every green organ missing last_verified_sha shows up here by name, and
    this test's own job is only to prove the strict flag actually surfaces
    them -- not to require the list be empty (that is Organ 23's job)."""
    import subprocess
    import sys

    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "verify_organ_contracts.py"),
            "--strict-release",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 1
    assert "last_verified_sha" in result.stderr


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
