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

import argparse
import json
import os
import sys
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


def test_the_repos_own_attestation_is_valid_and_covers_only_the_frozen_spine():
    """The live attestation must verify, and must not reach past organs 1-5.

    This replaces test_real_repo_has_no_attestation_so_counts_are_unchanged,
    which asserted the repo had NO attestation. That was true while the channel
    was unused and became false the moment the operator signed -- the third
    assertion in this feature whose premise was "nobody has used this yet".
    The default-behaviour case it was really protecting is
    test_no_attestation_means_frozen_organs_still_cannot_be_green above, which
    uses a clean tmp_path and is independent of repository state.

    An unsigned checkout is still fine here: absence is asserted to fail closed,
    not to be a violation.
    """
    from aios.application.governance.spine_release import (
        load_attestation,
        load_public_key,
        verify_signature,
    )

    attestation = load_attestation(REPO_ROOT)
    if attestation is None:
        assert (
            approved_organ_ids(REPO_ROOT, _records(), current_sha=None) == frozenset()
        )
        return

    public_key = load_public_key(REPO_ROOT)
    assert public_key, "an attestation exists with no public key to verify it against"
    assert verify_signature(attestation, public_key), (
        "the committed attestation does not verify against the committed public key"
    )
    assert set(attestation.organ_ids) <= set(FROZEN_SECURITY_ORGAN_IDS), (
        "the attestation claims organs outside the frozen security spine: "
        f"{sorted(set(attestation.organ_ids) - set(FROZEN_SECURITY_ORGAN_IDS))}"
    )
    assert approved_organ_ids(REPO_ROOT, _records(), current_sha=None) == frozenset(
        attestation.organ_ids
    )


# --------------------------------------------------------------------------- #
# The legitimate path. This suite had twelve tests attacking the door and none
# opening it, which is how the ordering bug below survived to the point where the
# operator was about to waste a signing ceremony on it.
# --------------------------------------------------------------------------- #


def test_the_legitimate_path_actually_opens_the_door(tmp_path):
    """A real approval, walked end to end, must make the frozen organs green.

    The order matters and is the whole lesson: the ledger is prepared in its
    POST-approval form first (status green, the §VIII blocker discharged), and
    the operator signs over THAT. Signing the pre-approval state produces a
    signature that stops verifying the instant it is acted on, because the digest
    covers `status` -- the very field the approval authorises a change to.
    """
    operator, operator_pub = _keypair()

    final = []
    for record in _records():
        if record.organ_id in FROZEN_SECURITY_ORGAN_IDS:
            record = record.__class__(
                **{**vars(record), "status": "green", "known_blockers": []}
            )
        final.append(record)

    _install(tmp_path, operator_pub, _signed(operator, final, [1, 2, 3, 4, 5]))

    assert approved_organ_ids(tmp_path, final, current_sha=SHA) == frozenset(
        FROZEN_SECURITY_ORGAN_IDS
    )

    violations = validate_ledger(
        final, repo_root=tmp_path, enforce_owner_attestation=True, current_sha=SHA
    )
    frozen = [v for v in violations if "frozen" in v and "cannot claim green" in v]
    assert frozen == [], f"a valid approval still blocked the spine: {frozen}"


def test_signing_the_pre_approval_state_does_not_authorise_green(tmp_path):
    """The bug this suite missed, pinned so it cannot come back as a surprise.

    Sign while the organs are still yellow, then flip them green: the digest no
    longer matches and the approval evaporates. This is correct behaviour -- an
    approval covers a specific state -- but it is a trap for whoever runs the
    ceremony, so it is documented here as a test rather than as folklore.
    """
    operator, operator_pub = _keypair()

    # Build the yellow state explicitly rather than assuming the repo's ledger
    # still has organs 1-5 yellow. It does not, since the operator signed -- and
    # relying on that was what broke this test the first time it ran for real.
    yellow = []
    for record in _records():
        if record.organ_id in FROZEN_SECURITY_ORGAN_IDS:
            record = record.__class__(**{**vars(record), "status": "yellow"})
        yellow.append(record)

    # Signed over the yellow state...
    _install(tmp_path, operator_pub, _signed(operator, yellow, [1, 2, 3, 4, 5]))
    assert approved_organ_ids(tmp_path, yellow, current_sha=SHA) == frozenset(
        FROZEN_SECURITY_ORGAN_IDS
    )

    # ...then acted on: the digest covers `status`, so the approval evaporates.
    flipped = []
    for record in yellow:
        if record.organ_id in FROZEN_SECURITY_ORGAN_IDS:
            record = record.__class__(**{**vars(record), "status": "green"})
        flipped.append(record)

    assert approved_organ_ids(tmp_path, flipped, current_sha=SHA) == frozenset()


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


def test_a_shallow_clone_fails_closed_rather_than_approving(tmp_path):
    """ "Cannot verify ancestry" must mean "not approved", never "allowed".

    This is what a depth-1 checkout looks like to the verifier: git cannot
    answer merge-base --is-ancestor, so is_ancestor reports False. Refusing is
    correct for a security control -- but it produces the SAME violation text as
    an unsigned tree, so a valid signature reads as a missing one. That cost a CI
    cycle on PR #197, and the fix is fetch-depth: 0 on any job that verifies
    organ contracts, not a weakening here.
    """
    operator, operator_pub = _keypair()
    records = _records()
    _install(tmp_path, operator_pub, _signed(operator, records, [1], sha=SHA))

    # Signature valid, digest current, but HEAD differs and git cannot answer.
    assert (
        approved_organ_ids(
            tmp_path, records, current_sha="c" * 40, is_ancestor=lambda _sha: False
        )
        == frozenset()
    )


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
# The signing tool must not be able to leak what it never holds
# --------------------------------------------------------------------------- #


