"""Training on this repo must never BE training on this repo.

`self_corpus` exists so the system can learn from the only corpus on this
machine with a green test suite — itself — without the run being able to touch
the operator's working tree. That makes the isolation the whole product: a
training run that edits the live tree has not produced a weaker result, it has
produced an unusable one, because afterwards there is no way to tell which tree
the evidence came from.

So these tests are adversarial about the isolation and almost indifferent to
the training. Every one of them builds a scratch git repository; none touches
the real one.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from tools.self_corpus import (
    Corpus,
    CorpusError,
    assert_isolated,
    fingerprint,
    provision,
    require_green_baseline,
    run_suite,
    self_corpus,
    teardown,
    training_scope,
)


def _run(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(cwd), *args], capture_output=True, text=True, check=True
    )
    return result.stdout


def test_run_suite_uses_the_active_python_interpreter(tmp_path, monkeypatch) -> None:
    """The isolated suite must use the interpreter that owns its pytest."""
    from tools import self_corpus as self_corpus_module

    corpus = Corpus(
        root=tmp_path / "worktree",
        sha="deadbeef",
        source=tmp_path / "repo",
    )
    corpus.root.mkdir()
    observed: dict[str, object] = {}

    def fake_run(command, **kwargs):
        observed["command"] = command
        observed["kwargs"] = kwargs
        return subprocess.CompletedProcess(
            command,
            0,
            stdout="1 passed in 0.01s\n",
            stderr="",
        )

    monkeypatch.setattr(self_corpus_module.subprocess, "run", fake_run)

    result = run_suite(corpus, ["test_green.py"])

    assert result.green
    assert observed["command"][:3] == [sys.executable, "-m", "pytest"]
    assert observed["kwargs"]["cwd"] == str(corpus.root)


@pytest.fixture()
def repo(tmp_path) -> Path:
    """A scratch repository standing in for the live one."""
    root = tmp_path / "repo"
    root.mkdir()
    _run(root, "init", "-q", "-b", "main")
    _run(root, "config", "user.email", "test@example.invalid")
    _run(root, "config", "user.name", "test")
    (root / "module.py").write_text("VALUE = 1\n", encoding="utf-8")
    _run(root, "add", "-A")
    _run(root, "commit", "-qm", "initial")
    return root


class TestTheDestinationCannotOverlapTheLiveTree:
    def test_the_repo_itself_is_refused(self, repo) -> None:
        with pytest.raises(CorpusError, match="live repository itself"):
            assert_isolated(repo, repo)

    def test_a_destination_inside_the_repo_is_refused(self, repo) -> None:
        with pytest.raises(CorpusError, match="inside the live repository"):
            assert_isolated(repo, repo / "training_copy")

    def test_a_destination_containing_the_repo_is_refused(self, repo) -> None:
        """The same mistake upside down, and just as fatal."""
        with pytest.raises(CorpusError, match="is inside the destination"):
            assert_isolated(repo, repo.parent)

    def test_dotdot_cannot_smuggle_the_repo_back_in(self, repo) -> None:
        """Both sides resolve, because `..` is how this check gets fooled."""
        sneaky = repo / "sub" / ".." / "nested"
        with pytest.raises(CorpusError, match="inside the live repository"):
            assert_isolated(repo, sneaky)

    def test_a_sibling_directory_is_accepted(self, repo) -> None:
        assert_isolated(repo, repo.parent / "training-copy")  # no raise

    def test_a_sibling_whose_name_extends_the_repo_name_is_accepted(self, repo) -> None:
        """Path containment, not substring containment.

        `<repo>-selfcorpus` has `<repo>` as a string prefix, so a naive
        ``str(repo) in str(dest)`` rejects a perfectly isolated destination —
        and its mirror image would accept a nested one whose spelling happened
        not to match. A base/roots mismatch of exactly this shape has already
        been a real containment escape in this repository once.
        """
        assert_isolated(repo, repo.parent / f"{repo.name}-selfcorpus")  # no raise


class TestProvisioning:
    def test_it_creates_a_worktree_pinned_to_a_sha(self, repo, tmp_path) -> None:
        corpus = provision(repo, tmp_path / "wt")
        try:
            assert (corpus.root / "module.py").read_text(
                encoding="utf-8"
            ) == "VALUE = 1\n"
            assert corpus.sha == _run(repo, "rev-parse", "HEAD").strip()
        finally:
            teardown(corpus)

    def test_it_refuses_to_reuse_an_existing_directory(self, repo, tmp_path) -> None:
        """Reuse would silently mix two runs' evidence in one tree."""
        dest = tmp_path / "wt"
        dest.mkdir()
        with pytest.raises(CorpusError, match="already exists"):
            provision(repo, dest)

    def test_uncommitted_live_work_is_absent_from_the_corpus(
        self, repo, tmp_path
    ) -> None:
        """A worktree carries COMMITTED state, and that is the point.

        Training against unreviewed local edits would make the corpus
        unreproducible and the resulting evidence uncitable.
        """
        (repo / "scratch.py").write_text("not committed\n", encoding="utf-8")
        corpus = provision(repo, tmp_path / "wt")
        try:
            assert not (corpus.root / "scratch.py").exists()
        finally:
            teardown(corpus)

    def test_teardown_leaves_no_registration_behind(self, repo, tmp_path) -> None:
        corpus = provision(repo, tmp_path / "wt")
        teardown(corpus)
        assert not corpus.root.exists()
        assert str(corpus.root) not in _run(repo, "worktree", "list")


