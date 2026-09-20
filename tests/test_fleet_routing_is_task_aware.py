"""Many models, each on the work it was built for — and proof it isn't a claim.

The router has always accepted five task classes (``_VALID_ROUTER_TASKS`` in the
frozen ``aios/security/limits.py``): coding, reasoning, research, vision,
long_context. Three of them were unreachable in two different ways at once:

* ``infer_task`` could only ever return coding / reasoning / general, so nothing
  could ask for research, vision, or long_context;
* ``_normalise_task`` clamps anything outside its own ``TASKS`` tuple to
  ``coding``, so even a hand-passed ``research`` was silently re-labelled — and
  its calibration evidence filed under coding, poisoning the very metrics meant
  to teach the router which model performs where.

And on the cloud side, ``cloud_capability`` returned ONE number per model used
for all five classes, so a code-specialised model and a reasoning model ranked
identically for every job. "Route each model to the task it was designed for"
could not be expressed at all.

The load-bearing test here is the reachability guard: a task class no input can
produce is not a feature, it is a claim. The rest pin that the new affinity
signal is small enough to stay a tiebreak and never become a policy.
"""

from __future__ import annotations

import pytest

from aios.core import router
from aios.core.catalog import (
    TASK_AFFINITY_BONUS,
    _KIND_TOKENS,
    model_kind,
    task_affinity,
)
from aios.core.model_selector import (
    LONG_CONTEXT_CHARS,
    TASKS,
    _normalise_task,
    infer_task,
)
from aios.security.limits import ROUTER_CLOUD_TASKS  # noqa: F401  (documents the gate)
from aios.security.limits import _VALID_ROUTER_TASKS


class TestEveryRouterTaskIsReachable:
    """The guard. Everything else in this file is downstream of it."""

    def test_every_valid_router_task_can_be_produced_by_some_input(self) -> None:
        produced = {
            infer_task("fix the bug in main.py"),
            infer_task("why should i use a queue here"),
            infer_task("look up the release notes"),
            infer_task("describe this", has_images=True),
            infer_task("summarise", context_chars=LONG_CONTEXT_CHARS),
        }
        missing = set(_VALID_ROUTER_TASKS) - produced
        assert not missing, (
            f"task classes the router accepts but no input can produce: {missing}. "
            "A declared-but-unreachable branch is not a feature."
        )

    def test_no_router_task_is_clamped_away_by_normalisation(self) -> None:
        """`_normalise_task` silently rewrote three of them to `coding`."""
        for task in sorted(_VALID_ROUTER_TASKS):
            assert _normalise_task(task) == task, (
                f"{task!r} was normalised to {_normalise_task(task)!r} — its "
                "routing decision and its calibration evidence both land under "
                "the wrong class"
            )

    def test_an_unknown_task_still_falls_back_to_coding(self) -> None:
        """Widening the vocabulary must not remove the fail-safe."""
        assert _normalise_task("banana") == "coding"
        assert _normalise_task(None) == "coding"

    def test_general_and_fast_remain_outside_the_cloud_vocabulary(self) -> None:
        """Stated, not assumed.

        `_env_router_tasks` DROPS unrecognised entries, so these two can never
        be made cloud-eligible by configuration. That is a defensible default —
        ordinary chat stays on the machine — but it is a property worth pinning
        so nobody later reads their absence as an oversight and 'fixes' it.
        """
        assert "general" not in _VALID_ROUTER_TASKS
        assert "fast" not in _VALID_ROUTER_TASKS
        assert {"general", "fast"} <= set(TASKS)


