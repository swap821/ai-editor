"""Git-snapshot rollback engine (Blueprint Section 04 stage 11 / Q7).

Before a risky action, the engine captures a snapshot of the sandbox working
tree; if the action breaks something, the tree is restored to that snapshot and
the caller re-runs its baseline checks. The rollback is only "complete" once the
tree matches the snapshot.

**Isolation guarantee:** the engine operates on a dedicated git repository *inside
the scope root* (the ``training_ground`` playground by default) — never the
project's own repository. It refuses to run against the project root, so an
agent rollback can never reset your real source tree. Commits are authored with
an explicit in-repo identity, so no global git config is required.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from git import Actor, Repo  # GitPython

from aios import config

#: Identity stamped on snapshot commits (avoids needing global git config).
_AUTHOR = Actor("AI-OS Rollback", "rollback@aios.local")


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

    def __init__(self, repo_dir: Optional[Path] = None) -> None:
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
        self.repo = self._ensure_repo()

    def _ensure_repo(self) -> Repo:
        """Open the sandbox repo, initialising it with a baseline commit if new."""
        self.repo_dir.mkdir(parents=True, exist_ok=True)
        git_dir = self.repo_dir / ".git"
        if git_dir.exists():
            return Repo(self.repo_dir)

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
        out: list[Snapshot] = []
        for commit in self.repo.iter_commits(max_count=limit):
            out.append(Snapshot(sha=commit.hexsha, message=str(commit.message).strip()))
        return out
