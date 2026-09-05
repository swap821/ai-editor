"""Single coordinator for every human directive."""

from __future__ import annotations

import logging
import inspect
import re
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Callable, Optional

from aios.application.turns.turn_context import TurnContext, TurnMode
from aios.application.turns.turn_result import TurnResult

logger = logging.getLogger(__name__)


@dataclass
class RuntimeDeps:
    """Common runtime dependencies shared across turn modes.

    Routes populate this from their FastAPI dependencies and pass it to the
    coordinator.  The coordinator never builds dependencies itself, so tests can
    inject fakes without touching the HTTP layer.
    """

    llm_client: Optional[Any] = None
    chat_client: Optional[Any] = None
    bedrock: Optional[Any] = None
    gemini: Optional[Any] = None
    openai_client: Optional[Any] = None
    anthropic_client: Optional[Any] = None
    #: Vertex Model-as-a-Service (DeepSeek, gpt-oss). CLOUD brain, gated by
    #: the router policy's cloud_tasks exactly like every other cloud client.
    vertex_maas_client: Optional[Any] = None
    executor: Optional[Any] = None
    indexer: Optional[Any] = None
    reflector: Optional[Any] = None
    snapshot: Optional[Callable[..., object]] = None
    planner_llm: Optional[Any] = None
    approvals: Optional[Any] = None
    mistakes: Optional[Any] = None
    development: Optional[Any] = None
    skills: Optional[Any] = None
    swarm_patterns: Optional[Any] = None
    autonomy: Optional[Any] = None
    curriculum: Optional[Any] = None
    cerebellum: Optional[Any] = None
    native_planner: Optional[Any] = None
    consolidator: Optional[Any] = None
    conversation_state: Optional[Any] = None
    alignment_evaluation: Optional[Any] = None
    alignment_interpreter: Optional[Any] = None
    facts: Optional[Any] = None
    memory_authority: Optional[Any] = None
    compactor: Optional[Any] = None
    extra: dict[str, Any] = field(default_factory=dict)


ModeHandler = Callable[[TurnContext, RuntimeDeps], AsyncIterator[Any]]


StreamFactory = Callable[[TurnContext, RuntimeDeps], Any]
Preparer = Callable[[TurnContext, RuntimeDeps], None]


def _is_terminal_frame(event: Any) -> bool:
    """True when this SSE frame ends the turn.

    `done` maps to TURN_COMPLETED and `error` to TURN_FAILED (aios/api/main.py),
    so either means the turn reached a real conclusion and recorded its own
    outcome. Anything else -- including a stream that simply stops -- means it
    did not.
    """
    if isinstance(event, str):
        head = event[:64]
        return head.startswith("event: done") or head.startswith("event: error")
    if isinstance(event, dict):
        return event.get("type") in {"done", "error"} or event.get("event") in {
            "done",
            "error",
        }
    return False


