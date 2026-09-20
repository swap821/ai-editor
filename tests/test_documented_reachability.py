"""What a module SAYS about its own reachability has to stay true.

Two subsystems in this repo were heavily built, heavily tested, and described
in a way the wiring did not support:

* ``aios/application/learning/service.py`` called itself the *canonical* skill
  flow while being reachable only from ``/api/v1/skills/*``. Every ordinary
  chat turn uses a different store entirely (``aios.memory.skills``).
* ``aios/agents/swarm.py`` is complete and unreachable: ``generate_pipeline``
  rejects ``req.swarm`` unconditionally before any of it runs, and the SSE
  branches that handle its events sit after a ``return`` that always fires.

Neither is a bug in the code. Both were bugs in what the code claimed, which is
worse in one specific way: a reader auditing the product cannot tell a wired
subsystem from an unwired one, and every downstream judgement inherits the
error.

So both now state their real reachability, and this file pins the statement to
the wiring. If somebody connects the learning service to the turn path, or
removes the swarm gate, these tests fail — not because the change is wrong, but
because the docstring describing the old world would have quietly become false.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from aios import config

REPO = Path(config.PROJECT_ROOT)
TURN_PATH = REPO / "aios" / "application" / "turns"
AGENTS = REPO / "aios" / "agents"
LEARNING_SERVICE = REPO / "aios" / "application" / "learning" / "service.py"
SWARM = REPO / "aios" / "agents" / "swarm.py"
PIPELINE = TURN_PATH / "generate_pipeline.py"


def _imported_modules(path: Path) -> set[str]:
    """Every module name this file imports, including inside functions.

    Walked with ``ast`` rather than grepped because the interesting imports in
    this codebase are deliberately lazy — ``get_learning_service`` imports
    ``LearningService`` inside the function body to keep module load cheap, and
    a line-based search for a top-level import would have reported "not
    imported" for a module that very much is.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
        elif isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
    return names


def _python_files(root: Path) -> list[Path]:
    return [p for p in root.rglob("*.py") if "__pycache__" not in p.parts]


class TestTheLearningServiceIsMissionScopedNotCanonical:
    def test_the_turn_path_does_not_reach_it(self) -> None:
        offenders = [
            p.relative_to(REPO).as_posix()
            for p in _python_files(TURN_PATH)
            if any(
                mod.startswith("aios.application.learning.service")
                or mod == "aios.application.learning"
                for mod in _imported_modules(p)
            )
        ]
        assert not offenders, (
            "the turn path now reaches LearningService, so its docstring — which "
            f"states that it does not — is out of date: {offenders}"
        )

    def test_the_agent_loop_does_not_reach_it_either(self) -> None:
        offenders = [
            p.relative_to(REPO).as_posix()
            for p in _python_files(AGENTS)
            if any(
                mod.startswith("aios.application.learning.service")
                for mod in _imported_modules(p)
            )
        ]
        assert not offenders, offenders

    def test_it_no_longer_claims_to_be_canonical(self) -> None:
        """The specific word that made a true architecture read as a false one."""
        first_line = LEARNING_SERVICE.read_text(encoding="utf-8").splitlines()[0]
        assert "anonical" not in first_line, (
            "the module summary calls itself canonical again; it is reachable "
            "only from /api/v1/skills/*, and the chat turn uses SkillMemory"
        )

    def test_it_says_where_the_turn_path_system_actually_lives(self) -> None:
        """A correction that does not point at the truth is half a correction."""
        text = LEARNING_SERVICE.read_text(encoding="utf-8")
        assert "aios.memory.skills" in text
        assert "/api/v1/skills/" in text


class TestTheSwarmIsDormantAndSaysSo:
    def test_the_gate_that_makes_it_unreachable_still_exists(self) -> None:
        """If this gate goes, the dormancy banner is a lie and must be rewritten."""
        source = PIPELINE.read_text(encoding="utf-8")
        assert "if req.swarm or req.role_pass:" in source
        assert "strategy_unavailable" in source

    def test_the_gate_is_unconditional(self) -> None:
        """No flag opens it — that is why 'dormant' is accurate and not pessimism."""
        source = PIPELINE.read_text(encoding="utf-8")
        gate = source.index("if req.swarm or req.role_pass:")
        body = source[gate : gate + 700]
        assert "strategy_unavailable" in body
        assert "return" in body
        assert "SWARM_ENABLED" not in body, (
            "a flag now guards the gate, so the swarm is conditionally reachable "
            "and its docstring must stop saying nothing can reach it"
        )

    def test_the_module_declares_its_dormancy(self) -> None:
        head = SWARM.read_text(encoding="utf-8")[:1600]
        assert "DORMANT" in head
        assert "strategy_unavailable" in head, (
            "the banner must name the gate, so a reader can check the claim "
            "instead of trusting it"
        )


class TestTheseChecksCanActuallyFail:
    """A guard that cannot fire is the thing this whole file is about."""

    def test_the_import_walker_sees_a_lazy_function_level_import(
        self, tmp_path
    ) -> None:
        probe = tmp_path / "probe.py"
        probe.write_text(
            "def f():\n    from aios.application.learning.service import LearningService\n"
            "    return LearningService\n",
            encoding="utf-8",
        )
        assert "aios.application.learning.service" in _imported_modules(probe)

    def test_the_import_walker_sees_a_plain_import(self, tmp_path) -> None:
        probe = tmp_path / "probe2.py"
        probe.write_text("import aios.agents.swarm\n", encoding="utf-8")
        assert "aios.agents.swarm" in _imported_modules(probe)

    def test_deps_really_is_the_one_production_caller(self) -> None:
        """Pins the positive half: the claim is 'only here', not 'nowhere'."""
        deps = REPO / "aios" / "api" / "deps.py"
        assert "aios.application.learning.service" in _imported_modules(deps)


@pytest.mark.parametrize("path", [LEARNING_SERVICE, SWARM, PIPELINE])
def test_the_pinned_files_exist(path: Path) -> None:
    """A moved file would make every assertion above pass vacuously."""
    assert path.is_file(), f"{path} moved; these reachability pins now test nothing"
