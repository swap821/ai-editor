"""Verify the Organ Truth Ledger and its release manifest are self-consistent.

This is PR 0's actual enforcement point: it fails the build the moment a
green claim, a manifest hash, or a manifest commit reference drifts from
reality, rather than trusting whoever last hand-edited the JSON. It is
intentionally a thin CLI over `aios.application.governance.organ_ledger`'s
`validate_ledger`/`validate_manifest` -- the rules live there, tested there;
this script just runs them against the real shipped files and reports.

`--strict-release` additionally requires every green organ's
`last_verified_sha`, and the manifest's own `source_commit_sha`, to equal
the exact commit under test -- the Organ 23 / release-tagging gate, not a
rule every ordinary commit's CI should enforce. A commit's SHA is only
known once its own content (including a just-regenerated manifest) is
finalized, so no manifest committed alongside other changes can ever
truthfully name its own commit; `source_commit_sha` names its parent
instead, which the default (non-strict) run only checks is a well-formed
commit sha, not an exact match to whatever HEAD happens to be right now.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
LEDGER_PATH = REPO_ROOT / ".aios" / "state" / "ORGAN_GREEN_LEDGER.json"
MANIFEST_PATH = REPO_ROOT / "release" / "organ-proof-manifest.json"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def main(argv: list[str] | None = None) -> int:
    from aios.application.governance.organ_ledger import (
        current_commit_sha,
        load_ledger,
        validate_ledger,
        validate_manifest,
    )

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--strict-release",
        action="store_true",
        help="Also require every green organ's last_verified_sha == HEAD.",
    )
    args = parser.parse_args(argv)

    current_sha = current_commit_sha(REPO_ROOT)
    records = load_ledger(LEDGER_PATH)
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    violations = list(
        validate_ledger(
            records,
            current_sha=current_sha,
            repo_root=REPO_ROOT,
            strict_last_verified=args.strict_release,
        )
    )
    violations.extend(
        validate_manifest(
            manifest,
            records,
            repo_root=REPO_ROOT,
            current_sha=current_sha,
            strict_source_commit=args.strict_release,
        )
    )

    green = sum(1 for r in records if r.status == "green")
    yellow = sum(1 for r in records if r.status == "yellow")
    print(f"organs: {len(records)} total, {green} green, {yellow} yellow")
    print(f"evaluated at commit: {current_sha!r}")

    if violations:
        print(f"\n{len(violations)} contract violation(s):", file=sys.stderr)
        for violation in violations:
            print(f"  - {violation}", file=sys.stderr)
        return 1

    print("no contract violations -- ledger and manifest are self-consistent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
