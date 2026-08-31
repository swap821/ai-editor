#!/usr/bin/env python3
"""Fail any diff that touches the frozen security core without §VIII ceremony.

## Why this exists

`AGENTS.md` §VIII declares `aios/security/` frozen: a change may be *proposed*
for human review, but applying one is RED. Until now that rule had exactly two
enforcers, and neither ran at the merge boundary:

* `ConstitutionEnforcer.check_file_edit` -- in-process, so it only binds an
  agent going through the product's own file-edit path.
* `SelfAnalysisAgent.classify_target` -- in-process, same limitation.

A commit authored any other way -- an agent editing files directly, a human in a
hurry, a future self-improvement loop opening its own PR -- met no automated
resistance at all. Grep of `.github/workflows/` for a frozen-path gate returned
nothing. This is inventory item 5's "automated backstop independent of the
in-process check", and it is the precondition the catalog names for enabling any
self-improvement loop with PR-write access.

## One derivation, two callers

The frozen set is read from `aios.policy.constitution.FROZEN_PATH_PREFIXES` --
the SAME constant `ConstitutionEnforcer._is_frozen` consults at runtime. It is
deliberately not restated here. Two independently-maintained answers to "is this
path frozen?" is the exact shape that produced two containment escapes in this
repo already; a gate that disagrees with the runtime is worse than no gate,
because it certifies the wrong thing.

## What this is, honestly

A **tripwire that forces ceremony**, not an authorization system. The actual
authority is the human who merges the PR. What this guarantees is that a frozen
-core change cannot be quiet: CI goes red, and the only way to green is to add a
§VIII record, in the same diff, naming the exact file. It does not and cannot
stop a determined author from writing that record -- it stops the change from
passing unnoticed, and it leaves an artifact behind either way.

## Usage

    python scripts/check_frozen_core.py --base origin/master

Exit 0 when the diff touches nothing frozen, or when every frozen path it
touches is named by a §VIII record added in the same diff. Exit 1 otherwise.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from aios.policy.constitution import FROZEN_PATH_PREFIXES  # noqa: E402

#: Where a §VIII AUTHORIZATION record must live. Kept as a directory rather than
#: a magic commit-message token so the ceremony leaves a reviewable artifact in
#: the tree, which is what §VIII asks for.
#:
#: This directory means "the operator authorized this change", and nothing else.
#: A PROPOSAL -- the Observe/Analyse/Propose half of §VIII, written before anyone
#: has approved anything -- must NOT live here, or it would authorize itself the
#: moment someone bundled an edit alongside it. Proposals go under the relevant
#: `release/organ-N/` directory instead; see
#: `release/organ-2/2026-08-31-scope-context-proposal.md` and
#: `release/organ-4/2026-08-19-audit-key-trust-proposal.md`.
SECTION_VIII_DIR = "release/section-viii/"


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(
            f"git {' '.join(args)} failed ({result.returncode}): "
            f"{(result.stderr or result.stdout).strip()}"
        )
    return result.stdout


def changed_paths(base: str) -> list[str]:
    """Files changed between the merge base and HEAD, as POSIX repo paths."""
    merge_base = _git("merge-base", base, "HEAD").strip()
    raw = _git("diff", "--name-only", f"{merge_base}...HEAD")
    return [line.strip().replace("\\", "/") for line in raw.splitlines() if line.strip()]


def is_frozen(path: str) -> bool:
    """True when *path* falls under a frozen prefix.

    Prefix comparison mirrors `Constitution.is_frozen_path` -- exact match or a
    `/`-terminated prefix, so `aios/security_notes.py` is NOT caught by the
    `aios/security/` prefix.
    """
    for prefix in FROZEN_PATH_PREFIXES:
        frozen = prefix.rstrip("/")
        if path == frozen or path.startswith(f"{frozen}/"):
            return True
    return False


def authorizations(paths: list[str]) -> dict[str, str]:
    """Map each frozen path to the §VIII record authorizing it, if any.

    The record must be ADDED OR MODIFIED IN THIS DIFF. A record merged months ago
    must not keep authorizing edits forever -- that would turn one approved
    change into a standing permission, which is the opposite of ceremony.
    """
    records = [p for p in paths if p.startswith(SECTION_VIII_DIR) and p.endswith(".md")]
    found: dict[str, str] = {}
    for record in records:
        full = REPO_ROOT / record
        if not full.exists():
            # Deleted in this diff; a removed record authorizes nothing.
            continue
        text = full.read_text(encoding="utf-8", errors="replace")
        for path in paths:
            if is_frozen(path) and path in text:
                found[path] = record
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base",
        default="origin/master",
        help="branch/ref to diff against (default: origin/master)",
    )
    args = parser.parse_args()

    paths = changed_paths(args.base)
    touched = sorted(p for p in paths if is_frozen(p))

    if not touched:
        print(
            f"frozen-core gate: ok — no frozen path touched "
            f"(prefixes: {', '.join(FROZEN_PATH_PREFIXES)})"
        )
        return 0

    authorized = authorizations(paths)
    unauthorized = [p for p in touched if p not in authorized]

    for path in touched:
        record = authorized.get(path)
        marker = f"authorized by {record}" if record else "UNAUTHORIZED"
        print(f"frozen-core gate: {path} — {marker}")

    if not unauthorized:
        print(
            f"frozen-core gate: ok — {len(touched)} frozen path(s) changed, each "
            "named by a §VIII record added in this diff. A human still has to "
            "merge this."
        )
        return 0

    print("", file=sys.stderr)
    print(
        "frozen-core gate: FAILED — this diff edits the frozen security core.",
        file=sys.stderr,
    )
    for path in unauthorized:
        print(f"  - {path}", file=sys.stderr)
    print(
        "\nAGENTS.md §VIII: the security spine is FROZEN. A change may be "
        "PROPOSED for human review; applying one is RED.\n"
        "\nIf this change is a deliberate §VIII action the operator has "
        f"authorized, add a record under {SECTION_VIII_DIR} in THIS diff that "
        "names each path above verbatim, stating what was observed, why the fix "
        "is necessary, and how it was verified.\n"
        "\nDo NOT satisfy this gate by editing the frozen-path list. That list "
        "is read from aios/policy/constitution.py, the same constant the runtime "
        "enforcer uses, precisely so the gate and the product cannot disagree.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
