"""The payoff benchmark must show the model exactly what a live turn would.

`tools/learning_payoff.py` measures whether recalled memory helps, so its ON arm
has to carry recall in the SAME bytes the live turn path produces. It uses
`lessons_prompt_block` / `skills_prompt_block` from aios/api/turn_pipeline.py.

The live path (aios/application/turns/generate_pipeline.py) still builds the
same two blocks inline. It was not switched to call the shared functions,
deliberately: generate_pipeline.py is one of organ 32's production
entrypoints, and changing it re-opens organ 32's attestation -- which under a
squash merge has turned master red twice this week. A differential test buys
the same guarantee without that cost.

This is not a text comparison. It EXECUTES the live path's own expression,
lifted from its source by the AST, against the same inputs as the shared
function, and demands identical output. Rename a variable and it still passes;
change a single character of what the model sees, on either side, and it fails.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from aios.api.turn_pipeline import lessons_prompt_block, skills_prompt_block

LIVE = (
    Path(__file__).resolve().parents[1] / "aios/application/turns/generate_pipeline.py"
)

LESSONS = [
    {
        "verification_status": "verified",
        "error_type": "AssertionError",
        "lesson_text": "pin the list order",
    },
    {"error_type": "ImportError", "lesson_text": "import from the module path shown"},
]
SKILLS = [
    {
        "goal_pattern": "pin the behaviour of a::f",
        "steps": ["read_file", "create_file", "verify"],
        "success_rate": 0.8,
    },
    {"goal_pattern": "run the suite", "steps": ["verify"], "success_rate": 1.0},
]


def _live_expression(assigned_name: str) -> str:
    """The source of the expression the live path assigns to *assigned_name*."""
    source = LIVE.read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(source)):
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == assigned_name
        ):
            segment = ast.get_source_segment(source, node.value)
            if segment and (
                "RELEVANT LESSONS" in segment or "VERIFIED REUSABLE" in segment
            ):
                # Re-parenthesised: the live code wraps a multi-line expression
                # in parens that belong to the Assign, not to node.value, so the
                # lifted segment's continuation lines would read as indentation.
                return f"({segment})"
    pytest.fail(
        f"could not find the live path's `{assigned_name} = ...` recall block in "
        f"{LIVE.name}. If it moved or now calls the shared function, update this "
        "test -- do not delete it."
    )


def test_the_lessons_block_is_byte_identical() -> None:
    live = eval(_live_expression("block"), {}, {"lessons": LESSONS})  # noqa: S307 - our own source
    assert live == lessons_prompt_block(LESSONS)


def test_the_skills_block_is_byte_identical() -> None:
    live = eval(  # noqa: S307 - our own source
        _live_expression("skill_block"), {}, {"recalled_skills": SKILLS}
    )
    assert live == skills_prompt_block(SKILLS)


def test_the_alarm_can_actually_ring() -> None:
    """The negative control: a one-character drift must be caught."""
    drifted = _live_expression("block").replace("RELEVANT LESSONS", "RELEVANT LESSON")
    assert eval(drifted, {}, {"lessons": LESSONS}) != lessons_prompt_block(LESSONS)  # noqa: S307
