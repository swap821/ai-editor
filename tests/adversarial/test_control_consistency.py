"""Consistency attacks — the layer that VALIDATES and the layer that ACTS must
resolve the identical input identically.

Every other family in this directory is a *payload* family: it fixes a control
and enumerates inputs against it (``../../etc/passwd``, homoglyphs, nested
``$()``, forged chains). Roughly 450 such cases exist here, and they are worth
having. But a payload family can only find inputs the harness already imagines,
and — more importantly — **every one of those 450 cases shares the code's own
model of where a relative path resolves from.** That shared assumption is a
blind spot no amount of additional payloads can cover.

The proof that it is a blind spot: ``tests/adversarial/test_sandbox_escape.py``
attacks scope containment with 62 cases, including ``../../etc/passwd`` and
``cat ../../etc/passwd``. Both escape under *either* resolution base, so both
pass whether the check resolves against the scope root or against the repo root.
Meanwhile ``training_ground/../X`` escapes under only one of them — and that was
a live containment escape that all 62 cases reported as blocked.

So this family asserts a different kind of property. It never asks "is this
payload refused?" It asks "do these two layers agree?" — and it finds the
disagreement without having to guess the payload that exploits it:

    token    training_ground/../PROOF.txt
    CHECKED  <root>/training_ground/PROOF.txt   -> in scope, ALLOWED
    EXECUTED <repo>/PROOF.txt                   -> outside every declared root

Two bugs of exactly that shape have now been found this way, the second of them
in the fix for the first:

1. ``is_path_in_scope`` resolved command tokens against the scope root while the
   executor ran them with cwd = the root's parent.
2. After (1) was fixed, ``Executor._scope_cwd`` still read the process-start
   default ``config.SCOPE_ROOTS`` while the check read the live, re-declarable
   ``get_scope_roots()``. Under any session that called ``set_scope_roots``,
   ``touch training_ground/PROOF.txt`` was ALLOWED and landed outside every
   declared root. Two copies of one derivation, kept in sync by a comment that
   said "MUST stay identical", drifted anyway.

The lesson encoded here is structural, not textual: prefer one derivation with
two callers over two derivations with a comment. Where that is not possible,
assert the agreement mechanically — which is what these tests do.

``test_the_family_can_fail`` at the bottom is a required member, not a
formality: a benchmark that has never failed has never been shown capable of
failing.
"""
from __future__ import annotations

import ast
import inspect
import os
import textwrap
from pathlib import Path

import pytest

from aios import config
from aios.agents import tool_handlers
from aios.agents.tool_agent import TOOL_SPECS
from aios.api.routes import files as files_routes
from aios.core.executor import Executor
from aios.domain.capabilities.digest import payload_digest
from aios.probe_common import ALLOWED_FILE_RE
from aios.security import scope_lock


def _code_without_docstring(obj) -> str:
    """Return source with the docstring removed.

    These docstrings deliberately NAME the defect they fixed, so a plain
    substring search over ``inspect.getsource`` matches the explanation and
    fails against correct code. Examine what runs, not what is written about it.
    """
    tree = ast.parse(textwrap.dedent(inspect.getsource(obj)))
    node = tree.body[0]
    body = node.body[1:] if ast.get_docstring(node) is not None else node.body
    return "\n".join(ast.unparse(child) for child in body)


@pytest.fixture
def declared_roots(tmp_path):
    """Re-declare the scope roots and restore them afterwards.

    Restoration is not politeness — the authority is a process singleton, and a
    leaked root silently changes what every later test considers in-scope.
    """
    original = scope_lock.get_scope_roots()
    root = tmp_path / "training_ground"
    root.mkdir(parents=True, exist_ok=True)
    scope_lock.set_scope_roots([root])
    try:
        yield root
    finally:
        scope_lock.set_scope_roots(list(original))


#: Token shapes that a *correct* base resolves inside the sandbox and an
#: *incorrect* base resolves outside it (or vice versa). These are the tokens a
#: payload family cannot distinguish, because their verdict depends on the base
#: rather than on the token.
_BASE_SENSITIVE_TOKENS = [
    "training_ground/PROOF.txt",
    "training_ground/../PROOF.txt",
    "training_ground/nested/../PROOF.txt",
    "training_ground/./PROOF.txt",
    "./training_ground/PROOF.txt",
]


# ── VIII · the command-resolution base ───────────────────────────────────────

def test_the_check_and_the_executor_share_one_base() -> None:
    """The base is one function, not two that agree today."""
    assert Executor()._scope_cwd() == scope_lock.command_cwd()


