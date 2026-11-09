"""``complete()`` must redact before transmission, like every other egress method.

Inventory item 33. ``AnthropicDirectClient.complete`` and
``OpenAICompatClient.complete`` built their HTTP payload directly from the
caller's ``prompt``/``system`` and never called :class:`PrivacyFilter` -- while
``chat`` and ``stream_chat`` on the same classes each carried the filter block
verbatim, and both class docstrings claimed *"every message list is passed
through PrivacyFilter before transmission"*.

The catalogue named two clients. There are **three**:
:class:`VertexMaaSClient` subclasses ``OpenAICompatClient`` and its ``complete``
is ``strip_reasoning(super().complete(...))``, so it inherited the bypass.

## Why this was worth fixing while unreachable

``aios/api/main.py`` deliberately wires ``planner_llm``/``self_analysis_llm`` to
the LOCAL client, so no ``complete()`` caller reaches cloud today. But every
caller -- ``reflection_agent``, ``self_analysis_agent``, ``alignment``,
``planner``, ``council/reasoning``, ``runtime/intelligence_gateway`` -- is a
public API surface one wiring change away from shipping raw prompts (file
contents, tool output, secrets) to Anthropic/OpenAI/Vertex unredacted. A latent
leak that activates on an unrelated config change is the same class of defect as
the 2026-07-07 privacy-filter finding this project already got burned by.

## The shape of the fix

Not "add the five lines to complete() too" -- that is what left the hole open in
the first place, since the block was copy-pasted into two methods out of three.
Each client now has ONE ``_filtered_for_egress`` helper and all of its egress
methods call it, so the redaction cannot be present in one path and absent in
another. The structural test at the bottom is what keeps that true.
"""

from __future__ import annotations

import ast
import textwrap
from typing import Any

import pytest

from aios.core.anthropic_direct import AnthropicDirectClient
from aios.core.openai_compat import OpenAICompatClient
from aios.core.vertex_maas import VertexMaaSClient
from tests.source_rules import executable_source

#: A real-shaped AWS secret access key. Slash-bearing on purpose: the entropy
#: backstop exempts path-shaped tokens (the 2026-07-07 egress fix), so this is
#: the token that most nearly escapes redaction while still being a credential.
_SECRET = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"

#: A second, structurally different credential, so a pass cannot depend on one
#: pattern in the list happening to fire.
_TOKEN = "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"


def _capture(client: Any) -> list[dict[str, Any]]:
    """Intercept the HTTP payload at the wire instead of trusting the return.

    Asserting on what ``complete()`` RETURNS would prove nothing -- the leak is
    in what gets SENT.
    """
    sent: list[dict[str, Any]] = []

    def fake_post(payload: dict[str, Any]) -> dict[str, Any]:
        sent.append(payload)
        # Shapes for both providers; each client reads only its own keys.
        return {
            "content": [{"type": "text", "text": "ok"}],
            "choices": [{"message": {"role": "assistant", "content": "ok"}}],
        }

    client._post = fake_post  # type: ignore[method-assign]
    return sent


def _clients() -> list[tuple[str, Any]]:
    return [
        ("anthropic", AnthropicDirectClient(api_key="test-key")),
        ("openai", OpenAICompatClient(api_key="test-key")),
        # Constructible without google-auth: `_headers` (which mints a token)
        # is never reached because `_post` is replaced.
        ("vertex", VertexMaaSClient(project="test-project")),
    ]


@pytest.mark.parametrize("name, client", _clients())
def test_a_secret_in_the_prompt_never_reaches_the_wire(name: str, client: Any) -> None:
    """The leak itself, executed rather than described."""
    sent = _capture(client)

    client.complete(f"deploy with aws_secret_access_key = {_SECRET}")

    assert sent, f"{name}: complete() sent nothing"
    body = str(sent[0])
    assert _SECRET not in body, (
        f"{name}: complete() transmitted a raw AWS secret access key. The "
        "payload is built from the caller's prompt without passing through "
        f"PrivacyFilter. payload={body[:400]}"
    )


