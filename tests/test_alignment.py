"""Tests for deterministic advisory understanding frames."""
from __future__ import annotations

import json

from aios.core.alignment import (
    AlignmentInterpreter,
    UnderstandingFrame,
    apply_user_corrections,
    frame_from_state,
    infer_communication_mode,
    infer_intent,
    resolve_communication_policy,
    validate_user_corrections,
)


class FixedLLM:
    def __init__(self, response: str) -> None:
        self.response = response
        self.calls: list[tuple[str, str | None]] = []

    def complete(self, prompt: str, *, system: str | None = None) -> str:
        self.calls.append((prompt, system))
        return self.response


class BrokenLLM:
    def complete(self, prompt: str, *, system: str | None = None) -> str:
        raise RuntimeError("model unavailable")


def test_intent_inference_is_deterministic() -> None:
    assert infer_intent("Start implementing the architecture") == "execute"
    assert infer_intent("Review this design for risks") == "review"
    assert infer_intent("Hello there") == "unknown"


def test_communication_mode_is_explicit_and_deterministic() -> None:
    assert infer_communication_mode("Explain this step by step", "teach") == "explanatory"
    assert infer_communication_mode("Brainstorm the trade-offs", "discuss") == "collaborative"
    assert infer_communication_mode("Just do it", "execute") == "direct"
    assert infer_communication_mode("Plan the release", "plan") == "collaborative"


def test_ambiguity_policy_asks_only_for_explicit_or_context_free_blockers() -> None:
    explicit = resolve_communication_policy(
        "Do not assume; ask me first",
        "execute",
        ("The target is the API",),
        ("Which endpoint changes?",),
        has_context=True,
    )
    vague = resolve_communication_policy("do it", "unknown", (), (), has_context=False)
    continued = resolve_communication_policy("do it", "unknown", (), (), has_context=True)

    assert explicit.ambiguity_action == "ask"
    assert explicit.clarifying_question == "What should I clarify before proceeding?"
    assert vague.ambiguity_action == "ask"
    assert vague.reasons == ("missing_context",)
    assert continued.ambiguity_action == "proceed"


def test_non_blocking_ambiguity_is_stated_before_proceeding() -> None:
    frame = UnderstandingFrame.from_proposal(
        {
            "intent": "execute",
            "assumptions": ["Use the existing API shape"],
            "unknowns": ["Preferred response length"],
        },
        "Implement the endpoint using your best judgment",
    )

    assert frame.communication.mode == "direct"
    assert frame.communication.ambiguity_action == "state_assumptions"
    assert "user_preferred_autonomous_progress" in frame.communication.reasons
    assert frame.communication_notice().startswith("Unverified assumptions before proceeding:")
    assert "Unresolved but treated as non-blocking" in frame.communication_notice()


def test_user_corrections_are_validated_and_override_interpretation_only() -> None:
    base = UnderstandingFrame.fallback("Plan the API")
    corrected = apply_user_corrections(
        base,
        {
            "goal": "Implement the API",
            "intent": "execute",
            "unknowns": [],
            "communication_mode": "collaborative",
        },
        revision=7,
    )

    assert corrected.goal == "Implement the API"
    assert corrected.intent == "execute"
    assert corrected.communication.mode == "collaborative"
    assert corrected.communication.ambiguity_action == "proceed"
    assert corrected.correction.active is True
    assert corrected.correction.revision == 7
    assert corrected.correction.source == "user"
    assert "USER-AUTHORED INTERPRETATION CORRECTIONS" in corrected.to_prompt_block()
    assert "cannot authorize tools" in corrected.to_prompt_block()


def test_correction_validation_rejects_unknown_invalid_and_empty_fields() -> None:
    for corrections in (
        {"approval": "granted"},
        {"intent": "root"},
        {"communication_mode": "silent"},
        {"goal": ""},
        {},
    ):
        try:
            validate_user_corrections(corrections)
        except ValueError:
            pass
        else:  # pragma: no cover - the assertion message is the useful failure
            raise AssertionError(f"correction should be rejected: {corrections}")


