"""A squash merge leaves the tree identical and the citation dangling.

WHY THIS FILE EXISTS. `phase4_attach_ledger.py` already dropped live-evidence
rows that had gone STALE -- rows whose organ's own entrypoints moved after the
evidence was gathered. That rule is `changed_since`, and it is blind to the
other way a row dies.

Measured 2026-09-22, when PR #359 was squash-merged:

    40 branch commits collapsed into one new commit
    every evidence sha the branch produced became unreachable from master
    38 green organs left citing 78cbf1a37822
    0 of them flagged by the currency rule -- because a squash leaves the
      tree BYTE-IDENTICAL, so nothing had drifted

The learning ledger went 8 green -> 0 green on the same merge, for the same
reason. Unverifiable is worse than stale: a stale row is a true claim about an
old commit, an unreachable row is a claim nobody can check at all.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(
        f"_{name}", REPO_ROOT / "scripts" / f"{name}.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_currency = _load("verify_evidence_currency")


def _head() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


class TestTheReachabilityPredicate:
    def test_head_is_reachable_from_itself(self) -> None:
        assert _currency.is_reachable(_head(), _head())

    def test_a_commit_that_does_not_exist_is_not_reachable(self) -> None:
        """The squash case, in the only form a test can pin deterministically:
        a well-formed sha this repository has never contained."""
        assert not _currency.is_reachable("0" * 40, _head())

    def test_an_empty_sha_is_not_reachable(self) -> None:
        """Fail closed. An absent citation is not a satisfied one."""
        assert not _currency.is_reachable("", _head())


class TestDriftCannotSeeIt:
    def test_an_identical_tree_reports_no_drift(self) -> None:
        """The reason the currency rule missed this, stated as a fact.

        `changed_since` asks whether FILES differ. A squash merge produces a
        commit with the same tree, so the honest answer is "nothing moved" --
        which is why reachability has to be asked separately rather than
        folded into the same check.
        """
        head = _head()
        assert _currency.changed_since(head, ["aios/config.py"], head) == []


class TestAttachRefusesABranchTip:
    """Catch it while the choice is still free, not after the merge.

    Dropping unreachable rows fixes the damage. It does not stop it happening,
    and it happened twice in 48 hours -- #359's own tip, then #363's PR head,
    each time turning master red AFTER the merge where it costs the most to
    notice. The refusal belongs at the moment somebody picks which commit to
    attest.
    """

    def _artifact(self, tip: str) -> Path:
        """Written inside the repo because the tool requires that (it records a
        repo-relative artifact path in the ledger)."""
        import json

        real = json.loads(
            (REPO_ROOT / "release/phase4/live-evidence-latest.json").read_text(
                encoding="utf-8"
            )
        )
        real["tip_sha"] = tip
        path = REPO_ROOT / "release/phase4/.branch-tip-guard-test.json"
        path.write_text(json.dumps(real), encoding="utf-8")
        return path

    def test_a_commit_not_on_master_is_refused(self) -> None:
        path = self._artifact("164c7d572fc6" + "0" * 28)
        try:
            result = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "scripts/phase4_attach_ledger.py"),
                    "--artifact",
                    str(path),
                    "--dry-run",
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
            )
        finally:
            path.unlink(missing_ok=True)
        assert result.returncode == 1, "a branch tip was accepted"
        assert "not on master" in result.stderr
        # The refusal has to say WHY, or the next person just deletes the check.
        assert "SQUASH" in result.stderr.upper()

    def test_the_current_master_tip_is_accepted(self) -> None:
        """The negative control. Without it, a guard that refused EVERYTHING
        would pass the test above and nobody could ever attach evidence."""
        head = subprocess.run(
            ["git", "rev-parse", "origin/master"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if head.returncode != 0:
            import pytest

            pytest.skip("no origin/master ref in this clone")
        path = self._artifact(head.stdout.strip())
        try:
            result = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "scripts/phase4_attach_ledger.py"),
                    "--artifact",
                    str(path),
                    "--dry-run",
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
            )
        finally:
            path.unlink(missing_ok=True)
        assert result.returncode == 0, result.stderr[-400:]


class TestEveryCitedCommitIsReachableRightNow:
    """The bar, against the real ledgers rather than a fixture."""

    def test_the_organ_ledger_cites_only_reachable_commits(self) -> None:
        import json

        ledger = json.loads(
            (REPO_ROOT / ".aios/state/ORGAN_GREEN_LEDGER.json").read_text(
                encoding="utf-8"
            )
        )
        head = _head()
        bad = []

        def walk(node):
            if isinstance(node, list):
                for item in node:
                    walk(item)
            elif isinstance(node, dict):
                if node.get("status") == "green":
                    for row in node.get("live_evidence") or []:
                        sha = str(row.get("commit_sha") or "")
                        if sha and not _currency.is_reachable(sha, head):
                            bad.append((node.get("organ_id"), sha[:12]))
                for value in node.values():
                    walk(value)

        walk(ledger)
        assert not bad, f"green organs cite unreachable commits: {bad[:8]}"

    def test_the_learning_ledger_cites_only_reachable_commits(self) -> None:
        """The same question of the animal. It went 0 green / 8 on the merge
        that prompted this file, and nothing in LC1..LC12 noticed until LC10
        was taught to ask."""
        import json

        ledger = json.loads(
            (REPO_ROOT / ".aios/state/LEARNING_LEDGER.json").read_text(encoding="utf-8")
        )
        head = _head()
        bad = []
        for faculty in ledger["faculties"]:
            for row in faculty.get("live_evidence") or []:
                sha = str(row.get("commit_sha") or "")
                if sha and not _currency.is_reachable(sha, head):
                    bad.append((faculty["faculty_id"], sha[:12]))
        assert not bad, f"faculties cite unreachable commits: {bad}"
