"""Development, operator-model, autonomy, and curriculum routes.

Extracted from ``aios/api/main.py`` (monolith split, 2026-07-06) into an
APIRouter module. Dependency providers come from ``aios.api.deps`` — the SAME
function objects ``main`` re-exports, so ``app.dependency_overrides`` keyed on
either import path keep working.
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from aios import config
from aios.api.deps import (
    get_autonomy,
    get_curriculum_manager,
    get_development_tracker,
    require_privileged_operator,
    get_semantic_facts,
    get_skill_memory,
    get_memory_authority,
)
from aios.core.autonomy import AutonomyLedger
from aios.memory.curriculum import CurriculumManager
from aios.memory.development import DevelopmentTracker
from aios.memory.facts import SemanticFacts
from aios.memory.skills import SkillMemory
from aios.domain.identity.models import Principal
from aios.api.action_guard import enforce_action_boundary
from aios.application.memory.authority import MemoryAuthority

router = APIRouter(dependencies=[Depends(enforce_action_boundary)])


class CurriculumTaskRequest(BaseModel):
    """Body for defining a safe curriculum task; definitions never auto-run."""

    skill_name: str = Field(..., alias="skillName")
    level: int = Field(..., ge=1)
    prompt: str
    held_out: bool = Field(False, alias="heldOut")

    model_config = {"populate_by_name": True}


@router.get("/api/v1/development/metrics")
def development_metrics(
    tracker: DevelopmentTracker = Depends(get_development_tracker),
    authority: MemoryAuthority = Depends(get_memory_authority),
) -> dict[str, Any]:
    """Return measured behavior-change and verification coverage metrics."""
    if authority.owns_store("development", tracker):
        return authority.development_summary()
    return tracker.summary()


@router.get("/api/v1/operator/model")
def operator_model(
    facts: SemanticFacts = Depends(get_semantic_facts),
    authority: MemoryAuthority = Depends(get_memory_authority),
) -> dict[str, Any]:
    """Structured snapshot of what the system knows about the operator."""
    if authority.owns_store("facts", facts):
        return authority.operator_model()
    from aios.memory.operator_model import render_operator_model

    return render_operator_model(facts)


@router.get("/api/v1/development/skills")
def development_skills(
    status: Optional[str] = None,
    skills: SkillMemory = Depends(get_skill_memory),
    authority: MemoryAuthority = Depends(get_memory_authority),
) -> dict[str, Any]:
    """List candidate and verified procedural skills."""
    if authority.owns_store("skills", skills):
        return {"skills": authority.skills_list(status=status)}
    return {"skills": skills.list(status=status)}


@router.get("/api/v1/development/trails")
def development_trails(
    skills: SkillMemory = Depends(get_skill_memory),
    authority: MemoryAuthority = Depends(get_memory_authority),
) -> dict[str, Any]:
    """The pheromone map: every trail's computed strength, decay, and reuse
    evidence as of now, plus superseded-fragment lineage and the constants in
    effect — read-only observability and the tuning evidence base."""
    if authority.owns_store("skills", skills):
        return authority.skills_trail_map()
    return skills.trail_map()


@router.get("/api/v1/development/harness")
def development_harness() -> dict[str, Any]:
    """Aggregate status from automated experience harnesses (read-only).

    Reads the JSONL audit logs produced by the three harness tools and returns
    summary metrics: last run timestamps, cumulative success rates, and green/red
    status for each harness.
    """
    import json as _json
    from pathlib import Path as _Path

    audit_dir = _Path(config.PROJECT_ROOT) / ".aios" / "audit"
    result: dict[str, Any] = {}

    for name, filename, summary_kind in [
        ("experience", "experience-accumulator.jsonl", "run-summary"),
        ("golden", "golden-mission-runs.jsonl", "batch-summary"),
        ("endurance", "endurance-test.jsonl", "endurance-summary"),
    ]:
        log_path = audit_dir / filename
        if not log_path.exists():
            result[name] = {"runs": 0, "status": "no_data"}
            continue
        summaries: list[dict[str, Any]] = []
        try:
            with log_path.open() as fh:
                for line in fh:
                    record = _json.loads(line)
                    if record.get("kind") == summary_kind:
                        summaries.append(record)
        except (OSError, _json.JSONDecodeError):
            result[name] = {"runs": 0, "status": "error"}
            continue

        if not summaries:
            result[name] = {"runs": 0, "status": "no_data"}
            continue

        latest = summaries[-1]
        if name == "experience":
            result[name] = {
                "runs": len(summaries),
                "latest_success_rate": latest.get("success_rate", 0),
                "total_sessions": sum(s.get("total", 0) for s in summaries),
                "status": "green" if latest.get("success_rate", 0) >= 0.7 else "needs_attention",
            }
        elif name == "golden":
            result[name] = {
                "runs": len(summaries),
                "latest_pass_rate": latest.get("rate", 0),
                "total_missions": latest.get("total", 0),
                "status": "green" if latest.get("rate", 0) >= 0.8 else "needs_attention",
            }
        elif name == "endurance":
            result[name] = {
                "runs": len(summaries),
                "latest_green": latest.get("green", False),
                "latest_success_rate": latest.get("success_rate", 0),
                "latency_p95_s": latest.get("latency_p95_s", 0),
                "status": "green" if latest.get("green", False) else "needs_attention",
            }

    return {"harnesses": result}


@router.get("/api/v1/development/workspace")
def development_workspace() -> dict[str, Any]:
    """The agent's manufacturing workspace: the text files currently in
    ``training_ground/`` (the agent's writable sandbox), most-recent first, with
    contents. Read-only observability so a UI (the forge editor) can show the
    mind's ACTUAL written files — independent of how the write landed (approval,
    earned-autonomy, or edit). Strictly confined to ``training_ground/`` (no path
    parameter, no traversal); skips caches/binaries and caps file count + size so
    the response stays small."""
    from pathlib import Path

    root = Path(config.PROJECT_ROOT) / "training_ground"
    text_exts = {
        ".py", ".js", ".jsx", ".ts", ".tsx", ".html", ".css", ".json",
        ".md", ".txt", ".sh", ".yml", ".yaml", ".toml",
    }
    files: list[dict[str, str]] = []
    if root.is_dir():
        def _mtime(path: Path) -> float:
            try:
                return path.stat().st_mtime
            except OSError:
                return 0.0

        candidates = [
            p for p in root.rglob("*")
            if p.is_file()
            and "__pycache__" not in p.parts
            and p.suffix.lower() in text_exts
        ]
        candidates.sort(key=_mtime, reverse=True)  # newest write first
        for p in candidates:
            try:
                if p.stat().st_size > 200_000:
                    continue
                content = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            files.append({"path": p.relative_to(root).as_posix(), "content": content})
            if len(files) >= 16:
                break
    return {"root": "training_ground", "files": files}


@router.get("/api/v1/development/autonomy")
def development_autonomy(
    autonomy: AutonomyLedger = Depends(get_autonomy),
) -> dict[str, Any]:
    """The earned-autonomy ledger: which YELLOW action classes have graduated to
    autonomous execution by verified-success evidence, which are revoked, and the
    threshold + master switch in effect — read-only observability for the operator."""
    return autonomy.ledger_map()


@router.post("/api/v1/development/autonomy/revoke")
def development_autonomy_revoke(
    signature: str,
    _principal: Principal = Depends(require_privileged_operator),
    autonomy: AutonomyLedger = Depends(get_autonomy),
) -> dict[str, Any]:
    """Operator force-revoke of an earned signature — human authority over the
    bridge stays absolute: any earned class can be pulled back to YELLOW at will."""
    return {"revoked": autonomy.revoke(signature)}


@router.get("/api/v1/development/curriculum")
def development_curriculum(
    skill_name: Optional[str] = None,
    curriculum: CurriculumManager = Depends(get_curriculum_manager),
) -> dict[str, Any]:
    """List safe curriculum definitions and evidence state."""
    return {"tasks": curriculum.list(skill_name)}


@router.post("/api/v1/development/curriculum")
def add_curriculum_task(
    req: CurriculumTaskRequest,
    _principal: Principal = Depends(require_privileged_operator),
    curriculum: CurriculumManager = Depends(get_curriculum_manager),
) -> dict[str, Any]:
    """Define a curriculum task without executing it."""
    try:
        task_id = curriculum.add_task(
            req.skill_name, req.level, req.prompt, held_out=req.held_out
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"id": task_id, "executed": False}


@router.get("/api/v1/development/curriculum/proposals")
def curriculum_proposals(
    max_proposals: int = 10,
    curriculum: CurriculumManager = Depends(get_curriculum_manager),
) -> dict[str, Any]:
    """List auto-generated curriculum proposals from audit evidence."""
    from aios.memory.curriculum_miner import CurriculumMiner
    miner = CurriculumMiner()
    proposals = miner.list_proposals(max_proposals=max_proposals)
    return {
        "proposals": [
            {
                "fingerprint": p.fingerprint,
                "skill_name": p.skill_name,
                "level": p.level,
                "prompt": p.prompt,
                "rationale": p.rationale,
                "source_pattern": p.source_pattern,
                "difficulty_delta": p.difficulty_delta,
            }
            for p in proposals
        ]
    }


@router.post("/api/v1/development/curriculum/proposals/accept")
def accept_curriculum_proposal(
    req: dict[str, Any],
    _principal: Principal = Depends(require_privileged_operator),
    curriculum: CurriculumManager = Depends(get_curriculum_manager),
) -> dict[str, Any]:
    """Accept a mined proposal, adding it to the live curriculum."""
    fingerprint = req.get("fingerprint")
    if not fingerprint:
        raise HTTPException(status_code=422, detail="fingerprint required")
    from aios.memory.curriculum_miner import CurriculumMiner
    miner = CurriculumMiner()
    proposals = miner.list_proposals(max_proposals=50)
    match = next((p for p in proposals if p.fingerprint == fingerprint), None)
    if not match:
        raise HTTPException(status_code=404, detail="proposal not found")
    try:
        task_id = curriculum.add_task(match.skill_name, match.level, match.prompt)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"id": task_id, "accepted": True, "prompt": match.prompt}