class TestTheMeasuredSignalsBeatTheSpokenOnes:
    """Vision and long-context are facts about the input, not words in it."""

    def test_vision_requires_an_actual_image(self) -> None:
        assert infer_task("look at this screenshot and tell me what broke") != "vision"
        assert infer_task("what is this", has_images=True) == "vision"

    def test_long_context_requires_actual_length(self) -> None:
        assert infer_task("summarise this enormous file for me") != "long_context"
        assert (
            infer_task("summarise", context_chars=LONG_CONTEXT_CHARS) == "long_context"
        )

    def test_a_long_pasted_body_counts_even_without_a_context_measure(self) -> None:
        assert infer_task("x" * (LONG_CONTEXT_CHARS + 1)) == "long_context"

    def test_an_image_wins_over_everything_else(self) -> None:
        """A screenshot of a stack trace is still a vision turn."""
        assert infer_task("fix the bug in main.py", has_images=True) == "vision"

    def test_research_is_distinguished_from_reasoning(self) -> None:
        """Both are 'think about it'; only one says the answer is outside."""
        assert infer_task("compare these two designs") == "reasoning"
        assert infer_task("find out which version shipped that") == "research"

    def test_existing_behaviour_is_unchanged_for_the_old_classes(self) -> None:
        assert infer_task("edit app.py and run pytest") == "coding"
        assert infer_task("hello there") == "general"
        assert infer_task("") == "general"
        assert infer_task(None) == "general"


class TestAffinityIsKeyedOnTasksNotFamilies:
    def test_every_affinity_key_is_a_real_task(self) -> None:
        """The first version keyed this on 'coder' and never fired once.

        The task class is 'coding'; the equality check in `task_affinity`
        compared it against 'coder' and silently returned 0 for everything — a
        table that looks like a feature and does nothing.
        """
        unknown = set(_KIND_TOKENS) - set(TASKS)
        assert not unknown, f"affinity keyed on non-tasks: {unknown}"

    @pytest.mark.parametrize(
        "model_id,expected",
        [
            ("qwen.qwen3-coder-480b-a35b", "coding"),
            ("mistral.devstral-2-123b", "coding"),
            ("deepseek.r1-distill-70b", "reasoning"),
            ("kimi-k2-thinking", "reasoning"),
            ("qwen2.5-vl-72b", "vision"),
            ("us.anthropic.claude-opus-4", "general"),
        ],
    )
    def test_a_model_is_read_for_what_it_advertises(self, model_id, expected) -> None:
        assert model_kind(model_id) == expected

    def test_affinity_is_a_bonus_and_never_a_penalty(self) -> None:
        """An id saying 'coder' is not evidence it is WORSE at reasoning.

        A penalty would be a claim the model id does not make and this module
        has no evidence for; evidence-based re-ranking is calibration's job.
        """
        assert task_affinity("qwen3-coder-480b", "reasoning") == 0
        assert task_affinity("qwen3-coder-480b", "coding") == TASK_AFFINITY_BONUS
        assert task_affinity("claude-opus-4", "coding") == 0

    def test_it_cannot_flip_a_local_versus_cloud_decision(self) -> None:
        """Privacy is the policy's call, not a heuristic's.

        A scoring nudge big enough to move a privacy boundary is a policy change
        wearing a heuristic's clothes.
        """
        assert TASK_AFFINITY_BONUS < router._LOCAL_BIAS

    def test_measured_evidence_outweighs_the_name(self) -> None:
        """Calibration is 240; affinity is 40. A guess read off an id must lose."""
        assert TASK_AFFINITY_BONUS < router._CALIBRATION_SCALE / 2


def _cloud(name: str, model: str, cap: int) -> router.Provider:
    return router.Provider(
        name=name,
        privacy=router.PRIVACY_CLOUD,
        cost=router.COST_LOW,
        available=True,
        models=(model,),
        capability=cap,
    )


class TestAffinityActuallyChangesTheRoute:
    """Otherwise it is one more number nobody reads."""

    POLICY = router.Policy(
        cloud_tasks=("coding", "reasoning"),
        max_cost=router.COST_HIGH,
        prefer_local=False,
    )

    def test_the_coder_wins_the_coding_task(self) -> None:
        picks = router.candidates(
            "coding",
            [
                _cloud("bedrock", "some-general-300b", 340),
                _cloud("openai", "some-coder-300b", 340),
            ],
            policy=self.POLICY,
        )
        assert picks[0].model == "some-coder-300b"

    def test_the_same_fleet_routes_reasoning_elsewhere(self) -> None:
        """The point of the whole exercise: one fleet, different jobs."""
        picks = router.candidates(
            "reasoning",
            [
                _cloud("bedrock", "some-thinking-300b", 340),
                _cloud("openai", "some-coder-300b", 340),
            ],
            policy=self.POLICY,
        )
        assert picks[0].model == "some-thinking-300b"

    def test_a_big_capability_gap_still_beats_affinity(self) -> None:
        """Affinity is a tiebreak, not an override — 40 points, not 400."""
        picks = router.candidates(
            "coding",
            [
                _cloud("bedrock", "frontier-general", 360),
                _cloud("openai", "tiny-coder", 250),
            ],
            policy=self.POLICY,
        )
        assert picks[0].model == "frontier-general"


