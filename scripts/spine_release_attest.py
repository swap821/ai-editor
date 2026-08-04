#!/usr/bin/env python3
"""Operator-run §VIII signing tool for the frozen security spine (organs 1-5).

This is the human half of `Observe -> Analyse -> Propose -> Test -> Verify ->
Human Review -> Approve -> Deploy` (AGENTS.md §VIII). Everything before *Human
Review* is the agent's; this command is where the operator's own act enters the
system in a form the ledger can verify.

    python scripts/spine_release_attest.py keygen           # prints the offline recipe
    python scripts/spine_release_attest.py install-pubkey --key <public-hex>

    # in a terminal NO AGENT IS ATTACHED TO:
    AIOS_SPINE_RELEASE_KEY=<private-hex> python scripts/spine_release_attest.py sign --organs 1,2,3,4,5

Key handling, which is the entire point
---------------------------------------
The private key is read from ``AIOS_SPINE_RELEASE_KEY`` and is never written to
disk, never logged, and never committed -- AGENTS.md §VII, "keys live only in
volatile env vars". Only the PUBLIC key is written, to
``.aios/state/spine_release_pubkey.txt``, and committed.

An agent with full write access to this repository can rewrite this file, the
verifier, and the ledger check, and still cannot forge an approval, because the
private key does not exist anywhere it can read. That asymmetry is what makes a
green frozen organ mean "the operator personally signed for this".

Why keygen no longer generates anything (2026-08-04)
----------------------------------------------------
The first version of this tool generated the keypair and printed the private key
to stdout. That is unsafe in the environment this repository is actually
developed in: an agent asked to "run keygen" captures stdout, and the private key
lands in its context. Piping it through the session's ``!`` escape has the same
result -- that output goes into the conversation too. The footgun was not
theoretical; the tool would have handed away the one secret the whole mechanism
depends on, the first time anyone ran it in an agent session.

So this tool no longer creates private key material at all. It cannot leak what
it never holds. ``keygen`` prints a recipe for the operator to run in a terminal
with no agent attached; ``install-pubkey`` accepts only the PUBLIC half.

``sign`` additionally refuses to run unless stdout is a TTY. Signing is an
inherently interactive human act -- there is no legitimate scripted or CI use --
so a captured, piped or redirected stdout means the command is running somewhere
the private key should never have been passed. That check is a heuristic, not a
guarantee, and it is worth what heuristics are worth: it stops the accident, not
a determined mistake.

If the private key is ever pasted into a file, a commit, ``.env``, or an agent
conversation, the guarantee is gone and no code here can restore it.
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


#: The offline recipe. Deliberately a string printed for the operator to run
#: elsewhere, not code this tool executes -- see the module docstring.
_KEYGEN_RECIPE = (
    'python -c "from cryptography.hazmat.primitives.asymmetric.ed25519 import '
    "Ed25519PrivateKey; from cryptography.hazmat.primitives.serialization import "
    "Encoding,PrivateFormat,PublicFormat,NoEncryption; k=Ed25519PrivateKey.generate(); "
    "print('PRIVATE:',k.private_bytes(Encoding.Raw,PrivateFormat.Raw,NoEncryption()).hex()); "
    "print('PUBLIC :',k.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw).hex())\""
)


def cmd_keygen(_args: argparse.Namespace) -> int:
    """Print the offline recipe. This command creates no key material.

    It used to generate the keypair and print the private half. In an
    agent-driven repository that is a leak: whoever runs the command captures
    stdout. A tool that never holds the secret cannot give it away.
    """
    print("This command does NOT generate a key, on purpose.")
    print()
    print("The private key must never pass through a terminal an agent can read,")
    print("which includes this session and anything run through its `!` escape.")
    print("Generate it yourself, in a plain terminal with no agent attached:")
    print()
    print(f"    {_KEYGEN_RECIPE}")
    print()
    print("Then:")
    print("  PRIVATE -> your password manager. Never into a file in this repo,")
    print("             .env, a commit, or an agent conversation.")
    print("  PUBLIC  -> install it here (safe, it is meant to be committed):")
    print()
    print(
        "    python scripts/spine_release_attest.py install-pubkey --key <public-hex>"
    )
    return 0


def cmd_install_pubkey(args: argparse.Namespace) -> int:
    """Write the PUBLIC key. Safe to run anywhere, including an agent session."""
    key = args.key.strip().lower()

    # Validate before writing: a malformed key would silently make every
    # signature fail verification, which reads as "the operator never approved"
    # rather than as "the key is broken".
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

        Ed25519PublicKey.from_public_bytes(bytes.fromhex(key))
    except (ValueError, TypeError):
        print(
            "that is not a valid hex-encoded Ed25519 public key (expect 64 hex "
            "characters). Nothing was written.",
            file=sys.stderr,
        )
        return 2

    if len(key) != 64:
        print(
            "expected exactly 64 hex characters for an Ed25519 public key",
            file=sys.stderr,
        )
        return 2

    pub_path = REPO_ROOT / PUBKEY_RELPATH
    pub_path.parent.mkdir(parents=True, exist_ok=True)
    pub_path.write_text(key + "\n", encoding="utf-8")
    print(f"public key written to {PUBKEY_RELPATH.as_posix()} -- commit this file")
    print("Signing must still happen in a terminal with no agent attached.")
    return 0


def cmd_sign(args: argparse.Namespace) -> int:
    # Signing is an inherently interactive human act; there is no legitimate
    # scripted or CI use. A non-TTY stdout means the output is being captured,
    # which means this is very likely running inside an agent session -- and the
    # private key was passed on the command line to get here. Refuse before
    # doing anything with it.
    #
    # A heuristic, worth what heuristics are worth: it stops the accident, not a
    # determined mistake. AIOS_SPINE_RELEASE_ALLOW_NONTTY exists solely so the
    # test suite can exercise the rest of this function.
    if not sys.stdout.isatty() and not os.environ.get(
        "AIOS_SPINE_RELEASE_ALLOW_NONTTY"
    ):
        print(
            "refusing to sign: stdout is not a terminal, so this output is being\n"
            "captured. If you are running this through an agent, the private key\n"
            "is already in that agent's context -- rotate it.\n\n"
            "Run this in a plain terminal with no agent attached.",
            file=sys.stderr,
        )
        return 2

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

    # No --yes escape hatch. It existed in the first version and would have
    # defeated the TTY guard above for anyone who reached for it in a script.
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

    sub.add_parser(
        "keygen", help="print the offline key-generation recipe (creates nothing)"
    )

    install = sub.add_parser(
        "install-pubkey", help="write the PUBLIC key (safe to run anywhere)"
    )
    install.add_argument("--key", required=True, help="hex-encoded Ed25519 public key")

    sign = sub.add_parser("sign", help="sign a §VIII release approval")
    sign.add_argument("--organs", default="1,2,3,4,5", help="comma-separated organ ids")
    sign.add_argument(
        "--note", default="", help="free-text note recorded in the artifact"
    )

    args = parser.parse_args(argv)
    if args.command == "keygen":
        return cmd_keygen(args)
    if args.command == "install-pubkey":
        return cmd_install_pubkey(args)
    return cmd_sign(args)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
