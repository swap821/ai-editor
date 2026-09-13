"""The key that verifies the operator's approvals is itself checked.

`spine_release.py` claimed that an agent with full write access "still cannot
produce a valid attestation, because the signing key never exists inside the
repository". That was false, and rotating the key after the operator lost his
private half is what exposed it.

An agent does not need HIS key. It can generate its own pair, overwrite the
committed public key, sign with its own private half, and every verification
passes -- because verification trusts whatever key the file happens to contain.
Nothing pinned that file: not the release manifest, not CI, and the attestation
records no key identity. What stood between this repository and a forged
approval was the operator reading a one-line diff.

THIS IS A DETECTION CONTROL, NOT A PREVENTION ONE, and the distinction is the
point. A writer inside a repository can edit any file in it, including the
lineage record these tests exercise. Claiming otherwise would repeat the exact
overstatement being corrected. What it buys: a substitution must now forge a
rotation EVENT carrying a stated reason, which reads as an event in review,
rather than a hexadecimal string changing by one line.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aios.application.governance.spine_release import (
    KEY_HISTORY_RELPATH,
    PUBKEY_RELPATH,
    SpineReleaseError,
    key_continuity_findings,
    load_key_history,
)

REPO_ROOT = Path(__file__).resolve().parents[1]

KEY_A = "aa" * 32
KEY_B = "bb" * 32


def _plant(root: Path, *, installed: str | None, history: list[dict] | None) -> None:
    (root / PUBKEY_RELPATH).parent.mkdir(parents=True, exist_ok=True)
    if installed is not None:
        (root / PUBKEY_RELPATH).write_text(installed + "\n", encoding="utf-8")
    if history is not None:
        (root / KEY_HISTORY_RELPATH).write_text(
            "".join(json.dumps(e, sort_keys=True) + "\n" for e in history),
            encoding="utf-8",
        )


def test_a_silently_swapped_key_is_caught(tmp_path: Path) -> None:
    """THE BAR. This is the substitution the old docstring said was impossible."""
    _plant(tmp_path, installed=KEY_B, history=[{"pubkey": KEY_A}])

    findings = key_continuity_findings(tmp_path)

    assert findings, "an unrecorded key change was not reported"
    assert "SIGNING KEY CHANGED WITHOUT A RECORDED ROTATION" in findings[0]
    assert KEY_B[:12] in findings[0] and KEY_A[:12] in findings[0]


def test_a_recorded_rotation_is_accepted(tmp_path: Path) -> None:
    """A control that fires on a legitimate rotation would be switched off."""
    _plant(
        tmp_path,
        installed=KEY_B,
        history=[{"pubkey": KEY_A}, {"pubkey": KEY_B, "replaced": KEY_A}],
    )

    assert key_continuity_findings(tmp_path) == []


def test_an_installed_key_with_no_lineage_at_all_is_reported(tmp_path: Path) -> None:
    """Absent history is not innocence.

    Without this, deleting the lineage file would be a way to clear the finding
    -- the cheapest possible bypass, and one that looks like tidying.
    """
    _plant(tmp_path, installed=KEY_A, history=None)

    findings = key_continuity_findings(tmp_path)

    assert findings
    assert "NO RECORDED LINEAGE" in findings[0]


def test_no_installed_key_is_not_a_finding(tmp_path: Path) -> None:
    """The pre-attestation state must behave exactly as before this existed.

    With no key installed the frozen organs cannot be green by any route, so
    there is no approval to protect and nothing to report.
    """
    _plant(tmp_path, installed=None, history=None)

    assert key_continuity_findings(tmp_path) == []


def test_a_corrupt_lineage_refuses_rather_than_reading_past_it(
    tmp_path: Path,
) -> None:
    """Unparseable is not empty. Silently skipping a bad line would let an
    attacker corrupt the record to erase the key it contradicts."""
    _plant(tmp_path, installed=KEY_A, history=[{"pubkey": KEY_A}])
    (tmp_path / KEY_HISTORY_RELPATH).write_text(
        json.dumps({"pubkey": KEY_A}) + "\n{ not json\n", encoding="utf-8"
    )

    with pytest.raises(SpineReleaseError, match="unreadable"):
        load_key_history(tmp_path)


def test_the_shipped_repository_records_its_own_key(tmp_path: Path) -> None:
    """Against the REAL repository, not a fixture.

    The installed key must be the one the lineage ends with. If this fails, the
    key verifying the operator's approvals is not the key anyone recorded.
    """
    del tmp_path

    findings = key_continuity_findings(REPO_ROOT)

    assert findings == [], f"the shipped key does not match its lineage: {findings}"


def test_the_recorded_lineage_is_a_chain(tmp_path: Path) -> None:
    """Each rotation names what it replaced, so the history reads as a chain.

    A list of keys with no links is a list of keys; the `replaced` field is what
    makes an inserted entry visible as an insertion.
    """
    del tmp_path

    history = load_key_history(REPO_ROOT)
    assert history, "the shipped repository has no key lineage"

    for older, newer in zip(history, history[1:]):
        assert newer.get("replaced") == older["pubkey"], (
            f"lineage break: {str(newer.get('pubkey'))[:12]} claims to replace "
            f"{str(newer.get('replaced'))[:12]}, but the previous entry is "
            f"{older['pubkey'][:12]}"
        )
        assert str(newer.get("note") or "").strip(), (
            "a rotation with no stated reason is the thing this record exists to "
            "make impossible to do quietly"
        )


# --------------------------------------------------------------------------- #
# The signer is inside the signature
# --------------------------------------------------------------------------- #
def _keypair():
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()
    return private, public


def _sign(private, pubkey: str):
    from aios.application.governance.spine_release import SpineAttestation

    unsigned = SpineAttestation(
        organ_ids=(1,),
        commit_sha="a" * 40,
        evidence_digest="b" * 64,
        signature="",
        pubkey=pubkey,
    )
    return SpineAttestation(
        organ_ids=unsigned.organ_ids,
        commit_sha=unsigned.commit_sha,
        evidence_digest=unsigned.evidence_digest,
        signature=private.sign(unsigned.signing_payload()).hex(),
        pubkey=pubkey,
    )


def test_an_attestation_verifies_under_the_key_it_names() -> None:
    from aios.application.governance.spine_release import verify_signature

    private, public = _keypair()

    assert verify_signature(_sign(private, public), public) is True


def test_a_swapped_installed_key_no_longer_verifies_a_past_approval() -> None:
    """THE BAR for binding. Before this, swapping the file re-pointed every
    historical approval at a new signer with no signed byte changing."""
    from aios.application.governance.spine_release import verify_signature

    private, public = _keypair()
    _, attacker_public = _keypair()

    attestation = _sign(private, public)

    assert verify_signature(attestation, attacker_public) is False


def test_editing_the_named_key_breaks_the_signature() -> None:
    """The name is covered BY the signature, not merely stored beside it.

    Otherwise an attacker could rewrite `pubkey` to match whatever they
    installed and the mismatch check would pass on a forged pairing.
    """
    from aios.application.governance.spine_release import (
        SpineAttestation,
        verify_signature,
    )

    private, public = _keypair()
    _, attacker_public = _keypair()
    original = _sign(private, public)

    relabelled = SpineAttestation(
        organ_ids=original.organ_ids,
        commit_sha=original.commit_sha,
        evidence_digest=original.evidence_digest,
        signature=original.signature,
        pubkey=attacker_public,
    )

    assert verify_signature(relabelled, attacker_public) is False


def test_an_attestation_naming_no_key_is_refused_with_instructions(
    tmp_path: Path,
) -> None:
    """Attestations written before the binding are not corrupt -- they simply
    cannot say who signed them, and the only cure is another signature."""
    from aios.application.governance.spine_release import (
        ATTESTATION_RELPATH,
        SpineReleaseError,
        load_attestation,
    )

    (tmp_path / ATTESTATION_RELPATH).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / ATTESTATION_RELPATH).write_text(
        json.dumps(
            {
                "organ_ids": [1],
                "commit_sha": "a" * 40,
                "evidence_digest": "b" * 64,
                "signature": "cc",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(SpineReleaseError, match="names no signing key"):
        load_attestation(tmp_path)