class _StreamTurnHandler:
    """Adapt an existing route stream into the application handler contract.

    The legacy pipelines currently produce synchronous SSE iterators.  Keeping
    this adapter in the application layer lets the HTTP routes become thin
    coordinator adapters while the pipeline is split into smaller domain
    handlers in the next R5 slice.
    """

    def __init__(
        self,
        stream_factory: Optional[StreamFactory] = None,
        preparer: Optional[Preparer] = None,
    ) -> None:
        self._stream_factory = stream_factory
        self._preparer = preparer

    def prepare(self, context: TurnContext, runtime: RuntimeDeps) -> None:
        if self._preparer is not None:
            self._preparer(context, runtime)

    async def __call__(self, context: TurnContext, runtime: RuntimeDeps):
        stream_factory = self._stream_factory or runtime.extra.get("stream_factory")
        if stream_factory is None:
            raise RuntimeError(
                f"No stream factory registered for turn mode {context.mode.value}"
            )
        stream = stream_factory(context, runtime)
        if inspect.isawaitable(stream):
            stream = await stream

        # THE ABNORMAL PATH. This is the one generator every turn mode flows
        # through, and `main.py` hands it to `StreamingResponse` -- so Starlette
        # throws GeneratorExit in here on disconnect or cancellation. A turn
        # killed by a revocation therefore unwinds through this `finally` and
        # nowhere else: `stream_generate` has no `finally` of its own, and its
        # disposition recorder sits on the normal completion path.
        #
        # Organ 55's M4 caught the consequence. The emergency stop engaged with
        # work in flight, the turn died, and the ledger recorded NOTHING about
        # what became of it -- no `worker.work_incomplete`, no `turn.failed`.
        # "The ledger cannot say what happened" was a true finding.
        #
        # THE RULE IS "DID THE LATCH CLOSE DURING THIS TURN", not "did the turn
        # reach a terminal frame". An earlier version keyed on the terminal
        # frame to avoid double-recording, and that silently suppressed the
        # live case: cohorts 15 and 16 revoked authority while a turn was
        # genuinely mid-tool, the turn still reached a terminal frame, and
        # neither layer recorded anything. Reproduced directly --
        # abandoned-mid-flight recorded, ran-to-completion recorded nothing.
        #
        # Sampling the latch at both ends distinguishes the three cases that
        # matter: a revocation that landed DURING this turn (record), a turn
        # that merely ran while the system was already stopped (not this
        # turn's business), and an ordinary turn (nothing). Double-recording is
        # prevented properly, by making the emitter idempotent per turn id.
        #
        # Nothing here may change whether the turn runs, and nothing here may
        # raise -- an observation that breaks the stream is worse than a
        # missing one.
        try:
            from aios.application.governance.emergency_stop import latch_is_engaged

            latch_at_start = latch_is_engaged()
        except Exception:  # noqa: BLE001 - unknown latch state is not a claim
            latch_at_start = True  # fail closed: never invent a revocation

        try:
            if hasattr(stream, "__aiter__"):
                async for event in stream:
                    yield event
                return
            for event in stream:
                yield event
        finally:
            # DIAGNOSTIC, deliberately unconditional and at WARNING so it
            # survives the default log level. Five cohorts have now failed M4
            # with no trace of why: no recorder warning, no traceback, nothing.
            # Guessing from the ledger has been wrong five times, so this says
            # plainly whether this block runs at all and what it decided.
            try:
                from aios.application.governance.emergency_stop import (
                    latch_is_engaged as _probe,
                )

                logger.warning(
                    "turn disposition check: turn=%s latch_at_start=%s latch_now=%s",
                    getattr(context, "turn_id", "?"),
                    latch_at_start,
                    _probe(),
                )
            except Exception:  # noqa: BLE001 - diagnostics never break a turn
                logger.warning("turn disposition check: probe failed", exc_info=True)

            if not latch_at_start:
                try:
                    from aios.application.governance.emergency_stop import (
                        record_turn_incomplete_if_revoked,
                    )

                    record_turn_incomplete_if_revoked(
                        session_id=str(getattr(context, "session_id", "") or ""),
                        turn_id=str(getattr(context, "turn_id", "") or ""),
                    )
                except Exception:  # noqa: BLE001 - never break the stream
                    # Logged, not swallowed. A silent `except: pass` is how the
                    # cerebellum's missing bus stayed hidden for eleven cohorts;
                    # the disposition recorder must not repeat that.
                    logger.warning(
                        "Failed to record turn disposition on abnormal exit",
                        exc_info=True,
                    )


class ConversationTurnHandler(_StreamTurnHandler):
    """Production handler for ordinary conversational turns."""

    def __init__(
        self,
        stream_factory: Optional[StreamFactory] = None,
        preparer: Optional[Preparer] = None,
    ) -> None:
        if stream_factory is None:
            from aios.application.turns.conversation_pipeline import stream_conversation

            stream_factory = stream_conversation
        super().__init__(stream_factory, preparer)


class AdvisoryTurnHandler(_StreamTurnHandler):
    """Production handler for deterministic read-only/advisory turns."""


class MissionTurnHandler(_StreamTurnHandler):
    """Production handler for explicitly requested mission turns."""


