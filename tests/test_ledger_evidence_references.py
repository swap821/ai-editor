"""Ledger live-evidence rows must be checkable, not merely look checkable.

Before this, the only test applied to a ``proof_level="live"`` row was
``_LIVE_RECHECKABLE``: a substring search for things like ``https://`` or
``docker-compose``. It never opened the cited artifact, never confirmed the
cited run existed, and never checked that whatever was cited said anything
about the organ claiming it. Fifty-nine rows of prose were load-bearing on the
author's good faith alone.

The cases below are the ones good faith would not have caught.

(Distinct from tests/test_evidence_verification.py, which covers the unrelated
EvidenceAuthority/VerificationAuthority domain objects.)
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from aios.domain.governance.contracts import OrganRecord

REPO_ROOT = Path(__file__).resolve().parents[1]

_spec = importlib.util.spec_from_file_location(
    "verify_organ_twelve_conditions",
    REPO_ROOT / "scripts" / "verify_organ_twelve_conditions.py",
)
v12 = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(v12)

_SHA = "a" * 40
_OTHER_SHA = "b" * 40


def _artifact(root: Path, name: str, *, tip_sha: str, proofs: list[dict]) -> str:
    rel = f"release/phase4/{name}"
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {"schema": "phase4-live-evidence-v1", "tip_sha": tip_sha, "proofs": proofs}
        ),
        encoding="utf-8",
    )
    return rel


def _record(
    description: str, *, organ_id: int = 9, commit_sha: str = _SHA
) -> OrganRecord:
    return OrganRecord(
        organ_id=organ_id,
        name="Test",
        status="green",
        authority_owner="NobodyAuthority",
        live_evidence=[
            {
                "description": description,
                "commit_sha": commit_sha,
                "proof_level": "live",
            }
        ],
    )


def test_evidence_citing_nothing_checkable_is_refused(tmp_path: Path) -> None:
    """A bare URL used to satisfy _LIVE_RECHECKABLE. It proves nothing."""
    record = _record("Verified live at https://example.com, all good.")

    failures, attested = v12._evidence_reference_failures(record, tmp_path, {})

    assert attested == 0
    assert len(failures) == 1
    assert "resolves to nothing checkable" in failures[0][1]


def test_artifact_that_does_not_mention_this_organ_is_refused(tmp_path: Path) -> None:
    """The sharpest case: a real, passing artifact that proves someone else.

    Citing a genuine artifact is not evidence for YOUR organ unless that
    artifact actually carries a proof record for it.
    """
    rel = _artifact(
        tmp_path,
        "live-evidence-aaaaaaaaaaaa.json",
        tip_sha=_SHA,
        proofs=[{"organ_id": 41, "passed": True}],
    )
    record = _record(f"Proven by {rel}", organ_id=9)

    failures, _ = v12._evidence_reference_failures(record, tmp_path, {})

    assert len(failures) == 1
    assert "carries no proof record for organ 9" in failures[0][1]


def test_artifact_from_a_different_commit_is_refused(tmp_path: Path) -> None:
    """A real green artifact generated at another commit.

    This is how a row ends up describing work the named commit never
    contained: the artifact is genuine, the attribution is not.
    """
    rel = _artifact(
        tmp_path,
        "live-evidence-bbbbbbbbbbbb.json",
        tip_sha=_OTHER_SHA,
        proofs=[{"organ_id": 9, "passed": True}],
    )
    record = _record(f"Proven by {rel}", organ_id=9, commit_sha=_SHA)

    failures, _ = v12._evidence_reference_failures(record, tmp_path, {})

    assert len(failures) == 1
    assert "but the evidence claims" in failures[0][1]


def test_artifact_recording_a_failure_is_refused(tmp_path: Path) -> None:
    rel = _artifact(
        tmp_path,
        "live-evidence-cccccccccccc.json",
        tip_sha=_SHA,
        proofs=[{"organ_id": 9, "passed": False}],
    )
    record = _record(f"Proven by {rel}", organ_id=9)

    failures, _ = v12._evidence_reference_failures(record, tmp_path, {})

    assert any("NOT passed" in why for _, why in failures), failures


def test_a_missing_artifact_is_refused(tmp_path: Path) -> None:
    record = _record("Proven by release/phase4/live-evidence-deadbeef.json")

    failures, _ = v12._evidence_reference_failures(record, tmp_path, {})

    assert any("does not exist" in why for _, why in failures), failures


def test_a_matching_artifact_is_accepted(tmp_path: Path) -> None:
    rel = _artifact(
        tmp_path,
        "live-evidence-dddddddddddd.json",
        tip_sha=_SHA,
        proofs=[{"organ_id": 9, "passed": True}],
    )
    record = _record(f"Proven by {rel}", organ_id=9)

    failures, attested = v12._evidence_reference_failures(record, tmp_path, {})

    assert failures == []
    assert attested == 0


def test_operator_attestation_is_accepted_but_counted(tmp_path: Path) -> None:
    """Human-witnessed proof is legitimate, and must be visible as such.

    It cannot be re-derived by a script, so the honest treatment is to accept
    it only when DECLARED, and to report how many rows depend on it, rather
    than let it hide among machine-checkable evidence.
    """
    record = _record("OPERATOR-ATTESTED: browser session at http://localhost:5173")

    failures, attested = v12._evidence_reference_failures(record, tmp_path, {})

    assert failures == []
    assert attested == 1


def test_a_cited_test_node_must_have_passed(tmp_path: Path) -> None:
    record = _record("Proven by tests/test_thing.py::test_it_works")

    unexecuted, _ = v12._evidence_reference_failures(record, tmp_path, {})
    assert any("did not execute" in why for _, why in unexecuted), unexecuted

    wrong_test = {
        "tests/test_thing.py": {
            "passed": 1,
            "failed": 0,
            "passed_names": {"test_other"},
        }
    }
    mismatched, _ = v12._evidence_reference_failures(record, tmp_path, wrong_test)
    assert any("did not run and pass" in why for _, why in mismatched), mismatched

    right_test = {
        "tests/test_thing.py": {
            "passed": 1,
            "failed": 0,
            "passed_names": {"test_it_works"},
        }
    }
    ok, _ = v12._evidence_reference_failures(record, tmp_path, right_test)
    assert ok == []


def test_a_cited_ci_run_is_checked_when_a_verifier_is_supplied(tmp_path: Path) -> None:
    record = _record("See https://github.com/o/r/actions/runs/12345")

    calls: list[tuple[str, str]] = []

    def verifier(run_id: str, expected_sha: str) -> str | None:
        calls.append((run_id, expected_sha))
        return "conclusion is 'failure', not success"

    failures, _ = v12._evidence_reference_failures(
        record, tmp_path, {}, run_verifier=verifier
    )

    assert calls == [("12345", _SHA)]
    assert any("CI run 12345" in why for _, why in failures), failures

    # Without a verifier the row still resolves structurally -- the network
    # check is opt-in, and its absence is reported rather than silently passed.
    no_net, _ = v12._evidence_reference_failures(record, tmp_path, {})
    assert no_net == []
