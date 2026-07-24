"""Regenerate `release/organ-proof-manifest.json` deterministically.

Nothing about this file should ever be hand-edited again: `organ_summary` is
always computed from the ledger (never handwritten), `ledger_sha256` and every
entry in `files` are always the actual sha256 of the file on disk right now,
and `source_commit_sha` is always the exact commit this script ran at. Hand
edits are exactly how the manifest drifted before this script existed --
`source_commit_sha` pointed at a rebased-away commit, and both tracked file
hashes were stale relative to their real content.

Run with `--check` (no writes) in CI to fail the build the moment the
committed manifest stops matching what this script would generate -- the
ledger changed, or a tracked file changed, and nobody regenerated the
manifest afterward.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = REPO_ROOT / "release" / "organ-proof-manifest.json"
LEDGER_PATH = REPO_ROOT / ".aios" / "state" / "ORGAN_GREEN_LEDGER.json"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

#: Always tracked, regardless of what the existing manifest happens to list.
CORE_TRACKED_FILES: tuple[str, ...] = (
    ".aios/state/ORGAN_GREEN_LEDGER.json",
    "docs/architecture/GAGOS_54_ORGANS.md",
)


def _sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _existing_manifest() -> dict[str, object] | None:
    if not MANIFEST_PATH.exists():
        return None
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _tracked_files(existing: dict[str, object] | None) -> tuple[str, ...]:
    """CORE_TRACKED_FILES plus whatever the existing manifest already tracked
    (ad hoc evidence artifacts) that still exist -- additive, never silently
    dropping a previously-tracked file just because this run doesn't know
    to look for it."""
    tracked = list(CORE_TRACKED_FILES)
    if existing is not None:
        for rel_path in existing.get("files", {}) or {}:
            if rel_path not in tracked and (REPO_ROOT / rel_path).exists():
                tracked.append(rel_path)
    return tuple(tracked)


def build_manifest(*, note: str | None = None) -> dict[str, object]:
    from datetime import datetime, timezone

    from aios.application.governance.organ_ledger import (
        current_commit_sha,
        load_ledger,
    )

    records = load_ledger(LEDGER_PATH)
    existing = _existing_manifest()

    organ_summary = {
        "total": len(records),
        "green": sum(1 for r in records if r.status == "green"),
        "yellow": sum(1 for r in records if r.status == "yellow"),
    }
    files = {
        rel_path: _sha256_of(REPO_ROOT / rel_path)
        for rel_path in _tracked_files(existing)
    }
    resolved_note = note if note is not None else str((existing or {}).get("note", ""))

    return {
        "schema_version": str((existing or {}).get("schema_version", "1")),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_commit_sha": current_commit_sha(REPO_ROOT) or "",
        "ledger_path": ".aios/state/ORGAN_GREEN_LEDGER.json",
        "ledger_sha256": _sha256_of(LEDGER_PATH),
        "organ_summary": organ_summary,
        "files": files,
        "note": resolved_note,
    }


def _manifests_equal_ignoring_volatile_fields(
    a: dict[str, object], b: dict[str, object]
) -> bool:
    volatile = {"created_at"}
    return {k: v for k, v in a.items() if k not in volatile} == {
        k: v for k, v in b.items() if k not in volatile
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Do not write; fail if the committed manifest would differ from a fresh build.",
    )
    parser.add_argument(
        "--append-note",
        default=None,
        help="Append this sentence to the manifest's running narrative note.",
    )
    args = parser.parse_args(argv)

    existing = _existing_manifest()
    note = None
    if args.append_note:
        prior = str((existing or {}).get("note", "")).rstrip()
        note = f"{prior} {args.append_note}".strip() if prior else args.append_note

    fresh = build_manifest(note=note)

    if args.check:
        if existing is None:
            print("no existing manifest to check against", file=sys.stderr)
            return 1
        if not _manifests_equal_ignoring_volatile_fields(fresh, existing):
            print(
                "release/organ-proof-manifest.json is stale -- it does not match "
                "what `scripts/build_release_manifest.py` would generate right now. "
                "Run `python scripts/build_release_manifest.py` and commit the result.",
                file=sys.stderr,
            )
            for key in sorted(set(fresh) | set(existing)):
                if key == "created_at":
                    continue
                if fresh.get(key) != existing.get(key):
                    print(f"  field {key!r} differs:", file=sys.stderr)
                    print(f"    expected (fresh): {fresh.get(key)!r}", file=sys.stderr)
                    print(
                        f"    committed        : {existing.get(key)!r}", file=sys.stderr
                    )
            return 1
        print("release/organ-proof-manifest.json is up to date")
        return 0

    MANIFEST_PATH.write_text(
        json.dumps(fresh, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"wrote {MANIFEST_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
