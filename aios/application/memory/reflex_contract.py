"""The contract a reflex must satisfy before it may fire (plan Phase 5b).

Operator decision, 2026-09-29 ("1+2 both honestly"): a reflex fires only if
its skill passes ``SkillApplicabilityEngine`` -- the governed stack's
definition of "this skill applies here" -- and a skill is given the structured
contract that engine demands when its arc is born. This module derives that
contract from the arc's own steps, so nothing is invented:

* **verification plan** -- an allow-listed ``skill.reuse`` spec whose target
  is the relative file the arc's own test-runner step verifies. An arc with no
  recognised test runner gets NO plan: an ``echo`` is not verification, so such
  an arc can never pass the engine.
* **validated versions** -- a content hash of every file the arc's steps name,
  each read where the replay would touch it (file tools: the agent's read root;
  commands: the executor's ``command_cwd()``). An eligible (STRONG) success
  appends the hash of the code it actually ran against, so a reflex fires only
  on code it was verified on: freshness (threat T7). A success on other targets
  vouches for nothing here.
* **allowed scope** -- the declared scope roots the arc was learned in.
* **source trajectories** -- a reference to the arc's evidence trail. The live
  path records attempts as a trail, not per-run trajectories; that is stated.

Deterministic, file reads only, never raises on a missing file.
"""

from __future__ import annotations

import hashlib
import os
import re
import shlex
from pathlib import Path
from typing import Iterable, Optional

from aios import config
from aios.core.verification_strength import (
    VerificationStrength,
    _is_test_runner,  # read-only use of the recognised-runner rule
)
from aios.domain.verification.contracts import SkillVerifierSpec
from aios.security.scope_lock import command_cwd, get_scope_roots

#: The tools a reflex may replay: its "mission tool contract".
REFLEX_TOOLS = frozenset(
    {
        "read_file",
        "read_directory",
        "verify",
        "execute_terminal",
        "create_file",
        "edit_file",
    }
)
#: What a reuse of the plan must observe.
REUSE_OBSERVATION = "tests passed"
#: How many validated versions a skill keeps (newest last).
MAX_VALIDATED_VERSIONS = 20

#: What a read-only reuse must observe: the files it reads are a version it
#: was validated on (operator decision, 2026-09-29).
FRESHNESS_OBSERVATION = "read targets match a validated version"

#: ``SkillApplicabilityEngine``'s refusal when the code a skill touches is not
#: a version it was validated on -- the one way to tell staleness from every
#: other refusal. Pinned to the engine's own wording by a test.
STALE_REFUSAL = "Validated project version does not match the skill"

_FILE = "file"
_COMMAND = "command"
_READ_TOOLS = ("read_file", "read_directory")
_FILE_TOOLS = ("read_file", "read_directory", "create_file", "edit_file")
_COMMAND_TOOLS = ("verify", "execute_terminal")
_EXTENSION = re.compile(r"\.[A-Za-z0-9]{1,8}$")


def _split(step: str) -> tuple[str, str]:
    """``"verify: command=pytest x -q"`` -> ``("verify", "pytest x -q")``."""
    tool, _, rest = str(step).partition(":")
    rest = rest.strip()
    head = rest.split(" ", 1)[0]
    if "=" in head:
        _, _, rest = rest.partition("=")
    return tool.strip(), rest.strip()


def _normalise(path: str) -> str:
    path = path.replace("\\", "/")
    return path[2:] if path.startswith("./") else path


def _path_tokens(command: str) -> list[str]:
    try:
        parts = shlex.split(command, posix=True)
    except ValueError:
        parts = command.split()
    return [
        _normalise(p)
        for p in parts
        if not p.startswith("-") and ("/" in p or "\\" in p or _EXTENSION.search(p))
    ]


def _located_targets(steps: Iterable[str]) -> list[tuple[str, str]]:
    """``(kind, target)`` for every file the arc's steps name, sorted. *kind*
    says which base the replay resolves it against (see :func:`_base`)."""
    found: set[tuple[str, str]] = set()
    for step in steps:
        tool, value = _split(step)
        if tool in _FILE_TOOLS and value:
            found.add((_FILE, _normalise(value)))
        elif tool in _COMMAND_TOOLS:
            found.update((_COMMAND, token) for token in _path_tokens(value))
    return sorted(t for t in found if t[1])


def _base(kind: str) -> Path:
    """Where a replayed step touches a relative target -- the same derivation
    each acting layer uses, never a second one (a check resolved against a
    different base than the act checks nothing):

    * file tools: the agent's read root, ``config.PROJECT_ROOT`` (no
      production caller overrides ``ToolAgent.read_root``);
    * commands: ``scope_lock.command_cwd()``, the directory the executor runs
      them in -- the first scope root's parent.
    """
    return Path(config.PROJECT_ROOT) if kind == _FILE else command_cwd()


def _resolve(kind: str, target: str) -> Path:
    return _base(kind) / target


def step_targets(steps: Iterable[str]) -> list[str]:
    """Every file the arc's steps name, case preserved, sorted."""
    return sorted({target for _, target in _located_targets(steps)})


def created_targets(steps: Iterable[str]) -> set[str]:
    return {
        _normalise(value)
        for tool, value in (_split(s) for s in steps)
        if tool == "create_file" and value
    }


