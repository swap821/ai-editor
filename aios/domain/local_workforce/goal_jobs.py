"""The clerk's goal jobs, triage and briefing: each asked one way.

README step 3: "the local clerk classifies the task and prepares a briefing".
GAGOS's hour asks the clerk these two jobs about each of the operator's goals
(``aios.maintenance.goal_intake``), and organ 37's qualification suite asks the
same jobs to decide which model may be granted them. Both build the prompt
HERE and read the answer HERE, as ``skill_selection`` does for the reuse job,
so qualifying measures exactly the job GAGOS asks (2026-11-11, the operator's
one-system plan, phase 1).

The clerk is advisory: a triage or a briefing decides no authority.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

SEVERITIES = ("low", "medium", "high")
AREAS = ("frontend", "backend", "docs", "security")

#: The job runner's declared output (``LocalWorkforceService``): it refuses
#: any field outside these and checks the scalar types; the rest is read here.
TRIAGE_SCHEMA: Mapping[str, str] = {
    "severity": "str",
    "area": "str",
    "escalate": "bool",
}
BRIEFING_SCHEMA: Mapping[str, str] = {
    "goal": "str",
    "files": "list",
    "constraints": "list",
    "done_when": "str",
}


def triage_prompt(item: str) -> str:
    """The triage question about *item* (a goal, or a failure report)."""
    return (
        f"Triage this for GAGOS's operator: '{item}'. Return exactly JSON with "
        "severity (low, medium or high), area (frontend, backend, docs or "
        "security) and escalate (true when a frontier brain or the operator "
        "must look before any change)."
    )


def briefing_prompt(request: str, context: str = "") -> str:
    """The briefing question about *request*; *context* is beside it, never
    part of what the briefing may carry."""
    return (
        f"Prepare a briefing for a stronger model from this request: '{request}'. "
        + (f"{context.strip()} " if context.strip() else "")
        + "Return exactly JSON with goal (one sentence), files (the file paths "
        "the request names, exactly as written, in order), constraints (a "
        "list) and done_when (text). Use only facts in the request."
    )


#: What organ 37's qualification asks of these jobs, and the answers a model
#: must give: here, beside the jobs, so every stand-in model (tests, the R15
#: runtime proof) answers exactly the cases the suite asks, as
#: ``skill_selection.qualification_fixture_answer`` does for the reuse job.
TRIAGE_ESCALATES = (
    "test_login_rejects_expired_token fails: an expired session token was "
    "accepted (aios/identity/service.py)"
)
TRIAGE_ROUTINE = (
    "no-unused-vars: the variable unusedTimer is assigned but never used in "
    "frontend/src/workbench/FileTree.jsx"
)
ESCALATES_ANSWER: Mapping[str, Any] = {
    "severity": "high",
    "area": "security",
    "escalate": True,
}
ROUTINE_ANSWER: Mapping[str, Any] = {
    "severity": "low",
    "area": "frontend",
    "escalate": False,
}
BRIEFING_FILES = (
    "frontend/src/workbench/RecentActivity.tsx",
    "frontend/src/workbench/RecentActivity.test.tsx",
)
BRIEFING_REQUEST = (
    "The Recent activity panel in frontend/src/workbench/RecentActivity.tsx "
    "shows closed results twice. Fix it without touching the backend. Done when "
    "frontend/src/workbench/RecentActivity.test.tsx passes."
)
BRIEFING_ANSWER: Mapping[str, Any] = {
    "goal": "Stop the Recent activity panel showing closed results twice.",
    "files": list(BRIEFING_FILES),
    "constraints": ["Do not touch the backend."],
    "done_when": "frontend/src/workbench/RecentActivity.test.tsx passes",
}


def qualification_fixture_answer(prompt: str) -> str | None:
    """The correct answer to a triage or briefing qualification prompt, for a
    deterministic stand-in model; None for any other prompt."""
    if triage_prompt(TRIAGE_ESCALATES) in prompt:
        return json.dumps(dict(ESCALATES_ANSWER))
    if triage_prompt(TRIAGE_ROUTINE) in prompt:
        return json.dumps(dict(ROUTINE_ANSWER))
    if f"from this request: '{BRIEFING_REQUEST}'" in prompt:
        return json.dumps(dict(BRIEFING_ANSWER))
    return None


def _text_list(value: Any) -> bool:
    return isinstance(value, list) and all(
        isinstance(item, str) and item.strip() for item in value
    )


def read_triage(data: Mapping[str, Any]) -> tuple[bool, str]:
    """Whether *data* is a triage: exactly its fields, each one of its values."""
    if set(data) != set(TRIAGE_SCHEMA):
        return False, f"expected exact fields {sorted(TRIAGE_SCHEMA)}"
    if data.get("severity") not in SEVERITIES:
        return False, f"severity must be one of {list(SEVERITIES)}"
    if data.get("area") not in AREAS:
        return False, f"area must be one of {list(AREAS)}"
    if not isinstance(data.get("escalate"), bool):
        return False, "escalate must be true or false"
    return True, ""


def read_briefing(data: Mapping[str, Any]) -> tuple[bool, str]:
    """Whether *data* is a briefing: exactly its fields, the goal and done_when
    non-empty text, files and constraints lists of non-empty text."""
    if set(data) != set(BRIEFING_SCHEMA):
        return False, f"expected exact fields {sorted(BRIEFING_SCHEMA)}"
    for field in ("goal", "done_when"):
        value = data.get(field)
        if not isinstance(value, str) or not value.strip():
            return False, f"{field} must be non-empty text"
    if not _text_list(data.get("files")) or not data.get("files"):
        return False, "files must be a non-empty list of paths"
    if not _text_list(data.get("constraints")):
        return False, "constraints must be a list of non-empty text"
    return True, ""


__all__ = [
    "AREAS",
    "BRIEFING_ANSWER",
    "BRIEFING_FILES",
    "BRIEFING_REQUEST",
    "BRIEFING_SCHEMA",
    "ESCALATES_ANSWER",
    "ROUTINE_ANSWER",
    "SEVERITIES",
    "TRIAGE_ESCALATES",
    "TRIAGE_ROUTINE",
    "TRIAGE_SCHEMA",
    "briefing_prompt",
    "qualification_fixture_answer",
    "read_briefing",
    "read_triage",
    "triage_prompt",
]