class TestScopeIsReplacedNotExtended:
    def test_scope_points_at_the_worktree_and_nothing_else(
        self, repo, tmp_path
    ) -> None:
        corpus = Corpus(root=tmp_path / "wt", sha="deadbeef", source=repo)
        with training_scope(corpus):
            value = os.environ["AIOS_SCOPE_ROOTS"]
        assert value == str(tmp_path / "wt")
        assert "training_ground" not in value, (
            "a self-corpus run that could still write into training_ground would "
            "be reporting progress on the wrong tree"
        )

    def test_a_previous_value_is_restored(self, repo, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("AIOS_SCOPE_ROOTS", "/previous/value")
        corpus = Corpus(root=tmp_path / "wt", sha="deadbeef", source=repo)
        with training_scope(corpus):
            pass
        assert os.environ["AIOS_SCOPE_ROOTS"] == "/previous/value"

    def test_an_unset_variable_is_left_unset(self, repo, tmp_path, monkeypatch) -> None:
        """Leaving a widened scope behind is how a scoped experiment becomes a hole."""
        monkeypatch.delenv("AIOS_SCOPE_ROOTS", raising=False)
        corpus = Corpus(root=tmp_path / "wt", sha="deadbeef", source=repo)
        with training_scope(corpus):
            pass
        assert "AIOS_SCOPE_ROOTS" not in os.environ

    def test_scope_is_restored_even_when_the_run_raises(
        self, repo, tmp_path, monkeypatch
    ) -> None:
        monkeypatch.delenv("AIOS_SCOPE_ROOTS", raising=False)
        corpus = Corpus(root=tmp_path / "wt", sha="deadbeef", source=repo)
        with pytest.raises(ValueError):
            with training_scope(corpus):
                raise ValueError("training blew up")
        assert "AIOS_SCOPE_ROOTS" not in os.environ


class TestTheContainmentProof:
    def test_a_clean_run_completes_and_removes_the_worktree(
        self, repo, tmp_path
    ) -> None:
        with self_corpus(repo, tmp_path / "wt") as corpus:
            (corpus.root / "module.py").write_text("VALUE = 2\n", encoding="utf-8")
            root = corpus.root
        assert not root.exists()

    def test_a_modified_tracked_file_in_the_live_tree_raises(
        self, repo, tmp_path
    ) -> None:
        with pytest.raises(CorpusError, match="CONTAINMENT FAILURE"):
            with self_corpus(repo, tmp_path / "wt"):
                (repo / "module.py").write_text("VALUE = 99\n", encoding="utf-8")

    def test_a_stray_untracked_file_in_the_live_tree_raises(
        self, repo, tmp_path
    ) -> None:
        """`-uall` is why: a new file is a breach even though nothing was edited."""
        with pytest.raises(CorpusError, match="CONTAINMENT FAILURE"):
            with self_corpus(repo, tmp_path / "wt"):
                (repo / "leaked.py").write_text("x = 1\n", encoding="utf-8")

    def test_a_moved_head_in_the_live_tree_raises(self, repo, tmp_path) -> None:
        """A clean status is not proof: the branch itself can have moved."""
        with pytest.raises(CorpusError, match="CONTAINMENT FAILURE"):
            with self_corpus(repo, tmp_path / "wt"):
                (repo / "module.py").write_text("VALUE = 3\n", encoding="utf-8")
                _run(repo, "add", "-A")
                _run(repo, "commit", "-qm", "sneaky")

    def test_the_worktree_is_still_removed_when_training_raises(
        self, repo, tmp_path
    ) -> None:
        """Teardown runs in `finally`, so a crash cannot leave a widened tree."""
        dest = tmp_path / "wt"
        with pytest.raises(ValueError):
            with self_corpus(repo, dest):
                raise ValueError("training blew up")
        assert not dest.exists()
        assert str(dest) not in _run(repo, "worktree", "list")


class TestFingerprint:
    def test_it_is_stable_when_nothing_changes(self, repo) -> None:
        assert fingerprint(repo) == fingerprint(repo)

    def test_it_changes_for_an_untracked_file(self, repo) -> None:
        before = fingerprint(repo)
        (repo / "new.py").write_text("x = 1\n", encoding="utf-8")
        assert fingerprint(repo) != before


class TestTheBaselineMustBeGreenFirst:
    """Without a green baseline, a later red is unattributable."""

    @pytest.fixture()
    def suite_repo(self, tmp_path) -> Path:
        root = tmp_path / "suite-repo"
        root.mkdir()
        _run(root, "init", "-q", "-b", "main")
        _run(root, "config", "user.email", "test@example.invalid")
        _run(root, "config", "user.name", "test")
        (root / "test_green.py").write_text(
            "def test_one():\n    assert 1 + 1 == 2\n", encoding="utf-8"
        )
        (root / "test_red.py").write_text(
            "def test_broken():\n    assert False\n", encoding="utf-8"
        )
        _run(root, "add", "-A")
        _run(root, "commit", "-qm", "suite")
        return root

    def test_a_passing_selection_is_green(self, suite_repo, tmp_path) -> None:
        corpus = provision(suite_repo, tmp_path / "wt")
        try:
            result = run_suite(corpus, ["test_green.py"])
            assert result.green
            assert result.passed == 1
        finally:
            teardown(corpus)

    def test_a_failing_selection_is_not_green(self, suite_repo, tmp_path) -> None:
        corpus = provision(suite_repo, tmp_path / "wt")
        try:
            assert not run_suite(corpus, ["test_red.py"]).green
        finally:
            teardown(corpus)

    def test_a_red_baseline_refuses_to_start_the_run(
        self, suite_repo, tmp_path
    ) -> None:
        corpus = provision(suite_repo, tmp_path / "wt")
        try:
            with pytest.raises(CorpusError, match="NOT green before training"):
                require_green_baseline(corpus, ["test_red.py"])
        finally:
            teardown(corpus)

    def test_a_run_that_collected_nothing_is_not_green(
        self, suite_repo, tmp_path
    ) -> None:
        """Zero passed, zero failed is a suite that never ran — not a pass.

        This is the same hollow-run hole `verification_strength` already
        defends against; a selection that matches nothing must not be able to
        certify a corpus as ready.
        """
        corpus = provision(suite_repo, tmp_path / "wt")
        try:
            result = run_suite(corpus, ["-k", "no_such_test_anywhere"])
            assert result.passed == 0
            assert not result.green
            with pytest.raises(CorpusError, match="NOT green before training"):
                require_green_baseline(corpus, ["-k", "no_such_test_anywhere"])
        finally:
            teardown(corpus)

    def test_an_empty_selection_is_refused_outright(self, suite_repo, tmp_path) -> None:
        corpus = provision(suite_repo, tmp_path / "wt")
        try:
            with pytest.raises(CorpusError, match="empty run is not evidence"):
                run_suite(corpus, [])
        finally:
            teardown(corpus)
