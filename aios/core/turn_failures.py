"""Why a turn failed, as a code a consumer reads without parsing prose.

The SSE ``error`` event is shared: it carries the backend's own failures
("Internal error: ...", a refused approval, revoked authority) AND its honest
diagnosis of a turn the MODEL failed. A harness that cannot tell them apart
reads a weak model as a broken backend: the nightly endurance run aborted on
five turns a 0.5B model left empty and reported "the harness proves nothing"
(2026-10-07..10, four nights red with no backend change).

A code here means: the backend worked, the turn was measured, the model failed
it. Score it as a failed turn. Every other error stays an error.
"""

from __future__ import annotations

#: The model returned no tool call, no prose and no code.
MODEL_NO_OUTPUT = "model_no_output"
#: The model repeated the same call with no progress; the loop guard stopped it.
AGENT_LOOP = "agent_loop"

MODEL_FAILURE_CODES = frozenset({MODEL_NO_OUTPUT, AGENT_LOOP})