class GovernanceTurnHandler(_StreamTurnHandler):
    """Production handler for explicitly requested governance turns."""


def production_handlers(
    stream_factory: Optional[StreamFactory] = None,
    *,
    preparer: Optional[Preparer] = None,
) -> dict[TurnMode, ModeHandler]:
    """Build the handler registry used by live HTTP turn adapters."""
    return {
        TurnMode.CONVERSATION: ConversationTurnHandler(stream_factory, preparer),
        TurnMode.ADVISORY: AdvisoryTurnHandler(stream_factory, preparer),
        TurnMode.MISSION: MissionTurnHandler(stream_factory, preparer),
        TurnMode.GOVERNANCE: GovernanceTurnHandler(stream_factory, preparer),
    }


class TurnCoordinatorAuthority:
    """Owns the lifecycle of one human directive.

    Routes keep their HTTP responsibilities (CORS, rate-limit headers, auth
    extraction). Everything else—session context, memory recall, mode
    classification, event shaping and outcome recording—lives here.
    """

    _mode_handlers: dict[TurnMode, ModeHandler] = {}

    def __init__(
        self,
        *,
        deps: Optional[RuntimeDeps],
        default_model: Optional[str] = None,
        handlers: Optional[dict[TurnMode, ModeHandler]] = None,
    ) -> None:
        self.runtime = deps or RuntimeDeps()
        self.default_model = default_model
        # Explicit production handlers are instance-local.  The class registry
        # remains dynamic for lightweight tests and extension points that
        # register a handler after constructing a coordinator.
        self._instance_handlers = dict(handlers or {})

    @classmethod
    def register(cls, mode: TurnMode) -> Callable[[ModeHandler], ModeHandler]:
        """Register a handler for a mode.

        Usage as a decorator:

            @TurnCoordinatorAuthority.register(TurnMode.CONVERSATION)
            async def handle_conversation(ctx: TurnContext, deps: RuntimeDeps) -> ...
        """

        def _decorator(handler: ModeHandler) -> ModeHandler:
            cls._mode_handlers[mode] = handler
            return handler

        return _decorator

    @classmethod
    def classify_mode(
        cls,
        directive: str,
        *,
        mission_requested: bool = False,
        governance_requested: bool = False,
    ) -> TurnMode:
        """Deterministically classify a directive into a canonical mode.

        Governance takes precedence, then explicit mission requests.  Advisory
        mode is selected for read-only prompts; everything else falls back to
        conversation.  No LLM is consulted here.
        """
        clean = directive.strip().lower()
        if governance_requested:
            return TurnMode.GOVERNANCE
        if mission_requested:
            return TurnMode.MISSION
        read_only_markers = (
            "explain",
            "summarize",
            "describe",
            "what is",
            "what are",
            "list",
            "show",
        )
        action_tokens = {
            "create",
            "write",
            "edit",
            "delete",
            "run",
            "execute",
            "commit",
            "push",
        }
        tokens = set(re.findall(r"\b\w+\b", clean))
        if clean.startswith(read_only_markers) and not (action_tokens & tokens):
            return TurnMode.ADVISORY
        return TurnMode.CONVERSATION

    def coordinate(self, context: TurnContext) -> TurnResult:
        """Coordinate a single turn and return its event stream."""
        handler = self._instance_handlers.get(context.mode) or self._mode_handlers.get(
            context.mode
        )
        if handler is None:
            logger.warning(
                "No handler registered for mode %s; falling back to conversation",
                context.mode.value,
            )
            handler = self._instance_handlers.get(
                TurnMode.CONVERSATION
            ) or self._mode_handlers.get(TurnMode.CONVERSATION)
        if handler is None:
            raise RuntimeError("No conversation handler registered")

        prepare = getattr(handler, "prepare", None)
        if callable(prepare):
            prepare(context, self.runtime)

        events = handler(context, self.runtime)
        return TurnResult(context=context, events=events)


TurnCoordinator = TurnCoordinatorAuthority
