"""A guardrail an agent can widen by editing a file is not a guardrail.

`aios/security/limits.py` holds the five values that decide how far this system
may reach: where it may act, whether it may act unattended, what may leave the
machine, how much destruction one session may propose, and what the audit chain
is anchored to. They were moved into the frozen core precisely so an agent with
ordinary edit rights could not raise its own ceiling.

There is a quieter half of that property, and it was neither documented nor
tested: `aios/config.py` imports `limits` at module top and calls
``load_dotenv`` several lines LATER, so the guardrails are resolved from the
real process environment before `.env` is ever read. Writing
``AIOS_ROUTER_CLOUD_TASKS=coding,reasoning`` into `.env` therefore does exactly
nothing — and `.env` is a file an agent can write.

Reordering those two lines looks like tidying. It would make every guardrail
configurable from inside the repository, which is the whole attack the frozen
core exists to prevent. So the order is pinned here, from both ends: the
structural fact (the import precedes the load) and the behavioural one (a value
in `.env` does not reach the guardrail).
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

from aios import config
from aios.security import limits

REPO = Path(config.PROJECT_ROOT)
CONFIG_PY = REPO / "aios" / "config.py"

#: Every guardrail `limits` reads from the environment. Named individually
#: rather than discovered, so ADDING one to the frozen core without adding it
#: here is a visible omission instead of a silent gap.
GUARDRAIL_ENV_VARS = (
    "AIOS_SCOPE_ROOTS",
    "AIOS_ROUTER_CLOUD_TASKS",
    "AIOS_EARNED_AUTONOMY",
    "AIOS_EARNED_AUTONOMY_MIN_SUCCESSES",
    "AIOS_MAX_RED_ACTIONS",
)


def _first_lineno(predicate) -> int:
    tree = ast.parse(CONFIG_PY.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if predicate(node):
            return node.lineno
    raise AssertionError("node not found in aios/config.py")


class TestTheImportOrderIsLoadBearing:
    def test_limits_is_imported_before_dotenv_is_loaded(self) -> None:
        limits_line = _first_lineno(
            lambda n: (
                isinstance(n, ast.ImportFrom)
                and n.module == "aios.security"
                and any(a.name == "limits" for a in n.names)
            )
        )
        dotenv_line = _first_lineno(
            lambda n: (
                isinstance(n, ast.Call)
                and isinstance(n.func, ast.Name)
                and n.func.id == "load_dotenv"
            )
        )
        assert limits_line < dotenv_line, (
            "load_dotenv now runs before aios.security.limits is imported, so "
            "every frozen guardrail is configurable from .env — a file an agent "
            "can write. That is the exact escalation the frozen core prevents."
        )

    def test_limits_does_not_load_dotenv_itself(self) -> None:
        """The same hole, reachable a second way."""
        source = (REPO / "aios" / "security" / "limits.py").read_text(encoding="utf-8")
        assert "dotenv" not in source


class TestTheBehaviourItself:
    """Structure can be satisfied while behaviour is not. Check both."""

    @pytest.mark.parametrize("var", GUARDRAIL_ENV_VARS)
    def test_a_value_written_to_dotenv_does_not_reach_the_guardrail(
        self, var, tmp_path
    ) -> None:
        """Run a real subprocess: this cannot be proven inside an imported module.

        `aios.config` is already imported in this process with the environment
        it had at startup, so any in-process manipulation would test the
        manipulation rather than the property.
        """
        project = tmp_path / "proj"
        (project / "aios").mkdir(parents=True)
        (project / ".env").write_text(f"{var}=SENTINEL_FROM_DOTENV\n", encoding="utf-8")

        probe = project / "probe.py"
        probe.write_text(
            "import os, sys\n"
            f"sys.path.insert(0, {str(REPO)!r})\n"
            "from aios.security import limits\n"
            "from aios import config\n"
            f"print('IN_ENVIRON', {var!r} in os.environ)\n"
            "print('SENTINEL_REACHED_LIMITS', 'SENTINEL_FROM_DOTENV' in repr(\n"
            "    [getattr(limits, n) for n in limits.__all__]\n"
            "))\n",
            encoding="utf-8",
        )
        result = subprocess.run(
            [sys.executable, str(probe)],
            cwd=str(project),
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert "SENTINEL_REACHED_LIMITS False" in result.stdout, (
            f"{var} written to .env reached a frozen guardrail:\n{result.stdout}"
        )


class TestTheGuardrailsAreStillWhereTheyShouldBe:
    def test_every_named_var_is_actually_read_by_limits(self) -> None:
        """Otherwise this file pins variables nobody consults."""
        source = (REPO / "aios" / "security" / "limits.py").read_text(encoding="utf-8")
        missing = [var for var in GUARDRAIL_ENV_VARS if var not in source]
        assert not missing, f"named here but not read by limits.py: {missing}"

    def test_config_re_exports_them_so_callers_are_unchanged(self) -> None:
        for name in (
            "SCOPE_ROOTS",
            "ROUTER_CLOUD_TASKS",
            "MAX_RED_ACTIONS_PER_SESSION",
        ):
            assert getattr(config, name) == getattr(limits, name)
