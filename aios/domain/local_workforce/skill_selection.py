"""The clerk's skill-selection job: one question, asked one way.

"Does this verified skill apply here?" is the only job production code gives
the local clerk (``LearningService.attempt_local_reuse``). Until 2026-10-11:

* no qualification test covered it, so no model could ever earn the role and
  the job ALWAYS escalated (docs/PRODUCTION_HARDENING.md);
* the live prompt gave the clerk nothing to judge by -- not the skill's
  required inputs, its exclusions or its escalation conditions -- and embedded
  an example answer that already said ``"applicable": true``, so a model that
  copied the example passed.

Now the live caller and the qualification suite build the prompt HERE and
read the answer HERE, so qualifying measures exactly the job production asks.
The clerk only ever runs after the deterministic applicability engine has
admitted the skill: it can veto (escalate), never grant.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence

#: Below this the clerk's "applies" is not trusted and the job escalates.
MIN_CONFIDENCE = 0.8

FIELDS = ("applicable", "abstain", "required_inputs_present", "confidence", "reason")
#: The job's declared output schema. The job runner refuses an answer with any
#: field outside it -- the old live job declared 3 fields while its prompt asked
#: for 7, so an obedient model was always refused.
OUTPUT_SCHEMA: Mapping[str, str] = {
    "applicable": "bool",
    "abstain": "bool",
    "required_inputs_present": "bool",
    "confidence": "float",
    "reason": "str",
}


def skill_selection_prompt(
    *,
    problem_signature: str,
    required_inputs: Sequence[str],
    known_exclusions: Sequence[str],
    escalation_conditions: Sequence[str],
    inputs: Mapping[str, Any],
    state: Mapping[str, Any],
) -> str:
    """The question, with everything needed to answer it and no answer in it."""
    return (
        "Decide whether a verified skill applies to the current situation.\n"
        f"Skill purpose: {problem_signature}\n"
        f"Required inputs: {json.dumps(list(required_inputs))}\n"
        f"Known exclusions (the skill must NOT be used if any holds): "
        f"{json.dumps(list(known_exclusions))}\n"
        f"Escalate instead if: {json.dumps(list(escalation_conditions))}\n"
        f"Current inputs: {json.dumps(dict(inputs), sort_keys=True)}\n"
        f"Current state: {json.dumps(dict(state), sort_keys=True)}\n"
        "Respond with JSON holding exactly these fields: "
        '"applicable" (boolean), "abstain" (boolean: true when unsure or when an '
        'exclusion or escalation condition holds), "required_inputs_present" '
        '(boolean), "confidence" (number from 0 to 1), "reason" (short text).'
    )


@dataclass(frozen=True)
class SkillSelection:
    applicable: bool
    abstain: bool
    required_inputs_present: bool
    confidence: float
    reason: str

    def admits(self) -> bool:
        """Would production reuse the skill on this answer?"""
        return (
            self.applicable
            and not self.abstain
            and self.required_inputs_present
            and self.confidence >= MIN_CONFIDENCE
        )


def read_skill_selection(data: Any) -> Optional[SkillSelection]:
    """The clerk's answer, or None when it is not exactly the asked shape.
    Malformed is never read as a yes."""
    if not isinstance(data, Mapping) or set(data) != set(FIELDS):
        return None
    flags = (data["applicable"], data["abstain"], data["required_inputs_present"])
    if not all(isinstance(flag, bool) for flag in flags):
        return None
    confidence = data["confidence"]
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        return None
    if not 0.0 <= float(confidence) <= 1.0 or not isinstance(data["reason"], str):
        return None
    return SkillSelection(
        applicable=data["applicable"],
        abstain=data["abstain"],
        required_inputs_present=data["required_inputs_present"],
        confidence=float(confidence),
        reason=data["reason"],
    )


#: The qualification fixture: one skill, two situations. A model that always
#: says yes fails the second; one that always says no fails the first.
QUALIFICATION_SKILL: Mapping[str, Any] = {
    "problem_signature": "run the pin tests for one Python test file",
    "required_inputs": ["test_path"],
    "known_exclusions": ["the test file has been deleted"],
    "escalation_conditions": ["the tests need network access"],
}
APPLIES_SITUATION: Mapping[str, Mapping[str, Any]] = {
    "inputs": {"test_path": "tests/test_pin.py"},
    "state": {"test_file": "present", "network_needed": "no"},
}
EXCLUDED_SITUATION: Mapping[str, Mapping[str, Any]] = {
    "inputs": {"test_path": "tests/test_pin.py"},
    "state": {"test_file": "the test file has been deleted", "network_needed": "no"},
}


def qualification_prompt(situation: Mapping[str, Mapping[str, Any]]) -> str:
    return skill_selection_prompt(
        problem_signature=QUALIFICATION_SKILL["problem_signature"],
        required_inputs=QUALIFICATION_SKILL["required_inputs"],
        known_exclusions=QUALIFICATION_SKILL["known_exclusions"],
        escalation_conditions=QUALIFICATION_SKILL["escalation_conditions"],
        inputs=situation["inputs"],
        state=situation["state"],
    )


def check_applies(data: dict[str, Any]) -> tuple[bool, str]:
    answer = read_skill_selection(data)
    if answer is None:
        return False, f"not exactly the fields {list(FIELDS)} with their types"
    if not answer.admits():
        return False, "the skill applies and every input is present, but it was refused"
    return True, ""


def check_abstains(data: dict[str, Any]) -> tuple[bool, str]:
    answer = read_skill_selection(data)
    if answer is None:
        return False, f"not exactly the fields {list(FIELDS)} with their types"
    if answer.admits():
        return False, "a known exclusion holds, yet the skill was admitted"
    if not answer.required_inputs_present:
        return False, "the required input IS present; the exclusion is the reason"
    return True, ""


__all__ = [
    "APPLIES_SITUATION",
    "EXCLUDED_SITUATION",
    "FIELDS",
    "MIN_CONFIDENCE",
    "OUTPUT_SCHEMA",
    "QUALIFICATION_SKILL",
    "SkillSelection",
    "check_abstains",
    "check_applies",
    "qualification_prompt",
    "read_skill_selection",
    "skill_selection_prompt",
]
