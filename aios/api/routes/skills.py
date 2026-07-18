"""API routes for managing the Skill Library."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from aios.api.action_guard import enforce_action_boundary
from aios.api.deps import get_skill_repository
from aios.domain.learning.repository import SkillRepository

router = APIRouter(
    tags=["skill-library"], dependencies=[Depends(enforce_action_boundary)]
)


@router.get("/api/v1/skills")
def list_skills(
    repository: SkillRepository = Depends(get_skill_repository),
) -> dict[str, Any]:
    """List only persisted institutional skills."""
    items = [skill.model_dump(mode="json") for skill in repository.list_skills()]
    return {
        "items": items,
        "status": "available" if items else "empty",
        "source": "durable_repository",
    }
