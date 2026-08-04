#!/usr/bin/env python3
"""Operator-run §VIII signing tool for the frozen security spine (organs 1-5).

This is the human half of `Observe -> Analyse -> Propose -> Test -> Verify ->
Human Review -> Approve -> Deploy` (AGENTS.md §VIII). Everything before *Human
Review* is the agent's; this command is where the operator's own act enters the
system in a form the ledger can verify.

    # once, to create the identity (prints the private key to the terminal ONLY)
    python scripts/spine_release_attest.py keygen

    # each approval, after reviewing the evidence the command prints
    AIOS_SPINE_RELEASE_KEY=<private-hex> python scripts/spine_release_attest.py sign --organs 1,2,3,4,5

Key handling, which is the entire point
---------------------------------------
The private key is read from ``AIOS_SPINE_RELEASE_KEY`` and is never written to
disk, never echoed back after keygen, never logged, and never committed --
AGENTS.md §VII, "keys live only in volatile env vars". Only the PUBLIC key is
written, to ``.aios/state/spine_release_pubkey.txt``, and committed.

An agent with full write access to this repository can rewrite this file, the
verifier, and the ledger check, and still cannot forge an approval, because the
private key does not exist anywhere it can read. That asymmetry is what makes a
green frozen organ mean "the operator personally signed for this".

If the private key is ever pasted into a file, a commit or ``.env``, that
guarantee is gone and no code here can restore it.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from aios.application.governance.organ_ledger import (  # noqa: E402
    FROZEN_SECURITY_ORGAN_IDS,
    load_ledger,
)
from aios.application.governance.spine_release import (  # noqa: E402
    ATTESTATION_RELPATH,
    PUBKEY_RELPATH,
    SpineAttestation,
    evidence_digest,
)

ENV_KEY = "AIOS_SPINE_RELEASE_KEY"


def _head_sha() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip()


def cmd_keygen(_args: argparse.Namespace) -> int:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import (
        Encoding,
        PublicFormat,
        PrivateFormat,
        NoEncryption,
    )

    private = Ed25519PrivateKey.generate()
    private_hex = private.private_bytes(
        Encoding.Raw, PrivateFormat.Raw, NoEncryption()
    ).hex()
    public_hex = private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()

    pub_path = REPO_ROOT / PUBKEY_RELPATH
    pub_path.parent.mkdir(parents=True, exist_ok=True)
    pub_path.write_text(public_hex + "\n", encoding="utf-8")

    print(f"public key written to {PUBKEY_RELPATH.as_posix()} -- commit this file")
    print()
    print("PRIVATE KEY (shown once, never stored by this tool):")
    print()
    print(f"    {private_hex}")
    print()
    print("Put it in a password manager. Do NOT put it in .env, any file in this")
    print("repository, or anywhere an agent can read. If you do, any agent with")
    print("write access can forge approvals and the frozen-spine control is void.")
    return 0


def cmd_sign(args: argparse.Namespace) -> int:
    private_hex = os.environ.get(ENV_KEY, "").strip()
    if not private_hex:
        print(
            f"{ENV_KEY} is not set. Supply the private key in the environment for\n"
            "this one command only, e.g.\n\n"
            f"    {ENV_KEY}=<private-hex> python scripts/spine_release_attest.py sign --organs 1,2,3,4,5\n",
            file=sys.stderr,
        )
        return 2

    organ_ids = tuple(sorted(int(p) for p in args.organs.split(",") if p.strip()))
    unknown = [i for i in organ_ids if i not in FROZEN_SECURITY_ORGAN_IDS]
    if unknown:
        print(
            f"organs {unknown} are not frozen security-spine organs "
            f"{sorted(FROZEN_SECURITY_ORGAN_IDS)}; this tool signs only those",
            file=sys.stderr,
        )
        return 2

    records = load_ledger(REPO_ROOT / ".aios" / "state" / "ORGAN_GREEN_LEDGER.json")
    digest = evidence_digest(records, organ_ids)
    head = _head_sha()

    # Show the operator exactly what they are approving, before they approve it.
    print("You are about to sign a §VIII controlled-release approval for:")
    print()
    for record in sorted(records, key=lambda r: r.organ_id):
        if record.organ_id in organ_ids:
            print(
                f"  organ {record.organ_id:>2}  {record.name}  [status now: {record.status}]"
            )
            for blocker in (record.known_blockers or [])[:2]:
                print(f"           residual: {' '.join(str(blocker).split())[:150]}")
    print()
    print(f"  commit          {head}")
    print(f"  evidence digest {digest}")
    print()
    print("This signature covers that evidence. If any of it changes afterwards,")
    print("the digest changes and the approval stops verifying -- by design.")
    print()

    if not args.yes:
        reply = input("Type the word approve to sign, anything else to abort: ").strip()
        if reply != "approve":
            print("aborted; nothing was written")
            return 1

    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    try:
        private = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(private_hex))
    except ValueError:
        print(
            f"{ENV_KEY} is not a valid hex-encoded Ed25519 private key", file=sys.stderr
        )
        return 2

    attestation = SpineAttestation(
        organ_ids=organ_ids,
        commit_sha=head,
        evidence_digest=digest,
        signature="",
        note=args.note,
    )
    signature = private.sign(attestation.signing_payload()).hex()

    out_path = REPO_ROOT / ATTESTATION_RELPATH
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(
            {
                "organ_ids": list(organ_ids),
                "commit_sha": head,
                "evidence_digest": digest,
                "signature": signature,
                "note": args.note,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"wrote {ATTESTATION_RELPATH.as_posix()}")
    print("Commit it, then run: python scripts/verify_organ_contracts.py")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("keygen", help="create the operator identity (run once)")

    sign = sub.add_parser("sign", help="sign a §VIII release approval")
    sign.add_argument("--organs", default="1,2,3,4,5", help="comma-separated organ ids")
    sign.add_argument(
        "--note", default="", help="free-text note recorded in the artifact"
    )
    sign.add_argument(
        "--yes", action="store_true", help="skip the interactive confirmation"
    )

    args = parser.parse_args(argv)
    if args.command == "keygen":
        return cmd_keygen(args)
    return cmd_sign(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
