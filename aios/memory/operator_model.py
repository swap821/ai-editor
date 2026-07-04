"""Render a structured snapshot of what the system knows about the operator.

Distinct from the self-model (which captures AI performance traits), this
module synthesises approved facts about the OPERATOR: preferences, attributes,
and project context. The output is consumed by system-prompt builders and
(future) frontend profile cards.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from aios.memory.facts import SemanticFacts


def render_operator_model(facts: SemanticFacts) -> dict[str, Any]:
    """Produce a structured snapshot grouped by subject category."""
    from aios.memory.db import get_connection, init_memory_db

    init_memory_db(facts.db_path)
    operator_facts = facts.facts_for("operator")
    project_facts = facts.facts_for("project")

    with get_connection(facts.db_path) as conn:
        attr_rows = conn.execute(
            "SELECT * FROM semantic_facts "
            "WHERE subject LIKE 'operator.%' AND status = 'active' "
            "ORDER BY id DESC",
        ).fetchall()

    preferences: list[dict[str, str]] = []
    attributes: dict[str, str] = {}
    project_context: list[dict[str, str]] = []

    for row in operator_facts:
        preferences.append({
            "predicate": str(row["predicate"]),
            "object": str(row["object"]),
        })

    for row in attr_rows:
        subject = str(row["subject"])
        attr_name = subject.removeprefix("operator.")
        attributes[attr_name] = str(row["object"])

    for row in project_facts:
        project_context.append({
            "predicate": str(row["predicate"]),
            "object": str(row["object"]),
        })

    return {
        "preferences": preferences,
        "attributes": attributes,
        "project_context": project_context,
    }
