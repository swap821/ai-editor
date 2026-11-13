"""A standard-library logger takes no fields as keywords (2026-11-13).

Found while running GAGOS's first mission through the council: the
orchestrator's best-effort journal and its promotion failure path logged with
``_LOGGER.warning("...", mission_id=..., exc_info=exc)``. That is structlog's
spelling; on a ``logging.getLogger`` logger it raises TypeError, so the
failure path that was meant to record a problem and carry on crashed the run
instead. Fields go in ``extra``.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_LEVELS = {"debug", "info", "warning", "error", "exception", "critical", "log"}
_ALLOWED = {"exc_info", "extra", "stack_info", "stacklevel"}


def _stdlib_loggers(tree: ast.AST) -> set[str]:
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            func = node.value.func
            if (
                isinstance(func, ast.Attribute)
                and func.attr == "getLogger"
                and getattr(func.value, "id", None) == "logging"
            ):
                names.update(t.id for t in node.targets if isinstance(t, ast.Name))
    return names


def stray_keywords(source: str) -> list[tuple[int, list[str]]]:
    tree = ast.parse(source)
    loggers = _stdlib_loggers(tree)
    found = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in _LEVELS
            and getattr(node.func.value, "id", None) in loggers
        ):
            stray = [k.arg for k in node.keywords if k.arg and k.arg not in _ALLOWED]
            if stray:
                found.append((node.lineno, stray))
    return found


def test_no_stdlib_logger_call_passes_fields_as_keywords() -> None:
    offenders = []
    for path in sorted((ROOT / "aios").rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        if "logging.getLogger" not in source:
            continue
        for line, stray in stray_keywords(source):
            offenders.append(f"{path.relative_to(ROOT).as_posix()}:{line} {stray}")
    assert offenders == [], "use extra={...}: " + "; ".join(offenders)


def test_the_scan_sees_the_shape_that_crashed() -> None:
    source = (
        "import logging\n_LOGGER = logging.getLogger(__name__)\n"
        "_LOGGER.warning('x', mission_id='m', exc_info=True)\n"
        "_LOGGER.warning('y', extra={'mission_id': 'm'}, exc_info=True)\n"
    )
    assert stray_keywords(source) == [(3, ["mission_id"])]


def test_a_journal_that_fails_never_fails_the_mission(tmp_path) -> None:
    from aios.council import CouncilOrchestrator
    from aios.core.autonomy import UNGOVERNED_FIXTURE

    class Broken:
        def append(self, mission_id, transition):
            raise RuntimeError("journal down")

    orchestrator = CouncilOrchestrator(
        runtime_root=tmp_path,
        emergency_stop=UNGOVERNED_FIXTURE,
        mission_journal=Broken(),
    )
    orchestrator._journal_append("mission-0123456789ab", "APPROVED")