def test_they_still_share_one_base_after_the_roots_are_redeclared(
    declared_roots,
) -> None:
    """The drift that survived the first fix.

    ``config.SCOPE_ROOTS`` is the process-start default; ``get_scope_roots()``
    is the live authority. Reading the base from the former while checking
    against the latter reopened the escape for any session that re-declared its
    scope. Nothing in production re-declares roots today — but 20+ test modules
    do, which means the containment suite was validating a geometry the executor
    never used.
    """
    assert Executor()._scope_cwd() == scope_lock.command_cwd()
    assert Executor()._scope_cwd() == declared_roots.parent


def test_the_base_follows_the_authority_not_the_startup_default(
    declared_roots,
) -> None:
    """A re-declared root must move the executor's cwd with it."""
    assert Executor()._scope_cwd() != config.SCOPE_ROOTS[0].resolve().parent


def test_the_executor_does_not_derive_the_base_a_second_time() -> None:
    """Structural: one derivation, two callers.

    Asserted against the code rather than the behaviour because behavioural
    agreement is exactly what drifted last time — two derivations agreed under
    the default configuration and diverged under a re-declared one.
    """
    body = _code_without_docstring(Executor._scope_cwd)
    assert "SCOPE_ROOTS" not in body, (
        "Executor._scope_cwd re-derives the base from config.SCOPE_ROOTS "
        "instead of calling scope_lock.command_cwd(); that is the drift."
    )
    assert "command_cwd" in body


@pytest.mark.parametrize("token", _BASE_SENSITIVE_TOKENS)
def test_a_command_token_lands_where_the_check_said_it_would(
    declared_roots, token: str
) -> None:
    """The differential assertion this whole family exists for.

    For a base-sensitive token, the path the CHECK resolves must be byte-equal
    to the path the shell would touch. Note what is *not* asserted: whether the
    token is allowed. A token may legitimately be refused. What may never happen
    is the check clearing one path while the executor touches another.
    """
    checked = scope_lock._SCOPE_LOCK.is_path_in_scope(
        token, base=scope_lock.command_cwd()
    )
    executed = (Executor()._scope_cwd() / token).resolve()
    assert Path(checked.resolved) == executed


@pytest.mark.parametrize("token", _BASE_SENSITIVE_TOKENS)
def test_an_allowed_token_cannot_land_outside_a_declared_root(
    declared_roots, token: str
) -> None:
    """The escape, stated as a property rather than as a payload."""
    verdict = scope_lock.command_stays_in_scope(f"touch {token}")
    if not verdict.in_scope:
        return  # refused is always a safe answer
    landed = (Executor()._scope_cwd() / token).resolve()
    roots = scope_lock.get_scope_roots()
    assert any(
        landed == r or str(landed).startswith(str(r) + os.sep) for r in roots
    ), f"'{token}' was ALLOWED but lands at {landed}, outside {roots}"


# ── VIII · the actor consumes the validator's output ─────────────────────────

@pytest.mark.parametrize(
    "route", [files_routes.read_file, files_routes.get_file_tree]
)
def test_the_file_routes_open_the_path_the_check_resolved(route) -> None:
    """Consistency by construction — the pattern that kept these routes safe.

    ``files.py`` never re-derives a path: it opens ``Path(check.resolved)``, the
    validator's own output, so the two cannot disagree. The command path had the
    escape precisely because it re-derived instead. Encoded so a refactor that
    switches to ``read_root / req.path`` fails here.
    """
    body = _code_without_docstring(route)
    assert "check.resolved" in body


def test_the_sandbox_write_resolver_uses_the_checked_path() -> None:
    """Same invariant on the autonomous write path."""
    body = _code_without_docstring(tool_handlers.resolve_sandbox_file)
    assert "scope.resolved" in body


def test_the_write_resolver_fails_closed_when_its_root_and_the_scope_disagree(
    declared_roots, tmp_path
) -> None:
    """Where two bases legitimately differ, the answer must be refusal.

    ``read_root`` stays ``PROJECT_ROOT`` while the declared scope moves, so
    these two genuinely disagree under a re-declared root. That is acceptable
    only because the disagreement resolves to BLOCKED rather than to a write at
    the un-checked path.
    """
    result = tool_handlers.resolve_sandbox_file(
        "training_ground/PROOF.txt", read_root=config.PROJECT_ROOT
    )
    assert isinstance(result, str) and result.startswith("[BLOCKED]")


# ── IV · the allowlist and the paths it is supposed to admit ─────────────────

def test_the_write_allowlist_and_the_scope_check_agree_on_the_same_token() -> None:
    """``ALLOWED_FILE_RE`` mandates ``training_ground/x.py``; the scope check
    must consider that same string in-scope under the base commands run in.

    Two components encoding the same convention differently is the §2.1 shape:
    the allowlist means repo-relative, and the check's *default* base means
    scope-root-relative. They only agree because command checks pass an explicit
    base. If that base is dropped, this fails.
    """
    token = "training_ground/probe_case.py"
    assert ALLOWED_FILE_RE.match(token)
    checked = scope_lock._SCOPE_LOCK.is_path_in_scope(
        token, base=scope_lock.command_cwd()
    )
    assert checked.in_scope, (
        f"the allowlist admits '{token}' but the scope check refuses it: "
        f"{checked.reason}"
    )


