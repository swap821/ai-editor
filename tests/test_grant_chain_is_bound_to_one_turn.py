"""A consumed capability must not authorise a turn that never asked for it.

`grants()` returns every still-live consumed capability for a session+route, and
`generate_pipeline` appends each one to `approved_commands`. Clearing only when a
request arrived with NO tokens left a window: a paused turn that was abandoned
(client disconnect, or its stashed tail expiring) kept its grant live, and the
next request carrying ANY token inherited it.

Measured before the fix, against the real store: the grant was still live at
t+60s and gone at t+121s, so the window was bounded by the 120s capability TTL
but genuinely present.

What is NOT claimed here: the token itself was never replayable.
`consume_if_available` is an atomic compare-and-swap on `consumed_at IS NULL`,
pinned by `test_capability_is_opaque_exact_and_single_use` and
`test_two_consumers_race_for_one_capability`. What outlived its single use was
the AUTHORISATION, not the token.
"""

from __future__ import annotations

import inspect
import re

from aios.application.turns import generate_pipeline


def test_a_pause_always_stashes_so_a_replay_is_distinguishable() -> None:
    """The continuation signal must not depend on there being a convo tail.

    `turn_state.take()` is what tells the next request whether it continues a
    paused turn or starts a new one. That only works if EVERY pause stashes:
    the branch used to read `if _convo_tail: turn_state.stash(...)`, so a pause
    whose tail happened to be empty looked like no pause at all -- and its own
    replay would then clear the grants it was trying to redeem.

    Asserted against the source because the failure mode is a re-introduced
    guard, which no behavioural test of the happy path would notice.
    """
    source = inspect.getsource(generate_pipeline)

    match = re.search(
        r"_convo_tail = ev\.pop\(\"_convo_tail\", None\)(.{0,900}?)turn_state\.stash\(",
        source,
        re.S,
    )
    assert match, "the human_required branch no longer stashes -- inspect it"

    between = match.group(1)
    assert "if _convo_tail:" not in between, (
        "the stash is guarded by `if _convo_tail:` again. A paused turn with an "
        "empty tail then leaves nothing stashed, its replay is misread as a new "
        "turn, and the grants it is redeeming are cleared underneath it."
    )
    assert "_convo_tail or []" in source, (
        "the stash must pass an empty list rather than skipping, so `take()` "
        "reports the pause"
    )


def test_a_token_bearing_request_without_a_stash_clears_the_grant_chain() -> None:
    """Tokens alone must not mean 'continue the previous chain'.

    The whole window was that `clear_grants` fired only when a request arrived
    with NO tokens, so a new turn that happened to carry one inherited whatever
    an abandoned turn had left live.

    Structural for the same reason as above: the ordering matters and is
    invisible to a happy-path test. The decision must also PRECEDE the
    `grants()` read, or the chain is cleared after it has already been used.
    """
    source = inspect.getsource(generate_pipeline)

    take_at = source.find("turn_state.take(session_id)")
    grants_at = source.find("capabilities.grants(session_id")
    assert take_at != -1, "the continuation check disappeared"
    assert grants_at != -1, "the grant read disappeared"
    assert take_at < grants_at, (
        "grants are read BEFORE the request is classified as a replay or a new "
        "turn, so a new turn inherits the previous chain before anyone decides "
        "whether it should"
    )

    window = source[take_at:grants_at]
    assert "clear_grants" in window, (
        "a token-bearing request that found nothing stashed must clear the "
        "grant chain before reading it"
    )
