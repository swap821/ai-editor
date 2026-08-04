"""The §VIII approval channel must be unforgeable, or it is theatre.

organ_ledger forbade frozen-organ green unconditionally until 2026-08-04. The
gate now accepts an input -- an Ed25519 attestation the operator signs -- so the
critical question is no longer "does it block?" but "can anything other than the
operator's private key make it pass?".

Every test here is an attack. A suite that only proved the happy path would be
worth nothing: an agent wrote the verifier, so the verifier proving itself
correct on friendly input is not evidence of anything.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aios.application.governance.organ_ledger import (
    FROZEN_SECURITY_ORGAN_IDS,
    load_ledger,
    validate_ledger,
)
from aios.application.governance.spine_release import (
    ATTESTATION_RELPATH,
    PUBKEY_RELPATH,
    SpineAttestation,
    approved_organ_ids,
    evidence_digest,
    load_attestation,
    verify_signature,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
LEDGER_PATH = REPO_ROOT / ".aios" / "state" / "ORGAN_GREEN_LEDGER.json"
SHA = "a" * 40


def _keypair():
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import (
        Encoding,
        PublicFormat,
    )

    private = Ed25519PrivateKey.generate()
    public_hex = private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()
    return private, public_hex


def _records():
    """Real ledger rows, so digests are computed over genuine evidence."""
    return load_ledger(LEDGER_PATH)


def _install(root: Path, public_hex: str | None, payload: dict | None) -> None:
    (root / PUBKEY_RELPATH).parent.mkdir(parents=True, exist_ok=True)
    if public_hex is not None:
        (root / PUBKEY_RELPATH).write_text(public_hex + "\n", encoding="utf-8")
    if payload is not None:
        (root / ATTESTATION_RELPATH).write_text(json.dumps(payload), encoding="utf-8")


def _signed(private, records, organ_ids, *, sha=SHA, digest=None):
    digest = digest if digest is not None else evidence_digest(records, organ_ids)
    unsigned = SpineAttestation(
        organ_ids=tuple(organ_ids), commit_sha=sha, evidence_digest=digest, signature=""
    )
    return {
        "organ_ids": list(organ_ids),
        "commit_sha": sha,
        "evidence_digest": digest,
        "signature": private.sign(unsigned.signing_payload()).hex(),
    }


# --------------------------------------------------------------------------- #
# The default: nothing installed behaves exactly as before this module existed
# --------------------------------------------------------------------------- #


def test_no_attestation_means_frozen_organs_still_cannot_be_green(tmp_path):
    """Regression guard on the pre-2026-08-04 contract."""
    assert approved_organ_ids(tmp_path, _records(), current_sha=SHA) == frozenset()


def test_real_repo_has_no_attestation_so_counts_are_unchanged():
    """Building the channel must not itself move any organ."""
    assert approved_organ_ids(REPO_ROOT, _records(), current_sha=None) == frozenset()


# --------------------------------------------------------------------------- #
# Attacks
# --------------------------------------------------------------------------- #


def test_a_different_key_cannot_forge_an_approval(tmp_path):
    """The central property: only the holder of the committed key may approve.

    An agent can generate keypairs freely. What it cannot do is produce a
    signature that verifies against a public key it does not hold the private
    half of. If this test ever passes an attacker key, the entire mechanism is
    decorative.
    """
    _operator, operator_pub = _keypair()
    attacker, _attacker_pub = _keypair()
    records = _records()

    _install(tmp_path, operator_pub, _signed(attacker, records, [1, 2, 3, 4, 5]))
    assert approved_organ_ids(tmp_path, records, current_sha=SHA) == frozenset()


def test_tampering_with_evidence_after_signing_invalidates_the_approval(tmp_path):
    """Approval covers reviewed evidence, not the organ number in the abstract."""
    operator, operator_pub = _keypair()
    records = _records()
    _install(tmp_path, operator_pub, _signed(operator, records, [1]))
    assert approved_organ_ids(tmp_path, records, current_sha=SHA) == frozenset({1})

    # Now mutate what organ 1 claims, exactly as a later edit would.
    mutated = []
    for record in records:
        if record.organ_id == 1:
            verdicts = dict(record.condition_verdicts)
            verdicts["C9"] = "PASS -- edited after the operator signed"
            record = record.__class__(
                **{**vars(record), "condition_verdicts": verdicts}
            )
        mutated.append(record)

    assert approved_organ_ids(tmp_path, mutated, current_sha=SHA) == frozenset()


def test_an_approval_for_one_organ_does_not_cover_another(tmp_path):
    operator, operator_pub = _keypair()
    records = _records()
    _install(tmp_path, operator_pub, _signed(operator, records, [1]))

    approved = approved_organ_ids(tmp_path, records, current_sha=SHA)
    assert approved == frozenset({1})
    assert 4 not in approved


def test_replay_at_a_later_unrelated_commit_is_refused(tmp_path):
    """A signature given at one commit does not authorise a different one."""
    operator, operator_pub = _keypair()
    records = _records()
    _install(tmp_path, operator_pub, _signed(operator, records, [1], sha=SHA))

    # Different HEAD, and the signed commit is not an ancestor of it.
    assert (
        approved_organ_ids(
            tmp_path, records, current_sha="b" * 40, is_ancestor=lambda _sha: False
        )
        == frozenset()
    )
    # ...but a genuine ancestor is accepted, mirroring require_sha_ancestry.
    assert approved_organ_ids(
        tmp_path, records, current_sha="b" * 40, is_ancestor=lambda _sha: True
    ) == frozenset({1})


def test_editing_the_digest_in_the_artifact_breaks_the_signature(tmp_path):
    operator, operator_pub = _keypair()
    records = _records()
    payload = _signed(operator, records, [1])
    payload["evidence_digest"] = "0" * 64
    _install(tmp_path, operator_pub, payload)
    assert approved_organ_ids(tmp_path, records, current_sha=SHA) == frozenset()


def test_adding_organs_to_a_signed_artifact_breaks_the_signature(tmp_path):
    operator, operator_pub = _keypair()
    records = _records()
    payload = _signed(operator, records, [1])
    payload["organ_ids"] = [1, 2, 3, 4, 5]
    _install(tmp_path, operator_pub, payload)
    assert approved_organ_ids(tmp_path, records, current_sha=SHA) == frozenset()


def test_no_public_key_means_no_approval_however_valid_the_signature(tmp_path):
    operator, _pub = _keypair()
    records = _records()
    _install(tmp_path, None, _signed(operator, records, [1]))
    assert approved_organ_ids(tmp_path, records, current_sha=SHA) == frozenset()


def test_malformed_artifacts_fail_closed(tmp_path):
    _operator, operator_pub = _keypair()
    records = _records()
    _install(tmp_path, operator_pub, None)

    (tmp_path / ATTESTATION_RELPATH).write_text("{not json", encoding="utf-8")
    assert approved_organ_ids(tmp_path, records, current_sha=SHA) == frozenset()

    (tmp_path / ATTESTATION_RELPATH).write_text('{"organ_ids": [1]}', encoding="utf-8")
    with pytest.raises(Exception):
        load_attestation(tmp_path)
    assert approved_organ_ids(tmp_path, records, current_sha=SHA) == frozenset()


def test_garbage_signature_and_key_are_verification_failures_not_crashes():
    att = SpineAttestation(
        organ_ids=(1,), commit_sha=SHA, evidence_digest="x" * 64, signature="zz"
    )
    assert verify_signature(att, "not-hex") is False
    assert verify_signature(att, "ab" * 32) is False


# --------------------------------------------------------------------------- #
# End to end through the real conformance check
# --------------------------------------------------------------------------- #


def test_ledger_violations_still_block_an_unapproved_green_spine(tmp_path):
    """The whole point, exercised through the real entry point.

    A green frozen organ with no valid approval must still be a violation --
    otherwise this change quietly deleted the control it claims to preserve.
    """
    records = []
    for record in _records():
        if record.organ_id in FROZEN_SECURITY_ORGAN_IDS:
            record = record.__class__(**{**vars(record), "status": "green"})
        records.append(record)

    violations = validate_ledger(
        records, repo_root=tmp_path, enforce_owner_attestation=True
    )
    frozen_violations = [
        v for v in violations if "frozen" in v and "cannot claim green" in v
    ]
    assert len(frozen_violations) == len(FROZEN_SECURITY_ORGAN_IDS)
