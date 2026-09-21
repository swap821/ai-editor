"""An evidence row may only cite a commit this branch actually contains.

This repository squash-merges. A squash lands the CONTENT of a branch as one
new commit and discards the branch's own commits, so every sha the branch
produced becomes unreachable from the target the moment it merges. An organ row
that cites one is naming a commit no clone can resolve — the proof may have been
real, but nothing on master can check it, and a proof nobody can check is not
evidence.

WHY THIS IS A TEST AND NOT A LESSON
It has now broken master three times (#345, #347, and again after #349), each
time caught by CI rather than before the push, and each time it verified
perfectly on the machine that created it. That is the whole trap: the developer
machine still holds the source branch, so `git log <sha>..HEAD` resolves and
`_entrypoint_drift` computes a sensible answer. A fresh CI clone has no such
branch, and the same check reads differently.

So the invariant is not "the evidence is current" — the currency rules already
cover that. It is the cheaper, stricter one underneath: **every sha in the
ledger must be an ancestor of HEAD.** That is false on the developer machine in
exactly the same way it is false in CI, which is the point: this is a check that
cannot pass locally and fail remotely.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from aios import config

REPO = Path(config.PROJECT_ROOT)
LEDGER = REPO / ".aios" / "state" / "ORGAN_GREEN_LEDGER.json"


def _rows() -> list[dict]:
    data = json.loads(LEDGER.read_text(encoding="utf-8"))
    return data["organs"] if isinstance(data, dict) else data


def _is_ancestor(sha: str) -> bool:
    return (
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", sha, "HEAD"],
            cwd=REPO,
            capture_output=True,
        ).returncode
        == 0
    )


def _shas(row: dict) -> list[str]:
    out = []
    for entry in row.get("live_evidence") or []:
        sha = str(entry.get("commit_sha") or "").strip()
        if sha:
            out.append(sha)
    last = str(row.get("last_verified_sha") or "").strip()
    if last:
        out.append(last)
    return out


@pytest.fixture(scope="module")
def in_a_git_checkout() -> bool:
    ok = (
        subprocess.run(
            ["git", "rev-parse", "--git-dir"], cwd=REPO, capture_output=True
        ).returncode
        == 0
    )
    if not ok:
        pytest.skip("not a git checkout; reachability is unknowable here")
    return ok


def test_every_green_organ_cites_only_reachable_commits(in_a_git_checkout) -> None:
    """The one that would have caught the squash orphaning before the push."""
    orphaned: dict[str, list[int]] = {}
    for row in _rows():
        if row.get("status") != "green":
            continue
        for sha in _shas(row):
            if not _is_ancestor(sha):
                orphaned.setdefault(sha[:12], []).append(int(row["organ_id"]))
    assert not orphaned, (
        "green organs cite commits this branch does not contain — almost always "
        "a squash merge discarding the branch that produced them. Re-gather at "
        f"the current tip and re-attach: {orphaned}"
    )


def test_the_check_can_actually_fail(in_a_git_checkout) -> None:
    """A reachability check that calls everything reachable proves nothing."""
    assert not _is_ancestor("0" * 40)
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True
    ).stdout.strip()
    assert _is_ancestor(head)


def test_every_green_organ_has_at_least_one_live_evidence_row() -> None:
    """Pruning unreachable rows must not leave a green organ with nothing.

    This is the failure mode of the fix rather than of the bug: a script that
    drops orphaned rows can silently empty one, and an organ asserting green on
    no evidence is worse than one asserting it on stale evidence.
    """
    empty = [
        int(row["organ_id"])
        for row in _rows()
        if row.get("status") == "green" and not (row.get("live_evidence") or [])
    ]
    assert not empty, f"green organs left with no live evidence at all: {empty}"


def test_yellow_organs_may_keep_dated_evidence() -> None:
    """Deliberate asymmetry, stated so nobody 'fixes' it.

    The currency rules bind GREEN organs. A yellow organ carrying old evidence
    plus a blocker explaining why it is stale is the honest state — it is the
    verifier's own prescribed remedy ("record the organ as yellow with the
    reason"). Stripping those rows leaves a yellow organ with no named reason,
    which `verify_organ_contracts` rightly refuses.
    """
    yellow_with_evidence = [
        int(row["organ_id"])
        for row in _rows()
        if row.get("status") == "yellow" and (row.get("live_evidence") or [])
    ]
    assert yellow_with_evidence, (
        "no yellow organ carries evidence any more — if a prune stripped them, "
        "it went one status too far"
    )