def test_every_scope_exemption_is_still_a_command_the_system_generates() -> None:
    """A stale exemption is a permanent hole nobody is looking at.

    The sandbox scope check exempts the §VIII self-verification command by exact
    string. If that command is ever reworded, the exemption stops matching it
    (self-apply breaks loudly, which is fine) — but the old string keeps being
    exempt (which is not). Bind the two together.
    """
    from aios.core.self_apply import DEFAULT_VERIFY_COMMAND

    exempt = scope_lock._SCOPE_EXEMPT_COMMANDS
    assert exempt == frozenset({DEFAULT_VERIFY_COMMAND}), (
        "the scope exemption set has drifted from the command it exists to "
        f"exempt: exempt={exempt!r} verify={DEFAULT_VERIFY_COMMAND!r}"
    )


# ── VI · one digest function, both sides of the capability ───────────────────

def test_the_capability_binds_and_checks_with_the_same_digest_function() -> None:
    """Issue and consume must not each canonicalize the payload their own way.

    ``_token_digest`` legitimately hashes the capability *token* (an opaque
    string, for storage) rather than a payload, so it is named as the sole
    permitted hand-rolled hash instead of being caught by a blanket ban. A new
    ``hashlib`` call anywhere else in this module is a second canonicalization
    of something, which is the drift this family exists to catch.
    """
    from aios.application.capabilities import authority

    source = inspect.getsource(authority)
    assert "payload_digest(" in source, (
        "the capability authority no longer routes through the shared digest"
    )

    tree = ast.parse(source)
    hashing: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if "hashlib" in ast.unparse(node):
            hashing.add(node.name)

    assert hashing == {"_token_digest"}, (
        "only _token_digest may hash directly; payload binding must go through "
        f"aios.domain.capabilities.digest.payload_digest. Found: {sorted(hashing)}"
    )


def test_the_digest_is_stable_across_equivalent_payload_orderings() -> None:
    """The same payload written two ways must bind identically."""
    assert payload_digest({"a": 1, "b": 2}) == payload_digest({"b": 2, "a": 1})


# ── the agent surface: offered vs. actually reachable ────────────────────────

def test_every_offered_tool_is_reachable(monkeypatch) -> None:
    """A tool the model is offered but cannot reach wastes a whole turn.

    ``overwrite_file`` is deliberately absent from ``_dispatch``: it is
    translated into ``edit_file`` before dispatch, so the approval payload,
    replay, autonomy and auto-verify layers all see the real action. That is the
    one legitimate exception, and naming it here is the point — an accidental
    twelfth entry would not be named, and would fail.
    """
    offered = {spec["function"]["name"] for spec in TOOL_SPECS}

    from aios.agents import tool_agent

    reachable = set()
    source = inspect.getsource(tool_agent.ToolAgent._dispatch)
    for name in offered:
        if f'"{name}"' in source:
            reachable.add(name)

    translated = {"overwrite_file"}
    missing = offered - reachable - translated
    assert not missing, (
        f"offered to the model but not reachable in _dispatch: {sorted(missing)}"
    )


def test_the_translated_tool_really_is_translated() -> None:
    """The exception above must be an exception, not an oversight."""
    from aios.agents import tool_agent

    assert hasattr(tool_agent.ToolAgent, "_overwrite_as_edit")
    run_source = inspect.getsource(tool_agent.ToolAgent.run)
    assert "_overwrite_as_edit" in run_source, (
        "overwrite_file is exempted from the reachability check because it is "
        "translated in run() before dispatch; that translation is gone"
    )


# ── the negative control ─────────────────────────────────────────────────────

def test_the_family_can_fail(declared_roots, monkeypatch) -> None:
    """Deliberately break the agreement and confirm this family catches it.

    Re-points the executor's base at the scope root (the *old*, wrong base) and
    asserts the differential check now fails. Without this test, a green run
    proves only that the assertions execute — not that they discriminate.
    """
    monkeypatch.setattr(
        Executor, "_scope_cwd", lambda self: declared_roots, raising=True
    )

    disagreed = []
    for token in _BASE_SENSITIVE_TOKENS:
        checked = scope_lock._SCOPE_LOCK.is_path_in_scope(
            token, base=scope_lock.command_cwd()
        )
        executed = (Executor()._scope_cwd() / token).resolve()
        if Path(checked.resolved) != executed:
            disagreed.append(token)

    assert disagreed, (
        "the differential check passed against a deliberately divergent base — "
        "it cannot detect the bug it exists to detect"
    )
