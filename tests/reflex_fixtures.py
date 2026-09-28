"""A test stand-in for the operator's activation, for reflex MECHANISM tests.

Since Phase 2 slice 2.4c-B a reflex compiles and replays only from a skill the
operator activated in the institutional library. The cerebellum asks its gate
two questions: ``active_procedures()`` (which skills are activated, with which
steps) and ``successes(skill_id)`` (the library's evidence count, which the
retire rule compares). Production answers them from the library
(``InstitutionalSkillAdapter``).

Tests of matching, replay, decompilation and file confirmation need a compiled
reflex and nothing about how it was activated, so this answers the same two
questions from a dict. Tests of the gate ITSELF -- what activates, what
demotes -- use the real library instead (``tests/test_phase2_reflex_gate.py``).
"""

from __future__ import annotations

from typing import Any

from aios.core.cerebellum import Cerebellum


class ActivatedSkills:
    """The gate's contract, answered from a dict. Ids are allocated here."""

    def __init__(self) -> None:
        self._entries: dict[int, dict[str, Any]] = {}
        self._counts: dict[int, int] = {}
        self._next_id = 1

    def activate(
        self,
        goal: str,
        steps: list[str],
        *,
        successes: int = 3,
        sig_v2: str = "sig_test",
        activated: bool = True,
    ) -> int:
        skill_id = self._next_id
        self._next_id += 1
        self._counts[skill_id] = successes
        if activated:
            self._entries[skill_id] = {
                "goal_pattern": goal,
                "steps": list(steps),
                "success_count": successes,
                "signature_v2": sig_v2,
            }
        return skill_id

    def deactivate(self, skill_id: int) -> None:
        self._entries.pop(skill_id, None)

    def earn(self, skill_id: int, times: int = 1) -> None:
        self._counts[skill_id] = self._counts.get(skill_id, 0) + times
        if skill_id in self._entries:
            self._entries[skill_id]["success_count"] = self._counts[skill_id]

    # -- the gate's contract ------------------------------------------------ #

    def active_procedures(self) -> dict[int, dict[str, Any]]:
        return {k: dict(v) for k, v in self._entries.items()}

    def successes(self, skill_id: int) -> int | None:
        return self._counts.get(int(skill_id))


def gated(gate: ActivatedSkills, *args: Any, **kwargs: Any) -> Cerebellum:
    """A cerebellum wired as bootstrap wires one: with its gate attached."""
    cerebellum = Cerebellum(*args, **kwargs)
    cerebellum.attach_reflex_gate(gate)
    return cerebellum
