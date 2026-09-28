#!/usr/bin/env python3
"""Print the PUBLIC learning-signing keys for the seeds in this environment.

Plan Phase 3 (docs/learning/PHASE3_DESIGN.md). The operator generates one 32-byte
seed per source kind in their own terminal and keeps it in their environment
(``AIOS_LEARNING_KEY_LIVE``, ``AIOS_LEARNING_KEY_HARNESS``). This tool derives
the public halves so they can be pinned in
``.aios/state/LEARNING_PUBLIC_KEYS.json``. It never prints, logs or writes a
seed, and it never generates one: a seed an agent generated would be a seed an
agent has seen.

    python tools/learning_keys.py pubkey          # what to pin, as JSON
    python tools/learning_keys.py check           # is each kind signable AND pinned?
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from aios.memory.provenance import (  # noqa: E402
    KEY_ENV,
    PUBLIC_KEYS_FILE,
    LearningSigner,
    LearningVerifier,
    Provenance,
    content_digest,
)


def pubkeys() -> dict:
    signer = LearningSigner.from_env()
    return {
        "schema": "learning-public-keys/v1",
        "keys": {kind: [hexkey] for kind, hexkey in signer.public_keys().items()},
    }


def check() -> list[str]:
    """One line per kind: signable here, and verifiable against the pinned file."""
    signer = LearningSigner.from_env()
    verifier = LearningVerifier.from_pinned_file()
    lines = []
    for kind, env_name in KEY_ENV.items():
        if kind not in signer.kinds:
            lines.append(f"{kind:<9} no seed in {env_name}: {kind} rows stay unsigned")
            continue
        probe = Provenance(
            table="probe",
            row_id="0",
            content_sha256=content_digest({"probe": kind}),
            source_kind=kind,
            transition="created",
        )
        verdict = verifier.verify(
            signer.sign(probe), content_sha256=probe.content_sha256, context=kind
        )
        lines.append(
            f"{kind:<9} seed present; "
            + (
                "pinned and verifying"
                if verdict.admitted
                else f"NOT verifiable ({verdict.reason}): pin it in {PUBLIC_KEYS_FILE.name}"
            )
        )
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("command", choices=["pubkey", "check"])
    args = parser.parse_args(argv)
    if args.command == "pubkey":
        print(json.dumps(pubkeys(), indent=2))
        return 0
    for line in check():
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
