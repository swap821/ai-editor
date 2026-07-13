"""Tests for the Slice 6 TurnCoordinator unification layer."""

from __future__ import annotations

import pytest

from aios.application.turns import TurnContext, TurnCoordinator, TurnMode


class TestModeClassification:
    """Mode classification must be deterministic and LLM-free."""

    @pytest.mark.parametrize(
        "directive,expected",
        [
            ("What is the weather today?", TurnMode.ADVISORY),
            ("Explain the router policy", TurnMode.ADVISORY),
            ("Summarize the last meeting", TurnMode.ADVISORY),
            ("Describe the architecture", TurnMode.ADVISORY),
            ("List all running containers", TurnMode.ADVISORY),
            ("Show me the logs", TurnMode.ADVISORY),
            ("Write a function to parse JSON", TurnMode.CONVERSATION),
            ("Create a new file", TurnMode.CONVERSATION),
            ("Run the test suite", TurnMode.CONVERSATION),
            ("Hello", TurnMode.CONVERSATION),
            ("", TurnMode.CONVERSATION),
        ],
    )
    def test_classify_mode(self, directive: str, expected: TurnMode) -> None:
        assert TurnCoordinator.classify_mode(directive) is expected

    def test_governance_takes_precedence(self) -> None:
        assert (
            TurnCoordinator.classify_mode("explain the router", governance_requested=True)
            is TurnMode.GOVERNANCE
        )

    def test_mission_takes_precedence_over_advisory(self) -> None:
        assert (
            TurnCoordinator.classify_mode("what is the weather", mission_requested=True)
            is TurnMode.MISSION
        )


class TestTurnContext:
    def test_turn_context_is_frozen_and_has_metadata(self) -> None:
        ctx = TurnContext(
            turn_id="t-1",
            session_id="s-1",
            operator_id="op",
            project_id="p",
            directive="hello",
            mode=TurnMode.CONVERSATION,
            model_id="qwen2.5-coder",
            approval_tokens=("tok1",),
        )
        assert ctx.turn_id == "t-1"
        assert ctx.session_id == "s-1"
        assert ctx.mode == TurnMode.CONVERSATION
        assert ctx.metadata == {}

    def test_turn_context_mode_values_are_strings(self) -> None:
        assert TurnMode.CONVERSATION.value == "conversation"
        assert TurnMode.MISSION.value == "mission"


class TestCoordinatorRegistration:
    def test_register_and_coordinate_conversation(self) -> None:
        coordinator = TurnCoordinator(deps=None)
        captured: list[TurnContext] = []

        @TurnCoordinator.register(TurnMode.CONVERSATION)
        async def conversation_handler(ctx: TurnContext, runtime):
            captured.append(ctx)
            yield {"type": "text_chunk", "text": "hi"}

        ctx = TurnContext(
            turn_id="t-1",
            session_id="s-1",
            operator_id=None,
            project_id=None,
            directive="hello",
            mode=TurnMode.CONVERSATION,
            model_id=None,
            approval_tokens=(),
        )
        result = coordinator.coordinate(ctx)
        assert result.context is ctx

        async def collect():
            return [e async for e in result.events]

        import asyncio

        events = asyncio.run(collect())
        assert events == [{"type": "text_chunk", "text": "hi"}]
        assert captured[0] is ctx

    def test_unregistered_mode_falls_back_to_conversation(self) -> None:
        coordinator = TurnCoordinator(deps=None)

        @TurnCoordinator.register(TurnMode.CONVERSATION)
        async def conversation_handler(ctx: TurnContext, runtime):
            yield {"type": "fallback", "mode": ctx.mode.value}

        ctx = TurnContext(
            turn_id="t-2",
            session_id="s-2",
            operator_id=None,
            project_id=None,
            directive="run a mission",
            mode=TurnMode.MISSION,
            model_id=None,
            approval_tokens=(),
        )
        result = coordinator.coordinate(ctx)

        async def collect():
            return [e async for e in result.events]

        import asyncio

        events = asyncio.run(collect())
        assert events == [{"type": "fallback", "mode": "mission"}]

    def test_no_handler_raises(self) -> None:
        # Clear handlers to force an error.
        original = dict(TurnCoordinator._mode_handlers)
        TurnCoordinator._mode_handlers.clear()
        coordinator = TurnCoordinator(deps=None)
        ctx = TurnContext(
            turn_id="t-3",
            session_id="s-3",
            operator_id=None,
            project_id=None,
            directive="hello",
            mode=TurnMode.CONVERSATION,
            model_id=None,
            approval_tokens=(),
        )
        with pytest.raises(RuntimeError, match="No conversation handler registered"):
            coordinator.coordinate(ctx)
        TurnCoordinator._mode_handlers.update(original)