class TestModelsForFallback:
    def test_a_provider_without_a_task_list_behaves_exactly_as_before(self) -> None:
        prov = router.Provider(
            name="bedrock",
            privacy=router.PRIVACY_CLOUD,
            cost=router.COST_LOW,
            available=True,
            models=("a", "b"),
        )
        assert prov.models_for("coding") == ("a", "b")
        assert prov.models_for("anything-at-all") == ("a", "b")

    def test_a_declared_task_list_wins_for_that_task_only(self) -> None:
        prov = router.Provider(
            name="bedrock",
            privacy=router.PRIVACY_CLOUD,
            cost=router.COST_LOW,
            available=True,
            models=("general-1",),
            models_by_task={"coding": ("coder-1",)},
        )
        assert prov.models_for("coding") == ("coder-1",)
        assert prov.models_for("reasoning") == ("general-1",)

    def test_an_empty_task_list_falls_back_rather_than_vanishing(self) -> None:
        """Returning () would silently drop a provider from the whole fleet."""
        prov = router.Provider(
            name="bedrock",
            privacy=router.PRIVACY_CLOUD,
            cost=router.COST_LOW,
            available=True,
            models=("general-1",),
            models_by_task={"coding": ()},
        )
        assert prov.models_for("coding") == ("general-1",)


class TestTheLiveTurnPathSuppliesTheMeasuredSignals:
    """Reachable in principle is not reachable in production.

    `infer_task` gained `has_images` and `context_chars`, but the turn path
    called it with only the user's text — so vision and long_context would have
    stayed unreachable anyway, which is the same declared-but-unreachable defect
    one layer up.
    """

    def test_context_chars_counts_the_whole_history(self) -> None:
        from aios.api.main import _message_context_chars

        messages = [
            {"role": "user", "content": [{"text": "a" * 100}]},
            {"role": "assistant", "content": "b" * 50},
            {"role": "user", "content": [{"text": "c" * 25}, {"text": "d" * 25}]},
        ]
        assert _message_context_chars(messages) == 200

    def test_a_long_conversation_is_long_context_even_with_a_short_last_turn(
        self,
    ) -> None:
        """Three words on top of a huge history is still a long-context problem."""
        from aios.api.main import _message_context_chars

        history = [{"role": "user", "content": [{"text": "x" * LONG_CONTEXT_CHARS}]}]
        assert (
            infer_task("and now?", context_chars=_message_context_chars(history))
            == "long_context"
        )

    def test_image_detection_finds_a_real_block(self) -> None:
        from aios.api.main import _messages_have_images

        assert _messages_have_images(
            [{"role": "user", "content": [{"text": "hi"}, {"image": {"bytes": "..."}}]}]
        )

    def test_image_detection_is_false_for_text_only(self) -> None:
        from aios.api.main import _messages_have_images

        assert not _messages_have_images(
            [{"role": "user", "content": [{"text": "look at this screenshot"}]}]
        )
        assert not _messages_have_images([{"role": "user", "content": "plain string"}])

    def test_malformed_content_does_not_raise(self) -> None:
        """Turn routing must never be the thing that breaks a request."""
        from aios.api.main import _message_context_chars, _messages_have_images

        junk = [
            {"role": "user"},
            {"role": "user", "content": None},
            {"role": "user", "content": [None, 5, {"text": None}]},
        ]
        assert _message_context_chars(junk) == 0
        assert _messages_have_images(junk) is False
