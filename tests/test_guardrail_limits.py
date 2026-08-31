"""Guardrail constants are defined behind the freeze, and stay there.

Inventory item 5. `SCOPE_ROOTS`, `EARNED_AUTONOMY_*`, `ROUTER_CLOUD_TASKS`,
`MAX_RED_ACTIONS_PER_SESSION` and `AUDIT_GENESIS_HASH` decide how far the system
may reach and how much it may do without a human. They lived in
`aios/config.py`, which is not frozen, so an agent with ordinary edit rights
could widen its own sandbox, lower its own evidence bar, or re-anchor the audit
chain — with a human PR review as the only backstop and no automated one.

Moving them is only worth anything if they cannot drift back, so these tests
assert the STRUCTURE (definition site, freeze coverage, single derivation) rather
than just the values.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from aios import config
from aios.policy.constitution import FROZEN_PATH_PREFIXES
from aios.security import limits

REPO_ROOT = Path(__file__).resolve().parents[1]

GUARDRAILS = (
    "SCOPE_ROOTS",
    "EARNED_AUTONOMY_ENABLED",
    "EARNED_AUTONOMY_MIN_SUCCESSES",
    "ROUTER_CLOUD_TASKS",
    "MAX_RED_ACTIONS_PER_SESSION",
    "AUDIT_GENESIS_HASH",
)


@pytest.mark.parametrize("name", GUARDRAILS)
def test_config_re_exports_the_frozen_definition(name: str) -> None:
    """`config.X` must BE `limits.X`, not a second value that happens to match."""
    assert hasattr(limits, name), f"{name} is not defined in the frozen module"
    assert getattr(config, name) == getattr(limits, name)


@pytest.mark.parametrize("name", GUARDRAILS)
def test_config_does_not_redefine_a_guardrail(name: str) -> None:
    """Catch a re-inlining, which no value comparison would notice.

    If someone restores `SCOPE_ROOTS = _env_scope_roots(...)` in config.py, the
    values still agree on a default machine and every other test passes — while
    the definition has quietly moved back outside the freeze. Asserted against
    the AST so the check is about WHERE the value is decided.
    """
    source = (REPO_ROOT / "aios" / "config.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    for node in tree.body:
        target_names: list[str] = []
        value = None
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            target_names = [node.target.id]
            value = node.value
        elif isinstance(node, ast.Assign):
            target_names = [t.id for t in node.targets if isinstance(t, ast.Name)]
            value = node.value
        if name not in target_names or value is None:
            continue

        # The only permitted right-hand side is an attribute read off `_limits`.
        assert isinstance(value, ast.Attribute), (
            f"config.{name} is computed in config.py again; its definition "
            "belongs in aios/security/limits.py, behind the freeze"
        )
        assert isinstance(value.value, ast.Name) and value.value.id == "_limits", (
            f"config.{name} no longer reads from the frozen limits module"
        )
        return

    pytest.fail(f"config.{name} disappeared entirely — expected a _limits re-export")


def test_the_limits_module_is_inside_a_frozen_prefix() -> None:
    """The move is pointless if the destination is not actually frozen."""
    rel = Path(limits.__file__).resolve().relative_to(REPO_ROOT).as_posix()
    assert any(
        rel.startswith(prefix.rstrip("/") + "/") for prefix in FROZEN_PATH_PREFIXES
    ), f"{rel} is not under any frozen prefix, so nothing protects these constants"


def test_project_root_agrees_between_the_two_derivations() -> None:
    """The one real cost of the move, pinned rather than trusted.

    `limits` cannot import `config` (config imports IT), so it derives
    PROJECT_ROOT from its own location. Two pieces of path arithmetic that
    silently disagreed would root the scope checks and the documented scope in
    different places — and a base/roots mismatch has already been a real
    containment escape here once.
    """
    assert limits.PROJECT_ROOT == config.PROJECT_ROOT


def test_the_audit_genesis_hash_is_not_environment_derived() -> None:
    """A genesis hash an operator can set is one an attacker with env access can set.

    Re-anchoring the chain is exactly how a rewritten history is made to verify,
    so this value must be a literal, not a lookup.
    """
    source = (REPO_ROOT / "aios" / "security" / "limits.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == "AUDIT_GENESIS_HASH":
                assert not any(
                    isinstance(child, ast.Call)
                    and isinstance(child.func, ast.Name)
                    and child.func.id.startswith("_env")
                    for child in ast.walk(node)
                ), "AUDIT_GENESIS_HASH became environment-derived"
                return
    pytest.fail("AUDIT_GENESIS_HASH is no longer defined in limits.py")


# --------------------------------------------------------------------------- #
# One derivation of "is this path frozen?"
# --------------------------------------------------------------------------- #
def test_self_apply_asks_the_constitution_rather_than_its_own_list() -> None:
    """There were THREE independent answers; there is now one.

    `classify_target` carried `frozen_subdirs=("security",)`, which agreed with
    `FROZEN_PATH_PREFIXES` only by coincidence of content. Item 5 calls this out
    directly: frozen-core enforcement covered "1 of 4 surfaces". Asserted by
    behaviour — a path frozen by the constitution must classify RED here.
    """
    from aios.core.self_apply import classify_target

    for prefix in FROZEN_PATH_PREFIXES:
        probe = f"{prefix.rstrip('/')}/probe_file.py"
        assert classify_target(probe) == "RED", (
            f"{probe} is frozen per the constitution but self-apply calls it "
            "YELLOW — the two enforcement surfaces disagree again"
        )


def test_the_newly_relocated_limits_file_is_itself_red_to_self_apply() -> None:
    """The constants are only protected if the file holding them is."""
    from aios.core.self_apply import classify_target

    assert classify_target("aios/security/limits.py") == "RED"


def test_a_sibling_name_is_not_swept_up() -> None:
    """`aios/security_notes.py` is not inside `aios/security/`.

    An over-broad prefix match would freeze innocent files, which creates
    pressure to loosen the rule — the opposite of what item 5 wants.
    """
    from aios.core.self_apply import classify_target

    assert classify_target("aios/security_notes.py") == "YELLOW"
    assert classify_target("aios/core/executor.py") == "YELLOW"


def test_an_explicit_frozen_set_still_overrides() -> None:
    """Callers that genuinely need a different set keep working."""
    from aios.core.self_apply import classify_target

    assert classify_target("aios/foo/x.py", frozen_subdirs=("foo",)) == "RED"
    assert classify_target("aios/security/gateway.py", frozen_subdirs=("foo",)) == "YELLOW"
