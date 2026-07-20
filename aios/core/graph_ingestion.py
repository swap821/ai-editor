"""Cross-store ingestion for the knowledge graph.

Pure extraction functions: verified record in, (S, P, O, confidence) tuples
out. Each tuple is a candidate edge for SemanticFacts.add_fact(). The caller
decides when to ingest (typically on promotion/verification). The functions
never access the DB directly — they transform data structures, nothing more.
"""

from __future__ import annotations

import re

from aios.memory.relevance import tokens

_TOOL_VERBS = frozenset(
    {
        "read_file",
        "read_directory",
        "execute_terminal",
        "create_file",
        "edit_file",
        "verify",
    }
)

_PATH_LIKE = re.compile(
    r"[a-zA-Z_][\w./\\-]*\.(?:py|ts|tsx|js|jsx|json|md|sql|yml|yaml|toml|cfg)"
)
_QUOTED = re.compile(r"['\"`]([^'\"`]{2,60})['\"`]")
_GOAL_TARGET = re.compile(
    r"\b(?:for|of|in|to|on)\s+(?:the\s+)?([A-Za-z_][\w.-]{1,40})",
    re.IGNORECASE,
)


def find_entities(text: str) -> list[str]:
    """Extract candidate entity names from text. Deterministic, no LLM."""
    entities: list[str] = []
    seen: set[str] = set()

    def _add(raw: str) -> None:
        clean = raw.strip().strip(".,;:!?\"'`()[]{}").strip()
        if len(clean) < 2 or clean.lower() in seen:
            return
        seen.add(clean.lower())
        entities.append(clean)

    for m in _PATH_LIKE.finditer(text):
        _add(m.group(0))
        stem = m.group(0).rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
        stem = stem.rsplit(".", 1)[0]
        if len(stem) >= 2:
            _add(stem)

    for m in _QUOTED.finditer(text):
        _add(m.group(1))

    for m in _GOAL_TARGET.finditer(text):
        candidate = m.group(1)
        if candidate.lower() not in {"the", "a", "an", "this", "that", "it"}:
            _add(candidate)

    return entities


def edges_from_skill(
    goal_pattern: str,
    steps: list[str],
    *,
    success_rate: float = 1.0,
) -> list[tuple[str, str, str, float]]:
    """Extract (S, P, O, confidence) edges from a verified skill."""
    conf = max(0.5, min(1.0, success_rate))
    edges: list[tuple[str, str, str, float]] = []
    goal_entities = find_entities(goal_pattern)

    step_targets: list[str] = []
    for step in steps:
        if ":" not in step:
            continue
        tool, _, arg = step.partition(":")
        tool = tool.strip().lower()
        arg = arg.strip()
        if tool not in _TOOL_VERBS or not arg:
            continue

        arg_entities = find_entities(arg)
        for entity in arg_entities:
            step_targets.append(entity)
            if tool in ("read_file", "read_directory"):
                edges.append((entity, "read_in_workflow", goal_pattern[:60], conf))
            elif tool == "create_file":
                edges.append((entity, "created_in_workflow", goal_pattern[:60], conf))
            elif tool in ("execute_terminal", "verify"):
                cmd_stem = arg.split()[0] if arg.split() else arg[:30]
                edges.append((entity, "verified_by", cmd_stem, conf))

    for ge in goal_entities[:3]:
        for st in step_targets[:5]:
            if ge.lower() != st.lower():
                edges.append((ge, "associated_with", st, conf))

    return edges


def edges_from_mistake(
    error_type: str,
    root_cause: str,
    lesson_text: str,
) -> list[tuple[str, str, str, float]]:
    """Extract (S, P, O, confidence) edges from a verified mistake."""
    conf = 0.8
    edges: list[tuple[str, str, str, float]] = []

    if not error_type.strip():
        return edges

    cause_entities = find_entities(root_cause)
    for entity in cause_entities[:3]:
        edges.append((error_type, "caused_by", entity, conf))

    lesson_entities = find_entities(lesson_text)
    for entity in lesson_entities[:3]:
        edges.append((error_type, "prevented_by", entity, conf))

    return edges


def edges_from_outcome(
    task_text: str,
    outcome: str,
    tool_calls: int,
) -> list[tuple[str, str, str, float]]:
    """Extract (S, P, O, confidence) edges from a verified development outcome."""
    if outcome not in ("verified_success", "verified_failure"):
        return []

    conf = 1.0 if outcome == "verified_success" else 0.7
    predicate = (
        "has_verified_success"
        if outcome == "verified_success"
        else "has_verified_failure"
    )

    entities = find_entities(task_text)
    return [(entity, predicate, "true", conf) for entity in entities[:3]]
