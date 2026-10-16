"""Plan Phase 9: one derivation of "did this organ's code move since it was
verified?", for both the organ gate and the currency tool.

The gate (`_entrypoint_drift`, C10/C12) walked the log; the currency tool
(`changed_since`) diffed the trees. They disagreed in both directions:

* an entrypoint edited and then reverted was stale to the gate, current to
  the tool -- the file is byte-identical to the one attested;
* evidence gathered on a branch a squash orphaned, whose own edit to an
  entrypoint never reached HEAD, was CURRENT to the gate (no commit between it
  and HEAD touched the file) although HEAD's file is not the file it attested.

Content is the question. These pin the answer on throwaway repositories, and
that the two callers can no longer disagree.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import verify_evidence_currency as currency
from scripts import verify_organ_twelve_conditions as gate


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        [
            "git",
            "-c",
            "user.name=drift-test",
            "-c",
            "user.email=drift@test.invalid",
            "-c",
            "commit.gpgsign=false",
            *args,
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def _commit(root: Path, files: dict[str, str], message: str) -> str:
    for name, text in files.items():
        (root / name).write_text(text, encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "--allow-empty", "-m", message)
    return _git(root, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q", "-b", "main")
    return tmp_path


def _organ(*entrypoints: str) -> SimpleNamespace:
    return SimpleNamespace(production_entrypoints=list(entrypoints))


def _both(repo: Path, sha: str, *entrypoints: str) -> tuple[list[str], list[str]]:
    by_gate = gate._entrypoint_drift(_organ(*entrypoints), repo, sha)
    by_tool = sorted(currency.changed_since(sha, list(entrypoints), "HEAD", root=repo))
    return by_gate, by_tool


def test_an_edit_that_was_reverted_is_not_drift(repo: Path) -> None:
    attested = _commit(repo, {"a.py": "x = 1\n", "b.py": "y = 1\n"}, "attested")
    _commit(repo, {"a.py": "x = 2\n"}, "edit")
    _commit(repo, {"a.py": "x = 1\n"}, "revert")

    assert _both(repo, attested, "a.py", "b.py") == ([], [])


def test_a_real_change_is_drift_and_only_the_changed_file(repo: Path) -> None:
    attested = _commit(repo, {"a.py": "x = 1\n", "b.py": "y = 1\n"}, "attested")
    _commit(repo, {"a.py": "x = 2\n", "unlisted.py": "z = 1\n"}, "change")

    assert _both(repo, attested, "a.py", "b.py") == (["a.py"], ["a.py"])


def test_an_orphaned_branchs_own_edit_is_drift(repo: Path) -> None:
    """The case the log walk missed: the attested commit sits on a branch
    whose edit to a.py never reached HEAD."""
    base = _commit(repo, {"a.py": "x = 1\n"}, "base")
    _git(repo, "checkout", "-q", "-b", "evidence-branch")
    attested = _commit(repo, {"a.py": "x = 'branch only'\n"}, "attested on a branch")
    _git(repo, "checkout", "-q", "main")
    _commit(repo, {"other.py": "w = 1\n"}, "unrelated work on main")
    assert _git(repo, "merge-base", "HEAD", attested) == base

    assert _both(repo, attested, "a.py") == (["a.py"], ["a.py"])


def test_a_squash_of_the_same_content_is_not_drift(repo: Path) -> None:
    """The squash merge case: the branch's commit is orphaned but HEAD holds
    the same bytes, so the evidence still describes HEAD's file."""
    _commit(repo, {"a.py": "x = 1\n"}, "base")
    _git(repo, "checkout", "-q", "-b", "evidence-branch")
    attested = _commit(repo, {"a.py": "x = 2\n"}, "attested on a branch")
    _git(repo, "checkout", "-q", "main")
    _commit(repo, {"a.py": "x = 2\n"}, "squash of the branch")

    assert _both(repo, attested, "a.py") == ([], [])


def test_an_unresolvable_sha_is_drift_never_fresh(repo: Path) -> None:
    _commit(repo, {"a.py": "x = 1\n"}, "base")
    by_gate, by_tool = _both(repo, "0" * 40, "a.py")
    assert by_gate and by_gate[0].startswith("<unresolvable")
    assert by_tool and by_tool[0].startswith("<unresolvable")


def test_no_git_is_drift_never_fresh(repo: Path, monkeypatch) -> None:
    attested = _commit(repo, {"a.py": "x = 1\n"}, "base")

    def _no_git(*_a, **_k):
        raise FileNotFoundError("git")

    monkeypatch.setattr(currency.subprocess, "run", _no_git)
    drift = gate._entrypoint_drift(_organ("a.py"), repo, attested)
    assert drift and drift[0].startswith("<unresolvable")


def test_an_organ_with_no_entrypoints_has_nothing_to_drift(repo: Path) -> None:
    attested = _commit(repo, {"a.py": "x = 1\n"}, "base")
    _commit(repo, {"a.py": "x = 2\n"}, "change")
    assert gate._entrypoint_drift(_organ(), repo, attested) == []
