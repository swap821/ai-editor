"""Anti-passthrough AST gate for *Authority classes.

Fails when a public Authority method is only ``return same_named_fn(...)`` —
the classic banned twin that satisfies Decision A on paper while leaving
condition 2 (a real runtime path invokes the owner) false.

Store-facade delegations (``self.store`` / ``self.journal`` / ``self._adapter``)
and explicitly allowlisted cross-organ edges are permitted.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
AIOS_ROOT = REPO_ROOT / "aios"

#: (relative path under aios/, class name, method name)
ACCEPTABLE_STORE_FACADE: frozenset[tuple[str, str, str]] = frozenset()

#: Cross-organ delegation that is intentional, not a parallel twin.
ACCEPTABLE_CROSS_ORGAN: frozenset[tuple[str, str, str]] = frozenset(
    {
        (
            "policy/kernel.py",
            "PolicyKernelAuthority",
            "check_api_token_or_loopback",
        ),
        (
            "policy/kernel.py",
            "PolicyKernelAuthority",
            "check_mutation_origin_or_token",
        ),
    }
)

_STORE_ATTRS = frozenset({"store", "journal", "_adapter"})


@dataclass(frozen=True, slots=True)
class PassthroughViolation:
    rel_path: str
    class_name: str
    method_name: str
    callee: str

    def __str__(self) -> str:
        return (
            f"{self.rel_path}::{self.class_name}.{self.method_name} is a banned "
            f"passthrough twin to module function {self.callee}()"
        )


def _is_public(name: str) -> bool:
    return not name.startswith("_")


def _body_is_single_return_of_name_call(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> str | None:
    """Return the bare Name callee when body is only ``return name(...)``."""
    if len(node.body) != 1:
        return None
    stmt = node.body[0]
    if not isinstance(stmt, ast.Return) or stmt.value is None:
        return None
    value = stmt.value
    if isinstance(value, ast.Call) and isinstance(value.func, ast.Name):
        if value.func.id == node.name:
            return value.func.id
    return None


def _is_store_facade_return(stmt: ast.stmt) -> bool:
    if not isinstance(stmt, ast.Return) or stmt.value is None:
        return False
    call = stmt.value
    if not isinstance(call, ast.Call):
        return False
    func = call.func
    if not isinstance(func, ast.Attribute):
        return False
    if not isinstance(func.value, ast.Attribute):
        # self.store.method(...)
        if isinstance(func.value, ast.Name) and func.value.id == "self":
            return func.attr in _STORE_ATTRS
        return False
    # self.store.method(...) where store is direct attr of self
    outer = func.value
    return (
        isinstance(outer.value, ast.Name)
        and outer.value.id == "self"
        and outer.attr in _STORE_ATTRS
    )


def _method_is_store_facade(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    if len(node.body) != 1:
        return False
    return _is_store_facade_return(node.body[0])


def _find_authority_classes(
    rel_path: str, tree: ast.Module
) -> list[tuple[str, ast.ClassDef]]:
    found: list[tuple[str, ast.ClassDef]] = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name.endswith("Authority"):
            found.append((rel_path, node))
    return found


def scan_authority_passthroughs(root: Path = AIOS_ROOT) -> list[PassthroughViolation]:
    violations: list[PassthroughViolation] = []
    for file_path in sorted(root.rglob("*.py")):
        rel_path = file_path.relative_to(root).as_posix()
        try:
            source = file_path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(file_path))
        except (OSError, SyntaxError):
            continue
        if not isinstance(tree, ast.Module):
            continue
        for path, class_node in _find_authority_classes(rel_path, tree):
            for child in class_node.body:
                if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                if not _is_public(child.name):
                    continue
                key = (path, class_node.name, child.name)
                if key in ACCEPTABLE_CROSS_ORGAN or key in ACCEPTABLE_STORE_FACADE:
                    continue
                if _method_is_store_facade(child):
                    continue
                callee = _body_is_single_return_of_name_call(child)
                if callee is not None:
                    violations.append(
                        PassthroughViolation(path, class_node.name, child.name, callee)
                    )
    return violations


def test_no_banned_authority_passthrough_twins() -> None:
    violations = scan_authority_passthroughs()
    assert not violations, "\n".join(str(v) for v in violations)


def test_scanner_detects_a_synthetic_passthrough(tmp_path: Path) -> None:
    probe = tmp_path / "probe.py"
    probe.write_text(
        "def classify(cmd):\n"
        "    return 'green'\n\n"
        "class SecurityGatewayAuthority:\n"
        "    def classify(self, cmd):\n"
        "        return classify(cmd)\n",
        encoding="utf-8",
    )
    violations = scan_authority_passthroughs(tmp_path)
    assert len(violations) == 1
    assert violations[0].method_name == "classify"


def test_scanner_allows_store_facade(tmp_path: Path) -> None:
    probe = tmp_path / "probe.py"
    probe.write_text(
        "class CapabilityAuthority:\n"
        "    def list_pending(self):\n"
        "        return self.store.list_pending()\n",
        encoding="utf-8",
    )
    assert scan_authority_passthroughs(tmp_path) == []


def test_scanner_allows_policy_kernel_cross_organ(tmp_path: Path) -> None:
    probe = tmp_path / "kernel.py"
    probe.write_text(
        "import edge_security\n\n"
        "class PolicyKernelAuthority:\n"
        "    def check_api_token_or_loopback(self, request):\n"
        "        return edge_security.get_edge_trust_authority()"
        ".check_api_token_or_loopback(request)\n",
        encoding="utf-8",
    )
    assert scan_authority_passthroughs(tmp_path) == []
