#!/usr/bin/env python3
"""Train on this repository without training ON this repository.

WHY
---
The learning chain has only ever been exercised against synthetic
``training_ground/`` toys, and the machine holds no other project with a test
suite at all (see ``.aios/state/TRAINING_CORPUS_INVENTORY.md`` — eleven
package.json files across six projects, zero test scripts). That matters
because STRONG verification is defined as *a recognized test runner reporting
passes with no failures*, and STRONG is the promotion floor. A corpus with no
suite cannot promote a single skill, so it cannot teach the system anything.

This repository is the one corpus on this machine that meets the bar: a large
suite that is currently green. The operator's call was to start here — the
system learns by reverse-engineering itself before it is pointed at anything
else.

Which raises the obvious danger, and this module exists for exactly that
danger: **a training run that edits the real working tree is a containment
failure, not a learning result.** Everything below is the isolation, and it is
written to fail loudly rather than quietly succeed.

THE FOUR GUARANTEES
-------------------
1. **Training happens in a throwaway git worktree**, pinned to a commit, never
   in the live tree.
2. **The live tree is never in scope.** ``AIOS_SCOPE_ROOTS`` is *replaced*
   (not extended) with the worktree path, so the executor's scope lock cannot
   reach the real repository even if an agent tries.
3. **The live tree is fingerprinted before and after**, and a difference raises
   — the run fails, whatever its score was. A containment breach that produced
   a good number is still a breach.
4. **The worktree is verified green before the agent touches it.** Without a
   green baseline, "the agent broke it" and "it was already broken" are the
   same observation, which is the vacuous-result trap this repo spends its
   effort refusing.

Nothing here weakens the frozen guardrails. ``AIOS_SCOPE_ROOTS`` is the
supported mechanism defined in ``aios/security/limits.py``; this module only
sets it, and sets it NARROWER in the sense that matters — a single throwaway
directory, with ``training_ground`` and ``lab`` dropped for the run's duration.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


class CorpusError(RuntimeError):
    """A containment or precondition failure. Never caught to keep a run alive."""


def _git(repo: Path, *args: str, check: bool = True) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if check and result.returncode != 0:
        raise CorpusError(
            f"git {' '.join(args)} failed in {repo}: {result.stderr.strip()}"
        )
    return result.stdout


def fingerprint(repo: Path) -> str:
    """A digest of everything a training run could disturb in *repo*.

    ``status --porcelain -uall`` lists every modified tracked file AND every
    untracked path, so a stray file written into the live tree changes this
    just as surely as an edit does. HEAD is folded in because a run that moved
    the branch has also changed the tree, even if the status is clean.
    """
    head, status = _tree_state(repo)
    digest = hashlib.sha256(f"{head}\n{status}".encode("utf-8")).hexdigest()
    return digest


def _tree_state(repo: Path) -> tuple[str, str]:
    return (
        _git(repo, "rev-parse", "HEAD").strip(),
        _git(repo, "status", "--porcelain=v1", "-uall"),
    )


def _changed_paths(before_status: str, after_status: str) -> list[str]:
    """Paths present in one status listing and not the other.

    A digest tells you THAT the tree moved; only the paths tell you whether it
    matters. The first real containment alarm fired because a second agent was
    editing `frontend/` in the same checkout at the same time -- a true
    statement the message could not distinguish from a training run escaping
    into the live tree, which is the one thing it exists to catch.
    """
    before = set(before_status.splitlines())
    after = set(after_status.splitlines())
    return sorted(
        line[3:].strip().strip('"') for line in (after - before) | (before - after)
    )


def assert_isolated(repo: Path, dest: Path) -> None:
    """Refuse any destination that overlaps the live repository.

    A worktree nested inside the repo would put the live tree's parent on the
    scope path, and a repo nested inside the worktree is the same mistake
    upside down. Checked with ``resolve()`` on both sides because a symlink or
    a ``..`` segment is exactly how this kind of check gets fooled.
    """
    repo, dest = repo.resolve(), dest.resolve()
    if repo == dest:
        raise CorpusError("destination is the live repository itself")
    if dest.is_relative_to(repo):
        raise CorpusError(f"destination {dest} is inside the live repository {repo}")
    if repo.is_relative_to(dest):
        raise CorpusError(f"live repository {repo} is inside the destination {dest}")


@dataclass(frozen=True)
class Corpus:
    """A provisioned training worktree."""

    root: Path
    sha: str
    source: Path

    @property
    def scope_roots(self) -> str:
        """The value ``AIOS_SCOPE_ROOTS`` takes for this run — this and nothing else."""
        return str(self.root)


def provision(repo: Path, dest: Path, *, ref: str = "HEAD") -> Corpus:
    """Create a throwaway worktree of *repo* at *ref*.

    The worktree is detached at a resolved sha rather than tracking a branch:
    a training run must not be able to move a branch the operator is using, and
    a pinned sha is also what makes a result reproducible later.

    Note that a worktree carries COMMITTED state. Uncommitted work in the live
    tree is deliberately absent — training against unreviewed local edits would
    make the corpus unreproducible and the result unciteable.
    """
    repo = repo.resolve()
    dest = dest.resolve()
    assert_isolated(repo, dest)
    if dest.exists():
        raise CorpusError(f"destination {dest} already exists; refusing to reuse it")
    sha = _git(repo, "rev-parse", ref).strip()
    dest.parent.mkdir(parents=True, exist_ok=True)
    _git(repo, "worktree", "add", "--detach", str(dest), sha)
    return Corpus(root=dest, sha=sha, source=repo)


def teardown(corpus: Corpus) -> None:
    """Remove the worktree and its registration, leaving no trace in *repo*.

    ``--force`` because the whole point of the worktree is that the agent
    dirtied it; a run that ended with modifications is the normal case, not an
    error. The prune afterwards is what keeps ``git worktree list`` in the live
    repository honest when the directory is already gone.
    """
    _git(corpus.source, "worktree", "remove", "--force", str(corpus.root), check=False)
    if corpus.root.exists():
        shutil.rmtree(corpus.root, ignore_errors=True)
    _git(corpus.source, "worktree", "prune", check=False)


@contextmanager
def training_scope(corpus: Corpus) -> Iterator[Corpus]:
    """Point the executor's scope lock at the worktree, and only the worktree.

    ``AIOS_SCOPE_ROOTS`` REPLACES the defaults rather than extending them (see
    ``_env_scope_roots`` in ``aios/security/limits.py``), so inside this block
    ``training_ground`` and ``lab`` are out of scope too. That is intended: a
    self-corpus run that quietly wrote into ``training_ground`` would be
    reporting progress on the wrong tree.

    The previous value is restored on the way out, including the case where it
    was unset — leaving a widened scope behind after a crash is precisely the
    kind of residue that turns a scoped experiment into a standing hole.
    """
    # BOTH mechanisms, because they cover different processes and only one of
    # them was here. `AIOS_SCOPE_ROOTS` is read when `aios.security.limits` is
    # IMPORTED, so setting it in a process that already imported aios changes
    # nothing in that process -- this block's own docstring claimed the
    # executor's scope lock was confined, and in-process it was not. It was
    # still effective for CHILD processes, which import aios fresh, and the
    # worktree plus the before/after fingerprint were doing the real work.
    #
    # `set_scope_roots` is the supported in-process re-declaration, so the two
    # together make the documented guarantee true for the runner AND anything
    # it spawns. Both are restored on the way out: a widened scope left behind
    # after a crash is exactly the residue that turns a scoped experiment into
    # a standing hole.
    from aios.security.scope_lock import get_scope_roots, set_scope_roots

    previous = os.environ.get("AIOS_SCOPE_ROOTS")
    previous_roots = get_scope_roots()
    os.environ["AIOS_SCOPE_ROOTS"] = corpus.scope_roots
    set_scope_roots([corpus.root])
    try:
        yield corpus
    finally:
        set_scope_roots(previous_roots)
        if previous is None:
            os.environ.pop("AIOS_SCOPE_ROOTS", None)
        else:
            os.environ["AIOS_SCOPE_ROOTS"] = previous


@contextmanager
def self_corpus(repo: Path, dest: Path, *, ref: str = "HEAD") -> Iterator[Corpus]:
    """Provision, train, tear down — and prove the live tree never moved.

    The before/after fingerprint check runs in a ``finally``, so it fires even
    when the training run raised. It raises on mismatch rather than logging,
    because a run that disturbed the live tree has produced an unusable result
    no matter what its score said: there is no way afterwards to tell which of
    the two trees the evidence came from.
    """
    repo = repo.resolve()
    before_head, before_status = _tree_state(repo)
    before = fingerprint(repo)
    corpus = provision(repo, dest, ref=ref)
    try:
        with training_scope(corpus):
            yield corpus
    finally:
        teardown(corpus)
        after = fingerprint(repo)
        if after != before:
            after_head, after_status = _tree_state(repo)
            paths = _changed_paths(before_status, after_status)
            listing = "\n  ".join(paths[:12]) or "(HEAD moved, status unchanged)"
            if len(paths) > 12:
                listing += f"\n  ... and {len(paths) - 12} more"
            if before_head != after_head:
                listing += f"\nHEAD also moved: {before_head[:12]} -> {after_head[:12]}"
            raise CorpusError(
                "CONTAINMENT FAILURE: the live working tree changed during a "
                f"training run ({before[:12]} -> {after[:12]}).\n"
                f"Paths that differ:\n  {listing}\n"
                "Read them before drawing a conclusion. Training writes ONLY "
                "inside the worktree, so a path under the live tree points at a "
                "concurrent writer -- another agent in this checkout, an editor "
                "saving, a background job -- far more often than at an escape. "
                "Either way this run's evidence cannot be attributed to the "
                "worktree, so it is refused rather than reported."
            )


@dataclass(frozen=True)
class SuiteResult:
    """What a pytest run in the corpus actually reported."""

    passed: int
    failed: int
    errors: int
    returncode: int
    tail: str

    @property
    def green(self) -> bool:
        """Green means passes AND no failures — `passed > 0` is load-bearing.

        A run that collected nothing exits 5 with zero of everything. Treating
        that as green is how a suite that never executed becomes evidence, which
        is the same hollow-run hole `verification_strength` already defends
        against on the verifier side.
        """
        return (
            self.returncode == 0 and self.passed > 0 and self.failed == self.errors == 0
        )

    @property
    def hollow(self) -> bool:
        """The runner produced NOTHING: not a red suite, a suite that never ran.

        `green` already refuses to call a hollow run a pass. Nothing refused to
        call it a FAILURE, and that asymmetry is the dangerous half, because a
        failure gets attributed to whoever wrote the test.

        Observed live on 2026-09-21: right after Ollama timed out at 300s --
        the machine under memory pressure -- six consecutive attempts across
        two cloud tiers came back "rejected" in 1-4 seconds each with a
        COMPLETELY EMPTY reason. pytest cannot produce no output; a real red
        prints the assertion, a collection error prints the traceback, and even
        "collected 0 items" prints. Empty means the subprocess died before
        saying anything. Those six rejections were recorded as the models'
        failures. They were the laptop's.

        The other direction is worse and less obvious. `fails_when_mutated` is
        computed as `not mutated.green`, so a hollow MUTATED run satisfies the
        negative control for exactly the wrong reason -- a test that pins
        nothing would be EARNED because the run that was supposed to catch it
        never happened.

        A tail is empty only when stdout and stderr were both empty, since
        `_useful_tail` falls back to the last lines when it finds no failure
        lines. So this is not a heuristic about what the output looked like.
        """
        return self.passed == self.failed == self.errors == 0 and not self.tail.strip()


_COUNT_RE = re.compile(r"(\d+) (passed|failed|error|errors)")

#: Lines that actually say what went wrong. A plain last-N-lines tail is mostly
#: pytest's summary furniture, and on a truncated log the one line a reader needs
#: -- the assertion -- is the line that got cut. That cost a manual reproduction
#: the first time this tool reported a failure: the note said "clean run not
#: green" and then showed the banner above the error instead of the error.
_SIGNAL = re.compile(r"^(E\s|assert |FAILED |ERROR |>\s)", re.MULTILINE)


def _useful_tail(output: str, *, limit: int = 30) -> str:
    """The failure lines when there are any, else the last few lines."""
    lines = (output or "").splitlines()
    signal = [line for line in lines if _SIGNAL.match(line)]
    if signal:
        return "\n".join(signal[:limit])
    return "\n".join(lines[-12:])


def run_suite(
    corpus: Corpus, selection: list[str], *, timeout: int = 1800
) -> SuiteResult:
    """Run a declared subset of the corpus's own suite, inside the worktree.

    *selection* is passed to pytest verbatim (paths, ``::`` node ids, ``-k``
    expressions are the caller's business). It is declared ONCE by the caller
    and used for both the baseline and the verification, because a baseline
    measured on a different selection than the verification proves nothing
    about the change between them.
    """
    if not selection:
        raise CorpusError("a suite selection is required; an empty run is not evidence")
    result = subprocess.run(
        # NO `-q` here. This repo's pytest.ini already carries `-q` in addopts,
        # and a second one makes `-qq`, which SUPPRESSES the "N passed" summary
        # line entirely -- leaving a green run indistinguishable from a run that
        # collected nothing. The counts are the evidence; do not mute them.
        # `sys.executable`, never a bare "python". Found by Codex, not by me:
        # a bare name resolves through PATH, and inside a virtualenv that is a
        # DIFFERENT interpreter from the one running this code -- one without
        # pytest installed. Seven self-corpus tests failed in his `.venv` while
        # passing here, because on this machine `python` and `sys.executable`
        # happen to be the same binary. "It works here because of an accident
        # of this environment" is the defect this repository keeps finding in
        # other places; this is the same one, in mine.
        [
            sys.executable,
            "-m",
            "pytest",
            *selection,
            "-p",
            "no:cacheprovider",
            "--no-cov",
        ],
        cwd=str(corpus.root),
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )
    output = (result.stdout or "") + (result.stderr or "")
    counts = {"passed": 0, "failed": 0, "error": 0, "errors": 0}
    for value, label in _COUNT_RE.findall(output):
        counts[label] = int(value)
    return SuiteResult(
        passed=counts["passed"],
        failed=counts["failed"],
        errors=max(counts["error"], counts["errors"]),
        returncode=result.returncode,
        tail=_useful_tail(output),
    )


def require_green_baseline(corpus: Corpus, selection: list[str]) -> SuiteResult:
    """Prove the corpus is green BEFORE the agent touches it.

    Without this, "the agent broke it" and "it was already broken" are the same
    observation — and a red baseline also makes a later green impossible to
    read as progress. Raises rather than returning a flag: continuing past a
    red baseline can only produce a result nobody should believe.
    """
    result = run_suite(corpus, selection)
    if not result.green:
        raise CorpusError(
            "the training corpus is NOT green before training "
            f"({result.passed} passed, {result.failed} failed, {result.errors} errors, "
            f"rc={result.returncode}). A run from here cannot distinguish a "
            f"regression the agent caused from one it inherited.\n{result.tail}"
        )
    return result
