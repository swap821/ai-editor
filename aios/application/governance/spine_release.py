"""§VIII spine-release attestation — the approval channel the frozen organs lacked.

Why this exists
---------------
``organ_ledger.FROZEN_SECURITY_ORGAN_IDS`` (organs 1-5, the security spine)
forbade a green claim **unconditionally**. There was no input -- no evidence, no
approval, no artifact -- that could satisfy it. That is why the operator's own
§VIII Approve+Deploy on 2026-07-31 left those organs yellow: the human act was
performed and the code had no way to receive it.

This module is that missing channel. It does not weaken the control; it gives it
an input that only a human can produce.

The property that matters, stated accurately
--------------------------------------------
Signing requires a **private** key supplied through the environment at the moment
of signing, per AGENTS.md §VII ("keys live only in volatile env vars; never on
disk, in logs, or in ``.aios/``"). Verification uses a committed **public** key.
The operator's private key is therefore unreachable from inside the repository,
and no agent can sign *as him*.

THIS DOCSTRING USED TO CLAIM MORE THAN THAT, and the claim was false. It said an
agent with write access "still cannot produce a valid attestation, because the
signing key never exists inside the repository". But an agent does not need HIS
key. It can generate its own pair, overwrite the committed public key, sign with
its own private half, and every verification then passes -- because verification
trusts whatever key the file happens to contain. Nothing pinned that file: not
the release manifest, not CI, and the attestation records no key identity. What
actually stood between this repository and a forged approval was the operator
reading a one-line diff.

That gap was found on 2026-09-13, while rotating the key after the operator lost
the private half of the original.

So the honest statement is narrower, and it is two things rather than one:

1. No agent can sign as the operator, because his private key is not here.
2. An attestation NAMES its signer, inside the signature (``pubkey`` below), so
   swapping the key file without re-signing is a mismatch rather than a silent
   re-pointing of every past approval.
3. An agent that substitutes its OWN key and re-signs cannot do so quietly --
   ``key_continuity_findings`` requires the trusted key to match an append-only
   lineage record, and reports loudly on every run when it does not.

(2) and (3) close different halves. (2) catches a key changed without a new
signature; (3) catches a new signature under a key nobody recorded. Either alone
leaves the other route open, which is why both exist.

(3) is a detection control, not a prevention one. A writer inside a repository
can edit any file in it, including the lineage; pretending otherwise is exactly
the overstatement being corrected here. What it buys is that a substitution must
now forge a rotation EVENT with a stated reason, visible as such in review,
instead of a hexadecimal string changing by one line.

A green frozen organ therefore means: the operator signed for it, under a key
whose lineage is recorded.

What an attestation binds
-------------------------
``{organ_ids, commit_sha, evidence_digest, pubkey}``, signed. Each field closes
an attack:

* ``organ_ids``   -- an approval for organ 1 cannot silently cover organ 4.
* ``commit_sha``  -- an approval given at one commit cannot be replayed at a
  later one whose evidence differs (the ledger additionally requires ancestry).
* ``evidence_digest`` -- a hash over those organs' ``condition_verdicts`` and
  ``live_evidence``. Editing a verdict after signing invalidates the signature,
  so approval covers the evidence that was actually reviewed, not merely the
  organ number.
* ``pubkey`` -- WHO signed. Added 2026-09-13, and the newest of the four
  because it was the one nobody had thought to bind. Without it an attestation
  asserted only that *somebody* signed; the signer was whatever
  ``spine_release_pubkey.txt`` contained at verification time, so replacing that
  file re-pointed every historical approval at a new signer while every signed
  byte stayed identical. Now the claimed signer is inside the signature, and
  ``verify_signature`` refuses when it disagrees with the installed key.

Shallow clones fail CLOSED
--------------------------
The ancestry check is anti-replay: an approval given at one commit must not
authorise a later, different one. ``git merge-base --is-ancestor`` cannot answer
that in a depth-1 clone, and this module treats "cannot verify" as "not
approved" rather than waving it through.

That is the right default for a security control and it has a sharp edge: a
shallow checkout produces exactly the same violation text as an unsigned tree --
"cannot claim green before controlled self-modification approval" -- so a valid
operator signature can look like a missing one. It cost a CI cycle on PR #197.
Any job that verifies organ contracts needs ``fetch-depth: 0``; the workflow's
release-authority and release-strict-gate jobs already did, and backend-tests
now does too.

The honest limit
----------------
This control holds only while the private key stays out of agent reach. If it is
ever pasted into a file, a commit, or ``.env``, an agent with repo write access
can forge attestations and the guarantee collapses silently. No code here can
prevent that; ``scripts/security_scan.py`` carries a pattern for the key name so
CI at least shouts when it leaks.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

#: Artifact the operator produces. Read by the ledger conformance check.
ATTESTATION_RELPATH = Path(".aios") / "state" / "spine_release_attestation.json"

#: Committed alongside the repo. The PRIVATE half must never appear here.
PUBKEY_RELPATH = Path(".aios") / "state" / "spine_release_pubkey.txt"


class SpineReleaseError(RuntimeError):
    """Raised when an attestation cannot be read, parsed or verified."""


@dataclass(frozen=True)
class SpineAttestation:
    """A signed operator approval for a set of frozen organs at one commit."""

    organ_ids: tuple[int, ...]
    commit_sha: str
    evidence_digest: str
    signature: str
    #: The public key this attestation was signed under, inside the signature.
    #:
    #: Without it an attestation said only "somebody signed these organs"; WHO
    #: was whatever `spine_release_pubkey.txt` happened to contain at verify
    #: time. Swapping that file therefore re-pointed every historical approval
    #: at a new signer, silently, because nothing in the signed bytes disagreed.
    #:
    #: Now the attestation names its own signer and the name is covered by the
    #: signature, so the two cannot be separated: changing the key without
    #: re-signing produces a mismatch, and re-signing produces a new signature
    #: that the lineage record then has to account for.
    pubkey: str = ""
    note: str = ""

    def signing_payload(self) -> bytes:
        """The exact bytes that are signed and verified.

        Canonical and sorted so an attestation cannot be made to verify against
        a different reading of the same fields.
        """
        return json.dumps(
            {
                "organ_ids": sorted(self.organ_ids),
                "commit_sha": self.commit_sha,
                "evidence_digest": self.evidence_digest,
                "pubkey": self.pubkey,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")


def evidence_digest(records: Iterable[Any], organ_ids: Sequence[int]) -> str:
    """Hash the reviewed evidence for *organ_ids*.

    Covers ``status``, ``condition_verdicts``, ``live_evidence`` and
    ``known_blockers`` -- everything a reviewer would have looked at. A change to
    any of them after signing must invalidate the approval, because the operator
    approved *that* evidence, not the organ number in the abstract.
    """
    wanted = set(organ_ids)
    material: list[dict[str, Any]] = []
    for record in sorted(records, key=lambda r: int(_attr(r, "organ_id"))):
        organ_id = int(_attr(r=record, name="organ_id"))
        if organ_id not in wanted:
            continue
        material.append(
            {
                "organ_id": organ_id,
                "status": _attr(record, "status"),
                "condition_verdicts": _attr(record, "condition_verdicts", {}),
                "live_evidence": _normalise_evidence(
                    _attr(record, "live_evidence", [])
                ),
                "known_blockers": list(_attr(record, "known_blockers", []) or []),
            }
        )
    if not material:
        raise SpineReleaseError(
            f"no ledger records found for organ ids {sorted(wanted)}"
        )
    blob = json.dumps(material, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _attr(
    record: Any = None, name: str = "", default: Any = None, *, r: Any = None
) -> Any:
    """Read *name* from a dataclass record or a plain dict."""
    target = record if record is not None else r
    if isinstance(target, dict):
        return target.get(name, default)
    return getattr(target, name, default)


def _normalise_evidence(evidence: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in evidence or []:
        if isinstance(item, dict):
            out.append({k: item[k] for k in sorted(item)})
        else:
            out.append({k: getattr(item, k) for k in sorted(vars(item))})
    return out


def load_public_key(root: Path) -> str | None:
    """Return the committed public key, or None when none is installed."""
    path = root / PUBKEY_RELPATH
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8").strip()
    return text or None


def load_attestation(root: Path) -> SpineAttestation | None:
    """Return the operator's attestation artifact, or None when absent.

    Absence is the normal state and must behave exactly as before this module
    existed: frozen organs cannot be green.
    """
    path = root / ATTESTATION_RELPATH
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SpineReleaseError(
            f"spine-release attestation is unreadable: {exc}"
        ) from exc

    missing = [
        key
        for key in ("organ_ids", "commit_sha", "evidence_digest", "signature")
        if not raw.get(key)
    ]
    if missing:
        raise SpineReleaseError(
            f"spine-release attestation is missing required field(s): {', '.join(missing)}"
        )
    if not raw.get("pubkey"):
        # Named separately from the list above so the message can say what to
        # DO. An attestation written before the key was bound into the payload
        # is not corrupt and not forged -- it simply predates the binding, and
        # the only way to add it is another signature.
        raise SpineReleaseError(
            "spine-release attestation names no signing key. It predates the "
            "key being bound into the signed payload, so it cannot state who "
            "signed it and a substituted public key would go unnoticed. "
            "Re-sign: python scripts/spine_release_attest.py sign --organs 1,2,3,4,5"
        )
    return SpineAttestation(
        organ_ids=tuple(int(i) for i in raw["organ_ids"]),
        commit_sha=str(raw["commit_sha"]),
        evidence_digest=str(raw["evidence_digest"]),
        pubkey=str(raw["pubkey"]),
        signature=str(raw["signature"]),
        note=str(raw.get("note", "")),
    )


def verify_signature(attestation: SpineAttestation, public_key_hex: str) -> bool:
    """True when *attestation* was signed by the holder of *public_key_hex*.

    Reuses the same Ed25519 primitives as aios/security/audit_logger.py rather
    than introducing a second crypto path. A malformed key or signature is a
    verification failure, never an exception that a caller might treat as a pass.
    """
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except ImportError:  # pragma: no cover - cryptography is a base dependency
        return False

    # THE ATTESTATION MUST NAME THE KEY IT IS BEING CHECKED AGAINST.
    #
    # Verifying the signature alone answers "was this signed by whoever owns the
    # key in the file", which is a different question from "was this signed by
    # the signer this attestation claims". Before the pubkey was bound in, those
    # were indistinguishable, so replacing the file re-pointed every past
    # approval at a new signer without a single signed byte changing.
    #
    # Checked BEFORE the cryptography, because a mismatch here is a statement
    # about identity and should not be reported as a broken signature.
    if (attestation.pubkey or "").strip().lower() != (
        public_key_hex or ""
    ).strip().lower():
        return False

    try:
        key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key_hex))
        key.verify(bytes.fromhex(attestation.signature), attestation.signing_payload())
    except (InvalidSignature, ValueError, TypeError):
        return False
    return True


def approved_organ_ids(
    root: Path,
    records: Sequence[Any],
    *,
    current_sha: str | None,
    is_ancestor: Any = None,
) -> frozenset[int]:
    """Return the frozen organ ids the operator has validly approved for green.

    Returns an empty set -- the safe default -- whenever anything is absent,
    malformed, unsigned, stale or tampered. Every early return below is a
    deliberate fail-closed path.
    """
    public_key = load_public_key(root)
    if not public_key:
        return frozenset()

    try:
        attestation = load_attestation(root)
    except SpineReleaseError:
        return frozenset()
    if attestation is None:
        return frozenset()

    if not verify_signature(attestation, public_key):
        return frozenset()

    # The approval must cover the evidence actually present now, not whatever
    # was there when it was signed.
    try:
        digest_now = evidence_digest(records, attestation.organ_ids)
    except SpineReleaseError:
        return frozenset()
    if digest_now != attestation.evidence_digest:
        return frozenset()

    # An approval given at one commit does not authorise a later, different one.
    # Ancestry (not equality) mirrors require_sha_ancestry: a commit cannot
    # truthfully self-stamp its own SHA.
    if current_sha and attestation.commit_sha != current_sha:
        if is_ancestor is None or not is_ancestor(attestation.commit_sha):
            return frozenset()

    return frozenset(attestation.organ_ids)


#: Append-only record of which public key has been trusted, and when it changed.
KEY_HISTORY_RELPATH = Path(".aios") / "state" / "spine_key_history.jsonl"


def load_key_history(root: Path) -> list[dict[str, Any]]:
    """Every recorded signing key, oldest first. Absent file means no history."""
    path = root / KEY_HISTORY_RELPATH
    if not path.exists():
        return []
    entries: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError as exc:
            raise SpineReleaseError(
                f"spine key history has an unreadable line: {exc}"
            ) from exc
        if isinstance(entry, dict):
            entries.append(entry)
    return entries


def key_continuity_findings(root: Path) -> list[str]:
    """Report when the trusted signing key is not the one last recorded.

    WHY THIS EXISTS, stated against this module's own former claim.

    The docstring above used to say an agent with write access "still cannot
    produce a valid attestation, because the signing key never exists inside the
    repository". That is false as it stood, and losing the operator's key is what
    exposed it: an agent does not need HIS private key. It can generate its own
    pair, overwrite the committed PUBLIC key, sign with its own private half, and
    every verification then passes -- because verification trusts whatever key
    the file happens to contain.

    Nothing pins that file. It is not in the release manifest, no CI step checks
    its value, and the attestation records no key identity. What actually stood
    between the repository and a forged approval was the operator reading a
    one-line diff.

    This does not make substitution impossible -- inside a repository the writer
    can edit anything, and claiming otherwise is how the first overstatement
    happened. It makes substitution LOUD: the trusted key must match the last
    recorded entry, and a change that is not recorded as a rotation is reported
    on every run. An attacker must now also forge a rotation record, which
    appears in the diff as an event with a stated reason rather than as a
    hexadecimal string quietly changing.

    Returns human-readable findings; empty means the key is the recorded one.
    """
    installed = load_public_key(root)
    history = load_key_history(root)

    if installed is None:
        return []  # no key installed: frozen organs cannot be green anyway

    if not history:
        return [
            "SIGNING KEY HAS NO RECORDED LINEAGE: a public key is installed "
            f"({installed[:12]}...) but .aios/state/spine_key_history.jsonl does "
            "not exist, so there is nothing to tell a legitimate key from a "
            "substituted one. Record the current key before trusting it."
        ]

    latest = history[-1]
    recorded = str(latest.get("pubkey") or "")
    if recorded == installed:
        return []

    return [
        "SIGNING KEY CHANGED WITHOUT A RECORDED ROTATION: the installed key is "
        f"{installed[:12]}... but the last recorded key is {recorded[:12]}... "
        "Every attestation verified from here is verified against a key nobody "
        "signed off. If this rotation is legitimate, append it to "
        ".aios/state/spine_key_history.jsonl with the reason; if it is not, the "
        "spine's approvals cannot be trusted and the frozen organs must not be "
        "green."
    ]
