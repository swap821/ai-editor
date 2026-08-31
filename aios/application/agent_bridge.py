"""Adjudicate an EXTERNAL CLI agent's proposed tool call against the GAGOS gates.

Munder Difflin ships the shape this serves: wrap Claude Code / Codex / Copilot
CLI in a PTY so an operator uses subscriptions they already pay for. What that
design leaves open is authority -- its orchestrator is a "GOD agent" that reads
requests and decides, i.e. a model adjudicating models, which is precisely what
VerificationStrength exists to refuse.

This module is the other half: before an external agent runs a tool, the call is
routed through the SAME gates the in-process agent passes -- gateway.classify
for zone, scope_lock for containment -- and the verdict is recorded.

WHAT THIS IS NOT
----------------
It is NOT the boundary the in-process executor is. That path cannot be bypassed:
the agent has no way to reach a subprocess except through Executor.execute.
Here, the external agent CHOOSES to consult us -- Claude Code's PreToolUse hook
can block a call, but only because Claude Code honours its own hook. A patched
client, a different agent, or a crashed hook simply does not ask.

So this raises the floor from "opaque subprocess" to "adjudicated and recorded".
It does not reach "contained". Anyone reading a refusal here should know which
of the two they are looking at; claiming otherwise would be the overclaim organ
46 exists to catch.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from aios import config
from aios.policy.credential_paths import (
    is_credential_path,
    refusal_reason,
)
from aios.security import scope_lock
from aios.security.gateway import Zone, classify

#: Tools whose payload is a shell command.
_COMMAND_TOOLS = frozenset(
    {"Bash", "BashOutput", "Shell", "Terminal", "execute_terminal"}
)
#: Tools that WRITE to a path -- gated against the sandbox scope roots.
_WRITE_TOOLS = frozenset(
    {"Write", "Edit", "MultiEdit", "NotebookEdit", "create_file", "edit_file"}
)
#: Tools that only READ -- gated against the project root, never wider.
_READ_TOOLS = frozenset({"Read", "Glob", "Grep", "read_file", "read_directory"})

#: Path markers that carry credentials. A read is not harmless when the bytes
#: are a key: VII.4 keeps secrets off disk and out of logs, and handing one to
#: an external agent's context is the same leak by another route.
#: Superseded by aios.policy.credential_paths. Kept only as a doc of what the
#: basename-only version caught, because the gap it left was structural: it
#: matched the FINAL segment only, so `.aws/credentials`, `.ssh/config`,
#: `.git/config` and `.docker/config.json` were all invisible to it -- every
#: credential store that identifies itself by its directory. It also guarded
#: reads only, so a bridge-authorized agent could not read `.env` but could
#: overwrite it.
_LEGACY_SECRET_MARKERS = (".env", "id_rsa", "credentials.json", ".pem", ".key", ".p12")


@dataclass(frozen=True)
class BridgeDecision:
    """One adjudication. ``allowed`` is the answer; the rest is the record."""

    allowed: bool
    reason: str
    tool: str
    zone: str = "N/A"
    target: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "tool": self.tool,
            "zone": self.zone,
            "target": self.target,
        }


def _first_str(payload: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def looks_secret_bearing(path: str) -> bool:
    """Whether a path names credential material rather than source.

    Delegates to the single repo-wide predicate. This function used to carry its
    own basename-substring answer, which disagreed with what every other
    chokepoint would have said -- and since it was the ONLY chokepoint that
    asked, the disagreement was invisible.
    """
    return is_credential_path(path)


def authorize(
    tool_name: str,
    tool_input: Optional[dict[str, Any]] = None,
    *,
    cwd: Optional[Path] = None,
) -> BridgeDecision:
    """Decide whether an external agent may run *tool_name* with *tool_input*.

    Fail-closed on anything unrecognised: a tool this does not model is a tool
    whose blast radius is unknown, and unknown is not safe.
    """
    payload = tool_input if isinstance(tool_input, dict) else {}
    name = (tool_name or "").strip()
    # An external agent runs with cwd at the PROJECT ROOT, not the scope root.
    # Resolving a bare relative path against the scope root would double-join it
    # (x.py -> training_ground/x.py) and report an out-of-tree path as contained
    # -- the same base mismatch that made training_ground/../X a live escape.
    # Resolve where the agent actually stands.
    base = Path(cwd) if cwd else Path(config.PROJECT_ROOT)

    if name in _COMMAND_TOOLS:
        command = _first_str(payload, "command", "cmd", "script")
        if not command:
            return BridgeDecision(False, "No command supplied to a command tool.", name)
        verdict = classify(command)
        zone = getattr(verdict.zone, "name", str(verdict.zone))
        if verdict.zone is Zone.RED:
            return BridgeDecision(False, "RED: " + str(verdict.reason), name, zone, command)
        scope = scope_lock.command_stays_in_scope(command)
        if not scope.in_scope:
            return BridgeDecision(
                False, "Out of scope: " + str(scope.reason), name, zone, command
            )
        if verdict.zone is Zone.YELLOW:
            return BridgeDecision(
                False,
                "YELLOW needs operator approval; the bridge does not grant it. "
                + str(verdict.reason),
                name, zone, command,
            )
        return BridgeDecision(True, "GREEN and within scope.", name, zone, command)

    if name in _WRITE_TOOLS:
        target = _first_str(payload, "file_path", "filepath", "path", "notebook_path")
        if not target:
            return BridgeDecision(False, "No path supplied to a write tool.", name)
        resolved = target if Path(target).is_absolute() else str((base / target).resolve())
        check = scope_lock.is_path_in_scope(resolved)
        if not check.in_scope:
            roots = ", ".join(str(r) for r in scope_lock.get_scope_roots())
            return BridgeDecision(
                False,
                "Write outside the sandbox scope (" + roots + "): " + str(check.reason),
                name, "N/A", target,
            )
        # In scope is not permission to WRITE credential material. Reads were
        # guarded here from the start and writes were not, so the bridge refused
        # to show an agent `.env` while letting it overwrite the file.
        if is_credential_path(target) or is_credential_path(resolved):
            return BridgeDecision(False, refusal_reason(target), name, "N/A", target)
        return BridgeDecision(True, "Write within the sandbox scope.", name, "N/A", target)

    if name in _READ_TOOLS:
        target = _first_str(payload, "file_path", "filepath", "path", "pattern")
        if not target:
            return BridgeDecision(True, "Read with no explicit path.", name, "N/A", "")
        if looks_secret_bearing(target):
            return BridgeDecision(
                False,
                "Refused: the path names credential material, and handing a key to "
                "an external agent's context is a leak (AGENTS.md VII.4).",
                name, "N/A", target,
            )
        resolved = Path(target) if Path(target).is_absolute() else (base / target)
        try:
            resolved.resolve().relative_to(Path(config.PROJECT_ROOT).resolve())
        except ValueError:
            return BridgeDecision(
                False, "Read outside the project root.", name, "N/A", target
            )
        return BridgeDecision(True, "Read within the project root.", name, "N/A", target)

    return BridgeDecision(
        False,
        "Unmodelled tool " + repr(name) + ": the bridge fails closed on tools whose "
        "blast radius it cannot reason about.",
        name,
    )
