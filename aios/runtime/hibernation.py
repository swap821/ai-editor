"""Local-only hibernation maintenance.

Hibernation is a proposal/evidence mode. It previews maintenance and rebuilds
local knowledge, but it does not perform autonomous writes, cloud calls,
self-modification, git pushes, or credential access.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from aios import config
from aios.learning.meta_loop import assess_meta_loop, collect_meta_loop_evidence
from aios.memory.project_passport import RepoScanLimits, harvest_project_passport
from aios.runtime.budget_guard import BudgetGuard


class HibernationPolicyError(RuntimeError):
    """Raised when a hibernation caller requests a forbidden capability."""


class CompactorLike(Protocol):
    def compact(self, dry_run: bool = True) -> dict[str, Any]:
        ...


class PheromoneStoreLike(Protocol):
    def query(self, *args: Any, **kwargs: Any) -> list[Any]:
        ...


@dataclass(frozen=True)
class HibernationReport:
    mode: str
    local_only: bool
    writes_performed: bool
    cloud_calls: int
    compaction: dict[str, Any]
    pheromones: dict[str, Any]
    project_passport: dict[str, Any]
    audit_summary: dict[str, Any]
    proposals: list[str]
    resource_status: dict[str, Any]
    meta_loop_assessment: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "localOnly": self.local_only,
            "writesPerformed": self.writes_performed,
            "cloudCalls": self.cloud_calls,
            "compaction": self.compaction,
            "pheromones": self.pheromones,
            "projectPassport": self.project_passport,
            "auditSummary": self.audit_summary,
            "proposals": self.proposals,
            "resourceStatus": self.resource_status,
            "metaLoopAssessment": self.meta_loop_assessment,
        }


class HibernationManager:
    def __init__(
        self,
        *,
        repo_root: str | Path = config.PROJECT_ROOT,
        compactor: CompactorLike | None = None,
        pheromone_store: PheromoneStoreLike | None = None,
        audit_db_path: str | Path = config.AUDIT_DB_PATH,
        budget_guard: BudgetGuard | None = None,
    ) -> None:
        self.repo_root = Path(repo_root)
        self.compactor = compactor
        self.pheromone_store = pheromone_store
        self.audit_db_path = Path(audit_db_path)
        self.budget_guard = budget_guard or BudgetGuard(mode="hibernation")
        self.budget_guard.set_mode("hibernation")

    def run(
        self,
        *,
        allow_writes: bool = False,
        allow_cloud: bool = False,
        rebuild_repo_map: bool = True,
    ) -> HibernationReport:
        if allow_writes:
            raise HibernationPolicyError("hibernation cannot perform writes")
        if allow_cloud:
            raise HibernationPolicyError("hibernation cannot perform cloud calls")

        compaction = self._compaction_preview()
        pheromones = self._pheromone_preview()
        project_passport = self._project_passport() if rebuild_repo_map else {
            "skipped": True,
            "reason": "repo map rebuild disabled",
        }
        audit_summary = self._audit_summary()
        proposals = list(project_passport.get("suggested_improvements", []))[:10]
        return HibernationReport(
            mode="hibernation",
            local_only=True,
            writes_performed=False,
            cloud_calls=0,
            compaction=compaction,
            pheromones=pheromones,
            project_passport=project_passport,
            audit_summary=audit_summary,
            proposals=proposals,
            resource_status=self.budget_guard.snapshot().to_dict(),
            meta_loop_assessment=self._meta_loop_assessment(compaction, pheromones, audit_summary),
        )

    def _compaction_preview(self) -> dict[str, Any]:
        if self.compactor is None:
            return {"skipped": True, "reason": "no compactor configured"}
        result = self.compactor.compact(dry_run=True)
        result["dry_run"] = True
        return result

    def _pheromone_preview(self) -> dict[str, Any]:
        if self.pheromone_store is None:
            return {"skipped": True, "reason": "pheromone store not configured"}
        pheromones = self.pheromone_store.query(min_strength=0.0)
        return {
            "dry_run": True,
            "signals_seen": len(pheromones),
            "decay_performed": False,
        }

    def _project_passport(self) -> dict[str, Any]:
        passport = harvest_project_passport(
            self.repo_root,
            limits=RepoScanLimits(max_files=200, max_file_bytes=80_000),
        )
        return passport.as_dict()

    def _meta_loop_assessment(
        self,
        compaction: dict[str, Any],
        pheromones: dict[str, Any],
        audit_summary: dict[str, Any],
    ) -> dict[str, Any]:
        """Advisory self-assessment over this hibernation cycle's own evidence.

        meta_loop.py ships a dedicated ``_hibernation_source`` adapter for
        exactly this shape but had no caller anywhere in the codebase. This
        is real evidence collection (this cycle's compaction/pheromone/audit
        state), not a synthetic call proving the import path works.
        """
        snapshot = collect_meta_loop_evidence(
            hibernation_report={
                "mode": "hibernation",
                "compaction": compaction,
                "pheromones": pheromones,
                "auditSummary": audit_summary,
            },
        )
        return assess_meta_loop(snapshot).as_dict()

    def _audit_summary(self) -> dict[str, Any]:
        if not self.audit_db_path.exists():
            return {"exists": False, "tables": {}, "error": ""}
        try:
            with sqlite3.connect(self.audit_db_path) as conn:
                rows = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
                tables: dict[str, int] = {}
                for (name,) in rows:
                    if not isinstance(name, str):
                        continue
                    count = conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
                    tables[name] = int(count)
        except sqlite3.Error as exc:
            return {"exists": True, "tables": {}, "error": str(exc)}
        return {"exists": True, "tables": tables, "error": ""}


__all__ = [
    "HibernationManager",
    "HibernationPolicyError",
    "HibernationReport",
]
