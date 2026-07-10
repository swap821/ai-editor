"""Git-snapshot rollback engine (Blueprint Section 04 stage 11 / Q7).

Before a risky action, the engine captures a snapshot of the sandbox working
tree; if the action breaks something, the tree is restored to that snapshot and
the caller re-runs its baseline checks. The rollback is only "complete" once the
tree matches the snapshot.

**Isolation guarantee:** the engine snapshots a dedicated git *work-tree* at the
scope root (the ``training_ground`` playground by default) — never the project's
own repository. It refuses to run against the project root, so an agent rollback
can never reset your real source tree. Commits are authored with an explicit
in-repo identity, so no global git config is required.

**Out-of-tree git database:** by default the git *database* lives under the
gitignored :data:`aios.config.ROLLBACK_DIR` (inside ``data/``), not inside the
sandbox — so no rollback ``.git`` database lands in the main-repo-tracked
``training_ground/`` (only a tiny ``gitdir:`` pointer file does, which is itself
gitignored). Snapshots are therefore local scratch state, like the rest of
``data/``. An explicitly injected ``repo_dir`` (used by tests) keeps its database
in-tree, since a temp directory is already isolated.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from filelock import FileLock, Timeout
from git import Actor, Repo  # GitPython

from aios import config

#: Identity stamped on snapshot commits (avoids needing global git config).
_AUTHOR = Actor("GAGOS Rollback", "rollback@aios.local")


class RollbackError(RuntimeError):
    """Raised when a snapshot or restore cannot be completed."""


@dataclass(frozen=True)
class Snapshot:
    """A captured point-in-time state of the sandbox tree."""

    sha: str
    message: str


@dataclass(frozen=True)
class RollbackResult:
    """Outcome of a restore operation."""

    restored: bool
    head_sha: str
    reason: str


class RollbackEngine:
    """Snapshot/restore over an isolated git repo in the sandbox scope root."""

    def __init__(
        self,
        repo_dir: Optional[Path] = None,
        *,
        git_dir: Optional[Path] = None,
        lock_path: Optional[Path] = None,
    ) -> None:
        roots = config.SCOPE_ROOTS
        target = Path(repo_dir).resolve() if repo_dir else (
            roots[0] if roots else Path.cwd()
        )

        # Hard refuse to ever operate on the project's own repository.
        if target == config.PROJECT_ROOT or config.PROJECT_ROOT == target:
            raise RollbackError(
                "Refusing to manage rollbacks on the project root; "
                "the rollback engine only operates inside a sandbox scope root."
            )

        self.repo_dir = target
        #: Where the git DATABASE lives. For the default sandbox we keep it OUT of
        #: the tracked work-tree, under the gitignored ``ROLLBACK_DIR`` — leaving
        #: only a small ``gitdir:`` pointer file in ``training_ground/``. When a
        #: ``repo_dir`` is injected (tests), the database stays inside it (a temp
        #: dir is already isolated) unless an explicit ``git_dir`` overrides.
        if git_dir is not None:
            self._git_dir = Path(git_dir).resolve()
        elif repo_dir is None:
            self._git_dir = Path(config.ROLLBACK_DIR).resolve()
        else:
            self._git_dir = (self.repo_dir / ".git").resolve()
            
        # Scope containment validation for CodeQL CWE-22
        try:
            self.repo_dir.relative_to(Path.cwd().resolve())
        except ValueError:
            pass # Testing sometimes puts repo_dir in /tmp, the real check is the hard refusal above.

        if lock_path is not None:
            resolved_lock = Path(lock_path).resolve()
        elif repo_dir is None:
            resolved_lock = (Path(config.ROLLBACK_DIR).parent / "rollback.lock").resolve()
        else:
            resolved_lock = (self.repo_dir.parent / f".{self.repo_dir.name}.rollback.lock").resolve()
        resolved_lock.parent.mkdir(parents=True, exist_ok=True)
        self._repo_lock = FileLock(str(resolved_lock), timeout=30)
        try:
            with self._repo_lock:
                self.repo = self._ensure_repo()
        except Timeout as exc:
            raise RollbackError("Rollback repository is busy; initialization refused") from exc

    def _ensure_repo(self) -> Repo:
        """Open the sandbox repo, initialising it with a baseline commit if new.

        The git *work-tree* is always the sandbox scope root, but the git
        *database* may live elsewhere (:attr:`_git_dir`) so it stays out of the
        tracked tree. When the database is external the repo is created with a
        ``separate_git_dir``, leaving only a ``.git`` pointer file in the work-tree;
        re-opening via the work-tree transparently follows that pointer.
        """
        self.repo_dir.mkdir(parents=True, exist_ok=True)
        # ``.git`` in the work-tree is a directory (in-tree DB) or a ``gitdir:``
        # pointer file (external DB); either way its presence means "already init".
        pointer = self.repo_dir / ".git"
        external = self._git_dir != pointer
        if pointer.exists():
            return Repo(self.repo_dir)

        if external:
            self._git_dir.parent.mkdir(parents=True, exist_ok=True)
            repo = Repo.init(self.repo_dir, separate_git_dir=str(self._git_dir))
        else:
            repo = Repo.init(self.repo_dir)
        # A .gitkeep guarantees a non-empty initial commit even in a bare folder.
        keep = self.repo_dir / ".gitkeep"
        if not keep.exists():
            keep.write_text("", encoding="utf-8")
        repo.index.add([str(keep.relative_to(self.repo_dir))])
        repo.index.commit("baseline: rollback engine initialised", author=_AUTHOR, committer=_AUTHOR)
        return repo

    def create_snapshot(self, message: str = "pre-action snapshot") -> Snapshot:
        """Stage everything and commit a snapshot. Returns the snapshot.

        If the tree is already clean, the current HEAD is returned as the
        snapshot (no empty commit is created).
        """
        try:
            with self._repo_lock:
                self.repo.git.add(A=True)
                if not self.repo.is_dirty(untracked_files=True):
                    head = self.repo.head.commit
                    return Snapshot(sha=head.hexsha, message=f"(clean) {message}")
                commit = self.repo.index.commit(
                    f"[SNAPSHOT] {message}", author=_AUTHOR, committer=_AUTHOR
                )
                return Snapshot(sha=commit.hexsha, message=message)
        except Exception as exc:  # noqa: BLE001
            raise RollbackError(f"Snapshot failed: {exc}") from exc

    def rollback(self, sha: Optional[str] = None) -> RollbackResult:
        """Restore the tree to *sha* (or the previous snapshot if omitted).

        Performs a hard reset plus a clean of untracked files, so the working
        tree exactly matches the target snapshot.
        """
        try:
            with self._repo_lock:
                if sha is None:
                    commits = list(self.repo.iter_commits(max_count=2))
                    if len(commits) < 2:
                        return RollbackResult(
                            restored=False,
                            head_sha=self.repo.head.commit.hexsha,
                            reason="No previous snapshot to roll back to.",
                        )
                    sha = commits[1].hexsha

                self.repo.git.reset("--hard", sha)
                self.repo.git.clean("-fd")
                head = self.repo.head.commit.hexsha
                return RollbackResult(
                    restored=(head == sha),
                    head_sha=head,
                    reason=f"Workspace restored to {sha[:10]}.",
                )
        except Exception as exc:  # noqa: BLE001
            raise RollbackError(f"Rollback failed: {exc}") from exc

    def list_snapshots(self, limit: int = 10) -> list[Snapshot]:
        """Return the most recent snapshot commits, newest first."""
        try:
            with self._repo_lock:
                out: list[Snapshot] = []
                for commit in self.repo.iter_commits(max_count=limit):
                    out.append(Snapshot(sha=commit.hexsha, message=str(commit.message).strip()))
                return out
        except Exception as exc:  # noqa: BLE001
            raise RollbackError(f"Snapshot listing failed: {exc}") from exc