@pytest.mark.parametrize("name, client", _clients())
def test_a_secret_in_the_system_prompt_never_reaches_the_wire(
    name: str, client: Any
) -> None:
    """The `system=` argument is a separate leak path from `prompt`.

    On Anthropic it is a top-level payload field rather than a message, so a fix
    that filtered only the user turn would still ship it verbatim.
    """
    sent = _capture(client)

    client.complete("hello", system=f"You may use the token {_TOKEN} to deploy.")

    assert sent, f"{name}: complete() sent nothing"
    body = str(sent[0])
    assert _TOKEN not in body, (
        f"{name}: complete() transmitted a raw GitHub token from the SYSTEM "
        f"prompt. payload={body[:400]}"
    )


# --------------------------------------------------------------------------- #
# The other direction: the fix must not neuter the call
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("name, client", _clients())
def test_the_prompt_still_arrives(name: str, client: Any) -> None:
    """Redacting everything would pass the tests above and break the product."""
    sent = _capture(client)

    client.complete("Summarise the failing test and propose one fix.")

    body = str(sent[0])
    assert "Summarise the failing test" in body, (
        f"{name}: the user's prompt did not survive filtering; complete() would "
        f"now send an empty or fully-redacted request. payload={body[:400]}"
    )


@pytest.mark.parametrize("name, client", _clients())
def test_the_system_prompt_still_arrives(name: str, client: Any) -> None:
    """A system prompt lost in conversion is a silent behaviour change.

    Both converters move it: Anthropic hoists it into a top-level ``system``
    string, OpenAI keeps it as a ``role: system`` message. Either way the text
    must be in the payload -- callers like the planner depend on it.
    """
    sent = _capture(client)

    client.complete("hi", system="You are a release engineer.")

    body = str(sent[0])
    assert "You are a release engineer." in body, (
        f"{name}: the system prompt vanished from the payload. payload={body[:400]}"
    )


# --------------------------------------------------------------------------- #
# Structural guard
# --------------------------------------------------------------------------- #
#: Every public method on a cloud client that transmits to a provider.
_EGRESS_METHODS = frozenset(
    {"complete", "chat", "stream_chat", "stream_chat_with_tools"}
)


#: How a cloud client sends: HTTP clients post or stream, the plan client runs
#: its CLI.
_TRANSPORTS = ("self._post(", "self._stream(", "self._call(")


def _cloud_clients() -> list[type]:
    """Every cloud brain's client class, from the router's one registry.

    This list was hand-written and named four classes; on 2026-11-04 the
    registry named six, and the plan client (the operator's own plans) and the
    Vertex client were not checked here at all.
    """
    from importlib import import_module

    from aios.core import router

    classes = []
    for spec in router.cloud_providers():
        module, _, name = spec.client_class.partition(":")
        classes.append(getattr(import_module(module), name))
    return classes


#: The only calls a delegating method may make besides its hand-off: pure
#: helpers on the answer it gets back.
_PURE_CALLS = frozenset({"super", "str", "strip_reasoning", "get"})