def test_keygen_creates_no_private_key_material():
    """The original keygen printed the private key to stdout.

    In an agent-driven repository that is a leak: whoever runs the command
    captures stdout, and the one secret the whole mechanism depends on lands in
    an agent's context. The fix is not a warning -- it is that the tool no longer
    generates key material at all, so there is nothing to leak.

    Tested behaviourally. A source-grep is the obvious approach and it is wrong
    here: the tool legitimately CONTAINS the text of a key-generation recipe,
    because it prints one for the operator to run elsewhere. What matters is that
    running keygen emits no key and writes nothing.
    """
    import re
    import subprocess

    # Snapshot rather than assert-absent. The first version of this test asserted
    # the pubkey file did not exist afterwards, which silently depended on no key
    # ever being installed -- it broke the moment the operator installed a real
    # one. The property is that keygen CHANGES NOTHING, not that the repo is bare.
    pubkey_path = REPO_ROOT / PUBKEY_RELPATH
    before = pubkey_path.read_bytes() if pubkey_path.exists() else None

    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "spine_release_attest.py"),
            "keygen",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0
    combined = result.stdout + result.stderr

    # An Ed25519 key is 64 hex characters. No such run may appear in the output,
    # whatever else the command says.
    assert not re.search(r"\b[0-9a-fA-F]{64}\b", combined), (
        "keygen emitted something shaped like a key"
    )
    assert "does NOT generate" in result.stdout
    assert "no agent attached" in result.stdout

    # And it must not have written or altered key material as a side effect.
    after = pubkey_path.read_bytes() if pubkey_path.exists() else None
    assert after == before, "keygen touched the public key file"


def test_sign_refuses_when_stdout_is_captured(tmp_path):
    """Non-TTY stdout means the output is being captured -- refuse before signing.

    This is the guard that would have caught the original mistake: an agent
    running `sign` gets a pipe, not a terminal.
    """
    import subprocess

    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "spine_release_attest.py"),
            "sign",
        ],
        cwd=REPO_ROOT,
        capture_output=True,  # <- this is exactly the condition under test
        text=True,
        timeout=60,
        env={**os.environ, "AIOS_SPINE_RELEASE_KEY": "00" * 32},
    )
    assert result.returncode == 2
    assert "not a terminal" in result.stderr
    assert "rotate it" in result.stderr


def test_sign_has_no_yes_flag_to_bypass_the_confirmation():
    """--yes existed in the first version and would have defeated the TTY guard."""
    source = (REPO_ROOT / "scripts" / "spine_release_attest.py").read_text(
        encoding="utf-8"
    )
    assert '"--yes"' not in source


def test_install_pubkey_rejects_anything_that_is_not_a_public_key(
    tmp_path, monkeypatch
):
    """A malformed key would make every signature fail verification.

    That failure reads as "the operator never approved" rather than "the key is
    broken", so it must be caught at install time.
    """
    import scripts.spine_release_attest as tool

    monkeypatch.setattr(tool, "REPO_ROOT", tmp_path)
    for bad in ("not-hex", "ab", "ff" * 64):
        args = argparse.Namespace(key=bad)
        assert tool.cmd_install_pubkey(args) == 2
    assert not (tmp_path / PUBKEY_RELPATH).exists()


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


def test_hash_pinned_state_files_use_lf_so_the_manifest_hash_is_portable():
    """CRLF in a hash-pinned file records a hash that exists only on one machine.

    PR #197 passed every local check and failed CI on all three platforms: the
    ledger was written with Python's default text mode on Windows (CRLF), git
    stores it as LF per .gitattributes, and release/organ-proof-manifest.json
    therefore recorded the hash of bytes that existed nowhere but the author's
    disk. .gitattributes already declared `eol=lf` for exactly this reason --
    the tooling just did not honour it.

    Asserted on the working tree, because that is what the manifest hashes.
    """
    for rel in (
        ".aios/state/ORGAN_GREEN_LEDGER.json",
        ".aios/state/spine_release_attestation.json",
        "release/organ-proof-manifest.json",
    ):
        path = REPO_ROOT / rel
        if not path.exists():
            continue
        raw = path.read_bytes()
        assert b"\r\n" not in raw, (
            f"{rel} contains CRLF. .gitattributes declares eol=lf for it because "
            "its bytes are hash-pinned; a CRLF working tree makes the recorded "
            "hash unreproducible anywhere else."
        )


def test_the_signing_tool_writes_lf():
    """The tool that produced the CRLF attestation must not do it again."""
    source = (REPO_ROOT / "scripts" / "spine_release_attest.py").read_text(
        encoding="utf-8"
    )
    body = source.split('"""', 2)[-1]
    writes = body.count("write_text(")
    newlines = body.count(r'newline="\n"')
    assert writes and newlines >= writes, (
        f"{writes} write_text call(s) but only {newlines} explicit LF newline "
        "argument(s); every write to a hash-pinned path must pin LF explicitly"
    )
