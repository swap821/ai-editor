"""GAGOS's daily frontend worker, the deterministic path (2026-10-30).

The frontend twin of the dead-import repair, through the same governed
pipeline: an admitted scanner finds, the worker proposes a registered
operation, an executor applies it in a staged copy, and the promotion smoke
judges the promoted file. Pinned here:

* the scanner reads through its bounded context, is project-rooted, never
  reports a file the lab-to-product port owns, and reports only what the
  operation can remove;
* the worker picks the frontend operation for the frontend scanner's findings;
* both executors run it, keeping line endings;
* staged copies never copy or hash ``node_modules``;
* a frontend target is really checked at promotion (it used to pass with "no
  Python targets"), and no toolchain is a failure, never a pass.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from aios.application.executor.service import execute_registered_repair_operation
from aios.application.promotion import smoke as smoke_module
from aios.application.promotion.smoke import python_smoke
from aios.application.workers.strategies import code_repair
from aios.application.workspaces.staged import tree_digest
from aios.domain.maintenance.lifecycle import MaintenanceLifecycleEngine
from aios.domain.maintenance.scanners import (
    FRONTEND_UNUSED_IMPORT_SCANNER_ID,
    frontend_unused_import_scanner,
    get_admitted_scanners,
)
from aios.domain.maintenance.service import AutonomousMaintenanceForce
from aios.executor_service import execute_registered_operation_in_service
from aios.maintenance.repair_operations import REMOVE_UNUSED_FRONTEND_IMPORTS_V1
from tests.test_maintenance_dead_import_mission import _contract, _job

PANEL = (
    "import { useState, useMemo } from 'react';\n"
    "import { Gauge } from './gauge';\n"
    "export function Panel() {\n"
    "  const v = useMemo(() => 1, []);\n"
    "  return <Gauge value={v} />;\n"
    "}\n"
)


def _frontend(root: Path) -> Path:
    files = {
        "frontend/src/workbench/Panel.jsx": PANEL,
        "frontend/src/workbench/Clean.tsx": "import { a } from './a';\nexport const b = a;\n",
        "frontend/src/superbrain/lib/Owned.ts": "import { unused } from './x';\nexport const y = 1;\n",
        "frontend/superbrain-source.json": json.dumps(
            {"version": 2, "files": {"lib/Owned.ts": "digest"}}
        ),
    }
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


def _scan(root: Path, target: str | None = None):
    return AutonomousMaintenanceForce(MaintenanceLifecycleEngine()).run_bounded_scan(
        _contract(root), frontend_unused_import_scanner, target_id=target
    )


# --------------------------------------------------------------------- scanner


def test_the_frontend_scanner_is_admitted_and_project_rooted() -> None:
    assert (
        get_admitted_scanners()[FRONTEND_UNUSED_IMPORT_SCANNER_ID]
        is frontend_unused_import_scanner
    )
    assert getattr(frontend_unused_import_scanner, "project_rooted", False)


def test_it_reports_unused_imports_but_never_a_port_owned_file(tmp_path) -> None:
    result = _scan(_frontend(tmp_path))
    findings = list(getattr(result, "findings", result))
    targets = {f.target_id: f for f in findings}
    assert set(targets) == {"frontend/src/workbench/Panel.jsx"}
    assert (
        "useState" in targets["frontend/src/workbench/Panel.jsx"].deterministic_evidence
    )
    assert (
        "Gauge"
        not in targets["frontend/src/workbench/Panel.jsx"].deterministic_evidence
    )


def test_a_target_narrows_what_is_reported(tmp_path) -> None:
    root = _frontend(tmp_path)
    clean = _scan(root, target="frontend/src/workbench/Clean.tsx")
    assert list(getattr(clean, "findings", clean)) == []


def test_a_scan_not_rooted_at_a_project_with_a_frontend_is_refused(tmp_path) -> None:
    root = _frontend(tmp_path)
    with pytest.raises(Exception):
        AutonomousMaintenanceForce(MaintenanceLifecycleEngine()).run_bounded_scan(
            _contract(root / "frontend"), frontend_unused_import_scanner
        )


# --------------------------------------------------------------------- worker


def test_the_worker_picks_the_frontend_operation_for_frontend_findings() -> None:
    assert (
        code_repair._OPERATION_FOR_SCANNER[FRONTEND_UNUSED_IMPORT_SCANNER_ID]
        == REMOVE_UNUSED_FRONTEND_IMPORTS_V1
    )


# --------------------------------------------------------------------- executors

EXPECTED = (
    "import { useMemo } from 'react';\n"
    "import { Gauge } from './gauge';\n"
    "export function Panel() {\n"
    "  const v = useMemo(() => 1, []);\n"
    "  return <Gauge value={v} />;\n"
    "}\n"
)


def test_the_in_process_executor_runs_the_operation(tmp_path) -> None:
    root = _frontend(tmp_path)
    rel = "frontend/src/workbench/Panel.jsx"
    execute_registered_repair_operation(
        _job(root, rel, op=REMOVE_UNUSED_FRONTEND_IMPORTS_V1)
    )
    assert (root / rel).read_text(encoding="utf-8") == EXPECTED


def test_the_executor_service_runs_the_operation_and_keeps_crlf(
    tmp_path, monkeypatch
) -> None:
    root = _frontend(tmp_path / "ws")
    rel = "frontend/src/workbench/Panel.jsx"
    (root / rel).write_bytes(PANEL.replace("\n", "\r\n").encode())
    monkeypatch.setenv("AIOS_EXECUTOR_WORKSPACE_ROOT", str(tmp_path))
    result = execute_registered_operation_in_service(
        _job(root, rel, op=REMOVE_UNUSED_FRONTEND_IMPORTS_V1)
    )
    assert result.status == "completed", result.reason
    assert (root / rel).read_bytes() == EXPECTED.replace("\n", "\r\n").encode()


def test_nothing_to_remove_is_a_refusal_not_a_silent_success(
    tmp_path, monkeypatch
) -> None:
    root = _frontend(tmp_path / "ws")
    monkeypatch.setenv("AIOS_EXECUTOR_WORKSPACE_ROOT", str(tmp_path))
    result = execute_registered_operation_in_service(
        _job(
            root,
            "frontend/src/workbench/Clean.tsx",
            op=REMOVE_UNUSED_FRONTEND_IMPORTS_V1,
        )
    )
    assert result.status == "failed" and "refused" in result.reason


# --------------------------------------------------------------------- staging


def test_staged_copies_never_copy_or_hash_node_modules(tmp_path) -> None:
    root = _frontend(tmp_path / "project")
    modules = root / "frontend" / "node_modules" / "pkg"
    modules.mkdir(parents=True)
    (modules / "index.js").write_text("module.exports = 1\n", encoding="utf-8")
    before = tree_digest(root)
    (modules / "index.js").write_text("module.exports = 2\n", encoding="utf-8")
    assert tree_digest(root) == before, "dependency installs are not project content"

    from aios.application.workspaces import StagedWorkspaceManager

    manager = StagedWorkspaceManager(tmp_path / "staging", enrolled_roots=(root,))
    lease = manager.stage("mission-node-modules", root)
    staged = Path(lease.workspace_path)
    assert (staged / "frontend/src/workbench/Panel.jsx").is_file()
    assert not (staged / "frontend" / "node_modules").exists()


# --------------------------------------------------------------------- smoke


def _toolchain(root: Path) -> None:
    modules = root / "frontend" / "node_modules"
    for rel in ("typescript/package.json", "eslint/bin/eslint.js", "vitest/vitest.mjs"):
        (modules / rel).parent.mkdir(parents=True, exist_ok=True)
        (modules / rel).write_text("", encoding="utf-8")


def _runner(*, parse_ok=True, eslint=None, vitest_ok=True, seen=None):
    def run(argv, **kwargs):
        if seen is not None:
            seen.append(argv)
        name = " ".join(str(a) for a in argv)
        if "transpileModule" in name:
            return SimpleNamespace(
                returncode=0 if parse_ok else 1, stdout="", stderr=""
            )
        if "eslint.js" in name:
            payload = eslint if eslint is not None else [{"messages": []}]
            return SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr="")
        if "vitest.mjs" in name:
            return SimpleNamespace(
                returncode=0 if vitest_ok else 1, stdout="", stderr=""
            )
        raise AssertionError(f"unexpected command: {name}")

    return run


@pytest.fixture()
def node(monkeypatch):
    monkeypatch.setattr(smoke_module.shutil, "which", lambda name: "node")


def test_a_frontend_target_is_no_longer_waved_through(tmp_path, node) -> None:
    """Before 2026-10-30 this returned passed=True, "no Python targets"."""
    root = _frontend(tmp_path)
    report = python_smoke(
        root, ["frontend/src/workbench/Panel.jsx"], timeout_s=60, run=_runner()
    )
    assert report.passed is False
    assert "npm ci" in report.reason


def test_a_frontend_target_that_parses_lints_and_tests_clean_passes(
    tmp_path, node
) -> None:
    root = _frontend(tmp_path)
    _toolchain(root)
    seen: list = []
    report = python_smoke(
        root, ["frontend/src/workbench/Panel.jsx"], timeout_s=60, run=_runner(seen=seen)
    )
    assert report.passed, report.reason
    assert [s.name for s in report.steps] == [
        "frontend toolchain",
        "parse (TypeScript)",
        "eslint",
        "vitest related",
    ]
    assert any("related" in argv for argv in seen)


@pytest.mark.parametrize(
    ("runner", "reason"),
    [
        (_runner(parse_ok=False), "does not parse"),
        (_runner(eslint=[{"messages": [{"severity": 2}]}]), "ESLint reports 1 error"),
        (_runner(vitest_ok=False), "related to the frontend targets"),
    ],
)
def test_each_frontend_check_can_fail_the_promotion(
    tmp_path, node, runner, reason
) -> None:
    root = _frontend(tmp_path)
    _toolchain(root)
    report = python_smoke(
        root, ["frontend/src/workbench/Panel.jsx"], timeout_s=60, run=runner
    )
    assert report.passed is False and reason in report.reason


def test_eslint_warnings_alone_do_not_fail_the_promotion(tmp_path, node) -> None:
    root = _frontend(tmp_path)
    _toolchain(root)
    runner = _runner(eslint=[{"messages": [{"severity": 1}]}])
    report = python_smoke(
        root, ["frontend/src/workbench/Panel.jsx"], timeout_s=60, run=runner
    )
    assert report.passed, report.reason


def test_the_real_parse_check_runs_with_the_repositorys_own_typescript(
    tmp_path,
) -> None:
    """The node script itself, against the real TypeScript, when present."""
    import shutil

    from aios import config

    typescript = Path(config.PROJECT_ROOT) / "frontend" / "node_modules" / "typescript"
    if shutil.which("node") is None or not typescript.is_dir():
        pytest.skip("no node or no frontend toolchain here")
    good = tmp_path / "Good.jsx"
    good.write_text(EXPECTED, encoding="utf-8")
    bad = tmp_path / "Bad.jsx"
    bad.write_text("export function (\n", encoding="utf-8")
    argv = ["node", "-e", smoke_module._PARSE_SCRIPT, str(typescript)]
    assert subprocess.run([*argv, str(good)], capture_output=True).returncode == 0
    assert subprocess.run([*argv, str(bad)], capture_output=True).returncode == 1
