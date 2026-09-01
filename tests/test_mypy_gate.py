"""The security spine is type-checked, at zero, and the gate actually runs.

Inventory item 86 / Ultra-plan Phase 8.

Gated at ZERO rather than ratcheted, unlike bandit. That asymmetry is deliberate:
bandit found 141 pre-existing findings and a budget was the only way to land a
gate at all; mypy on the security subset found **11**, small enough to fix
outright. A budget for 11 would institutionalise a pile that could simply be
cleared.

The first run paid for the whole exercise, finding two live bugs no test caught:

* `core/executor.py` — the subprocess-timeout path used four POSIX-only names
  (`signal.SIGCONT`, `os.killpg`, `os.getpgid`, `signal.SIGKILL`) guarded by
  `except (OSError, ProcessLookupError)`. None exist on Windows, so
  `AttributeError` escaped, the `process.kill()` fallback was unreachable, and a
  timed-out child was left RUNNING. See
  `tests/test_executor_timeout_kill_is_cross_platform.py`.
* `api/main.py` and `api/routes/skills.py` — FastAPI dependency annotations
  naming types that were never imported. See
  `tests/test_route_annotations_resolve.py`.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "check_mypy.py"


def _load():
    spec = importlib.util.spec_from_file_location("_mypy_gate", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_gate_runs_in_ci() -> None:
    """A gate nobody invokes is a claim."""
    workflow = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )
    assert "python scripts/check_mypy.py" in workflow, (
        "the mypy gate is no longer invoked by ci.yml"
    )
    assert "mypy==" in workflow, (
        "mypy is not pinned in CI; an unpinned type checker changes its findings "
        "under you and a zero-error gate becomes a random failure"
    )


def test_the_checked_paths_cover_the_frozen_core() -> None:
    """The spine is the whole point of starting here.

    If a frozen-core module drops out of the checked set, the gate keeps passing
    while covering less -- the same shape as the route sweep that silently
    covered a fifth of the app.
    """
    from aios.policy.constitution import FROZEN_PATH_PREFIXES

    module = _load()
    checked = set(module.CHECKED_PATHS)
    for prefix in FROZEN_PATH_PREFIXES:
        assert prefix in checked or any(p.startswith(prefix) for p in checked), (
            f"frozen prefix {prefix!r} is not covered by the mypy gate; the "
            "security spine must stay type-checked"
        )


def test_the_gate_is_scoped_so_it_reports_only_the_named_files() -> None:
    """`--follow-imports=silent` is load-bearing, not decoration.

    Without it the same subset reports 337 errors across 80 files, because mypy
    follows every import. A zero-error gate on that is unachievable, so removing
    the flag would silently make the gate impossible to satisfy and invite
    someone to weaken it instead.
    """
    module = _load()
    assert "--follow-imports=silent" in module.MYPY_ARGS


def test_the_gate_passes_on_the_current_tree() -> None:
    """Zero means zero."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        "the mypy gate does not pass on the current tree:\n"
        + (result.stdout + result.stderr)[-2000:]
    )
