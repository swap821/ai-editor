"""Git worktree backend for true parallel worker filesystem lanes."""
from __future__ import annotations

import re
import subprocess
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_LANE_ID_RE = re.compile(r"^[A-Za-z0-9-]+$")


class InvalidLaneIdError(ValueError):
    pass


class LaneExistsError(RuntimeError):
    pass


class LaneNotFoundError(RuntimeError):
    pass


@dataclass(frozen=True)
class WorktreeLane:
    lane_id: str
    path: Path
    branch: str
    active: bool


class WorktreeBackend:
    """Manages git worktrees for isolated parallel worker execution."""

    def __init__(self, base_repo: Path, worktree_root: Path):
        self._base_repo = base_repo
        self._root = worktree_root
        self._root.mkdir(parents=True, exist_ok=True)

    def _validate_lane_id(self, lane_id: str) -> None:
        if not lane_id or not _LANE_ID_RE.match(lane_id):
            raise InvalidLaneIdError(
                f"lane_id must be alphanumeric + hyphens only, got: {lane_id!r}"
            )

    def _lane_path(self, lane_id: str) -> Path:
        return self._root / lane_id

    def create_lane(self, lane_id: str, branch: str | None = None) -> Path:
        self._validate_lane_id(lane_id)
        lane_path = self._lane_path(lane_id)
        if lane_path.exists():
            raise LaneExistsError(f"lane already exists: {lane_id}")
        branch = branch or f"lane-{lane_id}"
        existing_branches = self._run_git(["branch", "--list", branch]).strip()
        args = ["worktree", "add"]
        if not existing_branches:
            args += ["-b", branch, str(lane_path)]
        else:
            args += [str(lane_path), branch]
        self._run_git(args)
        return lane_path

    def destroy_lane(self, lane_id: str) -> None:
        self._validate_lane_id(lane_id)
        lane_path = self._lane_path(lane_id)
        if not lane_path.exists():
            raise LaneNotFoundError(f"lane does not exist: {lane_id}")
        self._run_git(["worktree", "remove", str(lane_path), "--force"])
        self._run_git(["worktree", "prune"])
        if lane_path.exists():
            shutil.rmtree(lane_path, ignore_errors=True)

    def list_lanes(self) -> list[WorktreeLane]:
        output = self._run_git(["worktree", "list", "--porcelain"])
        lanes: list[WorktreeLane] = []
        current: dict[str, Any] = {}

        def flush() -> None:
            if "worktree" not in current:
                return
            path = Path(current["worktree"])
            try:
                path.relative_to(self._root)
            except ValueError:
                current.clear()
                return
            lane_id = path.name
            branch = current.get("branch", "")
            if branch.startswith("refs/heads/"):
                branch = branch[len("refs/heads/") :]
            lanes.append(
                WorktreeLane(
                    lane_id=lane_id,
                    path=path,
                    branch=branch,
                    active="prunable" not in current and "locked" not in current,
                )
            )
            current.clear()

        for line in output.splitlines():
            if not line.strip():
                flush()
                continue
            if line.startswith("worktree "):
                flush()
                current["worktree"] = line[len("worktree ") :]
            elif line.startswith("branch "):
                current["branch"] = line[len("branch ") :]
            elif line.startswith("prunable"):
                current["prunable"] = True
            elif line.startswith("locked"):
                current["locked"] = True
        flush()
        return lanes

    def lane_exists(self, lane_id: str) -> bool:
        self._validate_lane_id(lane_id)
        return self._lane_path(lane_id).exists()

    def _run_git(self, args: list[str], cwd: Path | None = None) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=str(cwd or self._base_repo),
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.stdout