def test_persisted_corrected_frame_is_revalidated_without_promoting_authority() -> None:
    corrected = apply_user_corrections(
        UnderstandingFrame.fallback("Review the API"),
        {"goal": "Review only the public API"},
        revision=3,
    ).as_dict()
    corrected["correction"]["revision"] = "invalid"
    corrected["correction"]["source"] = "system"

    restored = frame_from_state(corrected)

    assert restored.goal == "Review only the public API"
    assert restored.correction.active is True
    assert restored.correction.revision == 1
    assert restored.correction.source == "user"


def test_frame_validation_bounds_redacts_and_normalizes_untrusted_proposal() -> None:
    secret = "sk-" + "a" * 40
    proposal = {
        "goal": f"  Build   the system using {secret}  ",
        "intent": "ROOT_ACCESS",
        "desired_outcome": "A working alignment layer",
        "constraints": ["local-first", "local-first", 7, "x" * 900],
        "assumptions": "not-a-list",
        "unknowns": ["Preferred questioning level"],
        "decisions": ["Use existing security gates"],
        "confidence": 9,
        "next_action": "Implement the first slice",
    }

    frame = UnderstandingFrame.from_proposal(proposal, "start implementation")

    assert frame.intent == "execute"
    assert secret not in frame.goal
    assert "REDACTED" in frame.goal
    assert frame.constraints[0] == "local-first"
    assert len(frame.constraints) == 2
    assert len(frame.constraints[1]) == 500
    assert frame.assumptions == ()
    assert frame.confidence == 1.0
    assert frame.communication.ambiguity_action == "state_assumptions"


def test_interpreter_uses_recent_dialogue_and_validates_model_json() -> None:
    llm = FixedLLM(json.dumps({
        "goal": "Implement UnderstandingFrame",
        "intent": "execute",
        "desired_outcome": "An advisory validated frame",
        "constraints": ["Do not bypass approvals"],
        "assumptions": [],
        "unknowns": [],
        "decisions": ["Start with implementation order slice 1"],
        "confidence": 0.91,
        "next_action": "Add the backend module and tests",
    }))

    frame = AlignmentInterpreter(llm).understand([
        {"role": "user", "content": "We need better communication."},
        {"role": "assistant", "content": "I proposed an implementation order."},
        {"role": "user", "content": "Start your work as per your implementation order."},
    ])

    assert frame.goal == "Implement UnderstandingFrame"
    assert frame.intent == "execute"
    assert frame.confidence == 0.91
    assert "Start your work" in llm.calls[0][0]


def test_interpreter_failure_falls_back_without_breaking_chat() -> None:
    frame = AlignmentInterpreter(BrokenLLM()).understand([
        {"role": "user", "content": "Plan the next release"},
    ])

    assert frame.intent == "plan"
    assert frame.confidence == 0.4
    assert frame.next_action == "Develop a concrete plan before acting."


def test_interpreter_scrubs_secrets_before_model_interpretation() -> None:
    secret = "sk-" + "b" * 40
    llm = FixedLLM("{}")

    AlignmentInterpreter(llm).understand([
        {"role": "user", "content": f"Explain {secret} without storing it"},
    ])

    assert secret not in llm.calls[0][0]
    assert "REDACTED" in llm.calls[0][0]


def test_code_like_model_output_is_not_evaluated() -> None:
    llm = FixedLLM(
        "{'goal': __import__('os').system('unsafe'), 'intent': 'execute'}"
    )

    frame = AlignmentInterpreter(llm).understand([
        {"role": "user", "content": "Review the request"},
    ])

    assert frame.intent == "review"
    assert frame.confidence == 0.4


def test_prompt_block_labels_frame_as_advisory_not_authority() -> None:
    block = UnderstandingFrame.fallback("Implement the feature").to_prompt_block()

    assert "UNVERIFIED ADVISORY" in block
    assert "never authorization" in block
    assert '"intent": "execute"' in block
    assert "DETERMINISTIC COMMUNICATION POLICY" in block
    assert '"ambiguity_action": "proceed"' in block