def validated_version(steps: Iterable[str]) -> str:
    """A content hash of the files the arc touches, as they are now, each read
    where the replay would touch it. A file is its bytes. A directory is its
    listing exactly as ``read_directory`` reads it (one derivation): a reflex
    that lists a directory goes stale when an entry is added or removed. What
    is inside a directory is not hashed -- a stated limit, see
    ``docs/learning/PHASE5_DESIGN.md``."""
    from aios.agents.tool_handlers import read_directory

    digest = hashlib.sha256()
    for kind, target in _located_targets(list(steps)):
        path = _resolve(kind, target)
        try:
            if path.is_file():
                state = hashlib.sha256(path.read_bytes()).hexdigest()
            elif path.is_dir():
                listing, status, _ = read_directory(target, read_root=_base(kind))
                state = (
                    "directory:"
                    + hashlib.sha256(f"{status}\0{listing}".encode("utf-8")).hexdigest()
                )
            else:
                state = "missing"
        except OSError:
            state = "unreadable"
        digest.update(f"{kind}:{target}\0{state}\n".encode("utf-8"))
    return digest.hexdigest()[:32]


def verification_plan(steps: Iterable[str]) -> Optional[SkillVerifierSpec]:
    """The allow-listed plan from the arc's own steps, or ``None``.

    * An arc with a recognised test-runner step: that runner, on its relative
      target, must pass (``tests passed``).
    * An arc made ONLY of reads (operator decision, 2026-09-29): its check is
      freshness -- the files it reads are exactly a validated version. A read
      has no effect to verify; what must hold is that it reads what was
      validated.
    * Anything else (a command that is not a test runner, a write with no
      test): no plan, so ``SkillApplicabilityEngine`` refuses it.
    """
    steps = list(steps)
    for step in steps:
        tool, command = _split(step)
        if tool not in _COMMAND_TOOLS or not _is_test_runner(command):
            continue
        for target in _path_tokens(command):
            try:
                return SkillVerifierSpec(
                    target_pattern=target,
                    required_observations=(REUSE_OBSERVATION,),
                    minimum_strength=int(VerificationStrength.STRONG),
                )
            except ValueError:
                continue
    parsed = [_split(step) for step in steps]
    if parsed and all(tool in _READ_TOOLS and value for tool, value in parsed):
        try:
            return SkillVerifierSpec(
                target_pattern=_normalise(parsed[0][1]),
                required_observations=(FRESHNESS_OBSERVATION,),
                minimum_strength=int(VerificationStrength.STRONG),
            )
        except ValueError:
            return None
    return None


def plan_executable(plan: Optional[SkillVerifierSpec], steps: Iterable[str]) -> bool:
    """The plan's target exists where the replay would touch it, or the reflex
    itself creates it there. A freshness plan names a read target (a file-tool
    path); a test-runner plan names a command token."""
    if plan is None:
        return False
    kind = _FILE if FRESHNESS_OBSERVATION in plan.required_observations else _COMMAND
    target = _resolve(kind, plan.target_pattern).resolve()
    created = {_resolve(_FILE, path).resolve() for path in created_targets(steps)}
    return target.exists() or target in created


def scope_identity() -> str:
    """The declared scope roots, relative to the project where possible."""
    parts = []
    for root in get_scope_roots():
        try:
            rel = os.path.relpath(Path(root), config.PROJECT_ROOT)
        except ValueError:  # another drive
            rel = str(root)
        parts.append(rel.replace("\\", "/"))
    return ",".join(sorted(parts))


def trail_reference(skill_id: str, version: int) -> str:
    return f"skill-trail:{skill_id}@{version}"


def procedure_steps(procedure: str) -> Optional[list[str]]:
    """A library procedure as arc steps, or ``None`` when it is not an arc."""
    import json

    try:
        steps = json.loads(procedure)
    except (TypeError, ValueError):
        return None
    if isinstance(steps, list) and steps and all(isinstance(s, str) for s in steps):
        return steps
    return None


def with_validated(versions: Iterable[str], version: str) -> list[str]:
    kept = [v for v in versions if v != version]
    kept.append(version)
    return kept[-MAX_VALIDATED_VERSIONS:]


def stamp_for_activation(record):  # noqa: ANN001, ANN201 - SkillRecord in and out
    """The operator's activation fills in a skill's reflex contract.

    For a ``candidate`` (the contract is still writable): any missing plan,
    scope and trail reference are derived from its own steps, exactly as a
    skill born on the live path gets them. For every activation: the code
    state now is appended as a validated version -- the operator's activation
    is the human judgment that the skill applies to the code as it is.
    Not an arc (a procedure that is not a list of steps): returned unchanged.
    """
    steps = procedure_steps(record.procedure)
    if steps is None:
        return record
    update: dict = {
        "last_validated_versions": with_validated(
            record.last_validated_versions, validated_version(steps)
        )
    }
    if record.state == "candidate":
        if record.verification_plan is None:
            update["verification_plan"] = verification_plan(steps)
        if not record.allowed_scope_pattern:
            update["allowed_scope_pattern"] = scope_identity()
        if not record.source_trajectory_ids:
            update["source_trajectory_ids"] = [
                trail_reference(record.skill_id, record.version)
            ]
    return record.model_copy(update=update)


__all__ = [
    "MAX_VALIDATED_VERSIONS",
    "REFLEX_TOOLS",
    "FRESHNESS_OBSERVATION",
    "REUSE_OBSERVATION",
    "STALE_REFUSAL",
    "created_targets",
    "plan_executable",
    "procedure_steps",
    "scope_identity",
    "stamp_for_activation",
    "step_targets",
    "trail_reference",
    "validated_version",
    "verification_plan",
    "with_validated",
]