def _delegates(source: str) -> list[tuple[str, bool]] | None:
    """The egress methods a method only hands its messages to, as
    ``(name, through_super)``, or None when it does anything else.

    A method that delegates and ALSO calls anything that is not a pure helper
    (a socket, a client, a subprocess) is not a delegation: it must filter by
    itself. Without this, a method could leak its messages raw and still pass
    by calling a filtered sibling too (the privacy reviewer's counterexample
    of 2026-11-04, kept below as a test the guard must fail).
    """
    tree = ast.parse(textwrap.dedent(source))
    targets: list[tuple[str, bool]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id in _PURE_CALLS:
            continue
        if isinstance(func, ast.Attribute):
            if func.attr in _EGRESS_METHODS:
                base = func.value
                if isinstance(base, ast.Name) and base.id == "self":
                    targets.append((func.attr, False))
                    continue
                if (
                    isinstance(base, ast.Call)
                    and isinstance(base.func, ast.Name)
                    and base.func.id == "super"
                ):
                    targets.append((func.attr, True))
                    continue
            elif func.attr in _PURE_CALLS:
                continue
        return None
    return targets or None


def _filters(
    cls: type, name: str, seen: frozenset[tuple[type, str]] = frozenset()
) -> bool:
    """Whether *cls*'s own *name* passes its messages through the filter: by
    itself, or by doing nothing but hand them to an egress method that does
    (``super().chat`` in the Vertex client, ``self.chat`` in the plan
    client's ``stream_chat``)."""
    if (cls, name) in seen:
        return False
    seen = seen | {(cls, name)}
    source = executable_source(vars(cls)[name])
    if "_filtered_for_egress" in source or "_privacy_filter" in source:
        return True
    delegated = _delegates(source)
    if delegated is None:
        return False  # it does more than hand off, so it must filter by itself
    for target, through_super in delegated:
        mro = cls.__mro__[1:] if through_super else cls.__mro__
        owner = next((b for b in mro if target in vars(b)), None)
        if owner is None or not _filters(owner, target, seen):
            return False
    return True


class _Filtered:
    def complete(self, messages: Any) -> Any:
        return self._post(self._filtered_for_egress(messages))

    def _filtered_for_egress(self, messages: Any) -> Any:
        return messages

    def _post(self, payload: Any) -> Any:
        return payload


class _LeaksThenDelegates(_Filtered):
    def chat(self, messages: Any) -> Any:
        import socket

        sock = socket.socket()
        sock.connect(("example.invalid", 80))
        sock.send(repr(messages).encode())
        return self.complete(messages)


class _OnlyDelegates(_Filtered):
    def chat(self, messages: Any) -> Any:
        return str(super().complete(messages))


def test_the_guard_fails_a_method_that_leaks_and_also_delegates() -> None:
    """The privacy reviewer's counterexample (2026-11-04): calling a filtered
    sibling must not excuse a method that also sends its messages raw."""
    assert not _filters(_LeaksThenDelegates, "chat")
    assert _filters(_OnlyDelegates, "chat"), "a pure hand-off still counts"


@pytest.mark.parametrize("cls", _cloud_clients())
def test_every_egress_method_filters(cls: type) -> None:
    """The invariant, asserted against source rather than trusted to review.

    This is the test that would have caught item 33 the day it was written:
    ``complete`` was the one method in the set that never mentioned the filter.
    """
    unfiltered = []
    for name, member in vars(cls).items():
        if name not in _EGRESS_METHODS or not callable(member):
            continue
        if not _filters(cls, name):
            unfiltered.append(name)

    assert not unfiltered, (
        f"{cls.__name__} has egress methods that never pass their messages "
        f"through PrivacyFilter: {unfiltered}. Every method that transmits to a "
        "cloud provider must filter first -- the class docstring claims it does."
    )


@pytest.mark.parametrize("cls", _cloud_clients())
def test_no_unreviewed_public_method_transmits(cls: type) -> None:
    """A NEW public method that posts must not slip in unnoticed.

    The test above only checks methods it already knows the names of, so on its
    own it would say nothing about a future ``complete_json`` or ``embed``.
    This one fails the moment any public method calls the transport directly,
    forcing that method into the reviewed set above.
    """
    offenders = []
    for name, member in vars(cls).items():
        if name.startswith("_") or not callable(member) or name in _EGRESS_METHODS:
            continue
        try:
            source = executable_source(member)
        except (OSError, TypeError):  # pragma: no cover - builtins/slots
            continue
        if any(t in source for t in _TRANSPORTS):
            offenders.append(name)

    assert not offenders, (
        f"{cls.__name__}.{offenders} transmit to the provider but are not in "
        "_EGRESS_METHODS, so nothing checks that they redact first. Add them to "
        "_EGRESS_METHODS (and route them through _filtered_for_egress)."
    )


def test_vertex_inherits_the_filtered_path_rather_than_overriding_it() -> None:
    """The third client the catalogue missed.

    ``VertexMaaSClient.complete`` delegates via ``super().complete()``, which is
    why fixing ``OpenAICompatClient`` fixes it too. If a future edit gives Vertex
    its own payload-building ``complete``, this fails and sends the author to the
    behavioural tests above.
    """
    source = executable_source(VertexMaaSClient.complete)

    assert "super().complete(" in source, (
        "VertexMaaSClient.complete no longer delegates to OpenAICompatClient. It "
        "must not build its own payload, or it re-opens item 33 for Vertex only."
    )
    assert "self._post(" not in source, (
        "VertexMaaSClient.complete now transmits directly, bypassing the "
        "filtered path it used to inherit."
    )
