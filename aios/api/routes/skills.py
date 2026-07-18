"""API routes for managing the Skill Library."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from aios.api.action_guard import enforce_action_boundary

router = APIRouter(tags=["skill-library"], dependencies=[Depends(enforce_action_boundary)])

@router.get("/api/v1/skills")
def list_skills() -> dict[str, Any]:
    """Retrieve the list of current skills and their applicability."""
    return {
        "skills": [
            {
                "id": "skill-python-debug",
                "name": "Python Debugging",
                "status": "ready",
                "applicability": ["python", "debugging", "backend"],
                "confidence_score": 0.95
            },
            {
                "id": "skill-react-ui",
                "name": "React UI Component Creation",
                "status": "ready",
                "applicability": ["react", "frontend", "ui"],
                "confidence_score": 0.88
            },
            {
                "id": "skill-sql-optimization",
                "name": "SQL Optimization",
                "status": "learning",
                "applicability": ["database", "performance", "sql"],
                "confidence_score": 0.45
            }
        ],
        "total_count": 3
    }
