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

The property that matters
-------------------------
An agent with full write access to this repository can author every line of this
module, the CLI that drives it, and the ledger check that consumes it -- and
still cannot produce a valid attestation, because the signing key never exists
inside the repository. Verification uses a committed **public** key; signing
requires a **private** key supplied through the environment at the moment of
signing, per AGENTS.md §VII ("keys live only in volatile env vars; never on disk,
in logs, or in ``.aios/``").

That asymmetry is the whole design. A green frozen organ therefore means exactly
one thing: the operator personally signed for it.

What an attestation binds
-------------------------
``{organ_ids, commit_sha, evidence_digest}``, signed. Each field closes an
attack:

* ``organ_ids``   -- an approval for organ 1 cannot silently cover organ 4.
* ``commit_sha``  -- an approval given at one commit cannot be replayed at a
  later one whose evidence differs (the ledger additionally requires ancestry).
* ``evidence_digest`` -- a hash over those organs' ``condition_verdicts`` and
  ``live_evidence``. Editing a verdict after signing invalidates the signature,
  so approval covers the evidence that was actually reviewed, not merely the
  organ number.

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
    return SpineAttestation(
        organ_ids=tuple(int(i) for i in raw["organ_ids"]),
        commit_sha=str(raw["commit_sha"]),
        evidence_digest=str(raw["evidence_digest"]),
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
