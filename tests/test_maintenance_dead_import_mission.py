"""GAGOS's first self-maintenance mission: the vulture's dead imports, repaired.

The pipeline (scan -> finding -> approved mission -> worker in a staged copy ->
executor -> rescan -> promotion -> smoke -> rescan) had only ever repaired a
literal marker in a fixture. Four things stopped it repairing a real project,
each pinned here:

* the only admitted scanner matched marker strings, so no real defect could
  become a finding;
* the rescan passed only when the WHOLE workspace was clean, which a real
  project never is -- verification is now about the repaired target;
* the production smoke check parsed, imported and tested nothing;
* staging the live checkout copied its own staging directory into itself
  until the Windows path limit (measured 2026-10-12).

The two end-to-end tests run the real scanner, the real code worker, the real
in-service executor operation, the real verifier registry and the real smoke
check on a throwaway project: one repair is promoted, one is rolled back by the
smoke because a test reached the "dead" import dynamically.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from aios.application.evidence.verification import VerificationAuthority
from aios.application.evidence.verifier_registry import VerifierRegistry
from aios.application.executor.service import (
    ExecutorService,
    execute_registered_repair_operation,
)
from aios.application.maintenance.service import MaintenanceConvergenceService
from aios.application.missions.mission_service import MissionService
from aios.application.promotion.authority import PromotionAuthority
from aios.application.promotion.smoke import python_smoke, find_exercising_tests
from aios.application.workers.foundry import WorkerFoundry
from aios.application.workers.strategies.code_repair import (
    ProductionCodeWorkerStrategy,
)
from aios.application.workspaces import StagedWorkspaceManager
from aios.application.workspaces.staged import WorkspacePathViolation
from aios.core.autonomy import UNGOVERNED_FIXTURE
from aios.domain.executor import ExecutorCapability, ExecutorJob, ResourceLimits
from aios.domain.maintenance.lifecycle import MaintenanceLifecycleEngine
from aios.domain.maintenance.repository import MaintenanceFindingRepository
from aios.domain.maintenance.scan_contracts import BoundedScanContract
from aios.domain.maintenance.scan_repository import MaintenanceScanRepository
from aios.domain.maintenance.scanners import (
    VULTURE_DEAD_IMPORT_SCANNER_ID,
    get_admitted_scanners,
    vulture_dead_import_scanner,
)
from aios.domain.maintenance.service import (
    AutonomousMaintenanceForce,
    ScanExecutionError,
)
from aios.domain.verification import VerifierSpec
from aios.domain.workers.worker_contract import WorkerStrategyName
from aios.executor_service import execute_registered_operation_in_service
from aios.infrastructure.missions.sqlite_mission_repository import (
    SqliteMissionRepository,
)
from aios.maintenance.repair_operations import (
    REMOVE_DEAD_IMPORTS_V1,
    remove_dead_imports,
)
from tests.helpers import consume_real_capability_proof

MOD = (
    "import json\n"
    "import os\n"
    "from collections import OrderedDict, deque\n"
    "\n"
    "\n"
    "def sep():\n"
    "    return os.sep\n"
)
TEST_MOD = "from pkg.mod import sep\n\n\ndef test_sep():\n    assert sep()\n"


def _project(root: Path, *, dynamic_use: bool = False) -> Path:
    files = {
        "pyproject.toml": "[project]\nname = 'demo'\n",
        "pkg/__init__.py": "",
        "pkg/mod.py": MOD,
        "pkg/other.py": "import sys\n",  # dead too: never blocks mod's repair
        "tests/test_mod.py": TEST_MOD,
    }
    if dynamic_use:
        # A use no static rule can see: the module arrives through importlib
        # into a plain local, and "json" is read off it. The index sees no
        # alias and no name -- only running the test finds the dependency.
        files["tests/test_mod.py"] = TEST_MOD + (
            "\n\ndef test_json_through_the_module():\n"
            "    import importlib\n"
            "    module = importlib.import_module('pkg.' + 'mod')\n"
            "    assert module.json.dumps([]) == '[]'\n"
        )
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


def _contract(root: Path, **overrides) -> BoundedScanContract:
    values = dict(
        allowed_root=str(root),
        max_files=500,
        max_total_bytes=10_000_000,
        max_file_bytes=1_000_000,
        deadline=120,
        max_findings=100,
        git_history_allowed=False,
    )
    values.update(overrides)
    return BoundedScanContract(**values)


def _scan(root: Path, target: str | None = None, **overrides):
    return AutonomousMaintenanceForce(MaintenanceLifecycleEngine()).run_bounded_scan(
        _contract(root, **overrides), vulture_dead_import_scanner, target_id=target
    )


# --------------------------------------------------------------------- operation


def test_the_operation_removes_only_dead_names_and_keeps_comments(tmp_path) -> None:
    text = (
        "from collections import OrderedDict, deque, Counter  # keep me\n"
        "import json\n"
        "Counter()\n"
    )
    repair = remove_dead_imports(text, path=tmp_path / "x.py", project_root=tmp_path)
    assert repair.content == "from collections import Counter  # keep me\nCounter()\n"
    assert repair.removed == ("OrderedDict", "deque", "json")


def test_the_operation_preserves_crlf_and_directives(tmp_path) -> None:
    text = (
        "from __future__ import annotations\r\n"
        "import os  # noqa: F401\r\n"
        "import json\r\n"
        "x = 1\r\n"
    )
    repair = remove_dead_imports(text, path=tmp_path / "x.py", project_root=tmp_path)
    assert repair.content == (
        "from __future__ import annotations\r\nimport os  # noqa: F401\r\nx = 1\r\n"
    )


def test_a_multiline_import_loses_only_the_lines_of_dead_names(tmp_path) -> None:
    text = "from os import (\n    sep,\n    getcwd,  # used\n)\ngetcwd()\n"
    repair = remove_dead_imports(text, path=tmp_path / "x.py", project_root=tmp_path)
    assert repair.content == "from os import (\n    getcwd,  # used\n)\ngetcwd()\n"


def test_unsafe_shapes_are_left_alone_and_reported(tmp_path) -> None:
    text = "import json; x = 1\nfrom os import (sep,\n    getcwd)\ngetcwd()\n"
    repair = remove_dead_imports(text, path=tmp_path / "x.py", project_root=tmp_path)
    assert repair.content == text
    assert set(repair.skipped) == {"json", "sep"}


# ----------------------------------------------------------------------- scanner


def test_the_vulture_is_admitted_and_project_rooted() -> None:
    assert get_admitted_scanners()[VULTURE_DEAD_IMPORT_SCANNER_ID] is (
        vulture_dead_import_scanner
    )
    assert vulture_dead_import_scanner.project_rooted is True


def test_one_finding_per_file_with_the_names_as_evidence(tmp_path) -> None:
    root = _project(tmp_path)
    findings = {f.target_id: f for f in _scan(root)}
    assert set(findings) == {"pkg/mod.py", "pkg/other.py"}
    mod = findings["pkg/mod.py"]
    assert mod.deterministic_evidence == (
        "3 dead import(s) in pkg/mod.py: OrderedDict, deque, json"
    )
    assert (
        mod.fingerprint
        == hashlib.sha256(b"vulture_dead_imports:pkg/mod.py:dead_imports").hexdigest()
    )


def test_a_target_narrows_what_is_reported_not_what_is_read(tmp_path) -> None:
    root = _project(tmp_path)
    assert [f.target_id for f in _scan(root, "pkg/mod.py")] == ["pkg/mod.py"]


def test_a_scan_rooted_below_the_project_is_refused(tmp_path) -> None:
    root = _project(tmp_path)
    with pytest.raises(ScanExecutionError, match="project root"):
        AutonomousMaintenanceForce(MaintenanceLifecycleEngine()).run_bounded_scan(
            _contract(root / "pkg"), vulture_dead_import_scanner
        )


def test_the_contract_bounds_the_index_too(tmp_path) -> None:
    root = _project(tmp_path)
    with pytest.raises(ScanExecutionError, match="max_files"):
        _scan(root, max_files=2)


def test_the_rescan_judges_the_repaired_target_not_the_whole_project(
    tmp_path,
) -> None:
    root = _project(tmp_path)
    (root / "pkg/mod.py").write_text("import os\n\nos.sep\n", encoding="utf-8")
    run = VerifierRegistry(scanner_adapters=get_admitted_scanners()).run(
        VerifierSpec(
            scanner_id=VULTURE_DEAD_IMPORT_SCANNER_ID,
            scanner_version="1",
            target_id="pkg/mod.py",
            rescan_of="fingerprint",
            allowed_root=str(root),
        ),
        contract=_contract(root),
        scanner=vulture_dead_import_scanner,
    )
    # pkg/other.py still has a dead import; the repaired file is clean.
    assert run.status == "completed" and run.passed


# --------------------------------------------------------------------- executors


def _job(workspace: Path, target: str, op: str = REMOVE_DEAD_IMPORTS_V1):
    return ExecutorJob(
        job_id="job-dead-imports",
        mission_contract_digest="digest-dead-imports",
        capability=ExecutorCapability(
            capability_id="cap-dead-imports",
            action_digest="action-dead-imports",
            mission_contract_digest="digest-dead-imports",
            expires_at="2099-12-31T23:59:59Z",
        ),
        image="test-image",
        argv=("repair", op, target),
        workspace_snapshot=str(workspace),
        resource_limits=ResourceLimits(
            timeout_seconds=60,
            max_output_bytes=100_000,
            memory_budget_mb=512,
            cpu_budget=1.0,
            pids_limit=100,
        ),
        verification_expectation={},
    )


def test_the_executor_service_runs_the_operation_and_keeps_crlf(
    tmp_path, monkeypatch
) -> None:
    root = _project(tmp_path / "ws")
    (root / "pkg/mod.py").write_bytes(MOD.replace("\n", "\r\n").encode())
    monkeypatch.setenv("AIOS_EXECUTOR_WORKSPACE_ROOT", str(tmp_path))
    result = execute_registered_operation_in_service(_job(root, "pkg/mod.py"))
    assert result.status == "completed", result.reason
    assert (root / "pkg/mod.py").read_bytes() == (
        b"import os\r\n\r\n\r\ndef sep():\r\n    return os.sep\r\n"
    )


def test_the_in_process_executor_writes_bytes_not_text(tmp_path) -> None:
    root = _project(tmp_path)
    (root / "pkg/mod.py").write_bytes(MOD.replace("\n", "\r\n").encode())
    execute_registered_repair_operation(_job(root, "pkg/mod.py"))
    assert b"\r\r\n" not in (root / "pkg/mod.py").read_bytes()


def test_an_unregistered_operation_is_still_refused(tmp_path, monkeypatch) -> None:
    root = _project(tmp_path / "ws")
    monkeypatch.setenv("AIOS_EXECUTOR_WORKSPACE_ROOT", str(tmp_path))
    result = execute_registered_operation_in_service(
        _job(root, "pkg/mod.py", op="DELETE_EVERYTHING_V1")
    )
    assert result.status == "failed" and "unsupported" in result.reason


# ----------------------------------------------------------------- staging, smoke


def test_staging_refuses_a_staging_root_inside_the_project(tmp_path) -> None:
    root = _project(tmp_path / "p")
    manager = StagedWorkspaceManager(root / "data" / "staged", enrolled_roots=(root,))
    with pytest.raises(WorkspacePathViolation, match="inside the project"):
        manager.stage("mission-1", root)


def test_the_smoke_finds_the_tests_that_exercise_a_file(tmp_path) -> None:
    root = _project(tmp_path)
    # Imports the module but takes no name from it: still exercises it.
    (root / "tests/test_alias.py").write_text(
        "import pkg.mod as m\n\n\ndef test_it():\n    assert m\n", encoding="utf-8"
    )
    assert find_exercising_tests(root, [root / "pkg/mod.py"]) == [
        root / "tests/test_alias.py",
        root / "tests/test_mod.py",
    ]


def test_a_module_consumed_dynamically_has_no_dead_imports(tmp_path) -> None:
    root = _project(tmp_path)
    (root / "tests/test_dyn.py").write_text(
        "import pkg.mod as m\n\nname = 'js' + 'on'\ngetattr(m, name)\n",
        encoding="utf-8",
    )
    assert [f.target_id for f in _scan(root)] == ["pkg/other.py"]


def test_the_smoke_fails_a_file_that_does_not_compile(tmp_path) -> None:
    root = _project(tmp_path)
    (root / "pkg/mod.py").write_text("def broken(:\n", encoding="utf-8")
    report = python_smoke(root, ["pkg/mod.py"], timeout_s=120)
    assert not report.passed and "does not compile" in report.reason


def test_the_smoke_never_imports_a_loose_script(tmp_path) -> None:
    root = _project(tmp_path)
    (root / "script.py").write_text(
        "from pathlib import Path\nPath('ran.txt').write_text('x')\n", encoding="utf-8"
    )
    report = python_smoke(root, ["script.py"], timeout_s=120)
    assert report.passed, report.reason
    assert not (root / "ran.txt").exists()


def test_the_production_smoke_verifier_runs_the_real_check(
    tmp_path, monkeypatch
) -> None:
    from aios import config
    from aios.api.deps import get_promotion_smoke_verifier

    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    root = _project(tmp_path / "p")
    (root / "pkg/mod.py").write_text("import os\nos.sep(\n", encoding="utf-8")
    verify = get_promotion_smoke_verifier(promotion_authority=None)
    request = SimpleNamespace(
        project_root=str(root), required_targets=("pkg/mod.py",), mission_id="m-1"
    )
    assert verify(request) is False
    assert list((tmp_path / "data" / "maintenance_smoke").glob("m-1-*.json"))


# -------------------------------------------------------------------- end to end


@pytest.fixture()
def mission_env(tmp_path, monkeypatch):
    staged = tmp_path / "staged"
    monkeypatch.setenv("AIOS_EXECUTOR_WORKSPACE_ROOT", str(staged))

    def build(project: Path):
        workspace = StagedWorkspaceManager(staged, enrolled_roots=(project,))
        foundry = WorkerFoundry(
            workspace_manager=workspace,
            strategies={
                WorkerStrategyName.CODE.value: ProductionCodeWorkerStrategy(
                    workspace_manager=workspace
                )
            },
            emergency_stop=UNGOVERNED_FIXTURE,
        )
        service = MaintenanceConvergenceService(
            finding_repository=MaintenanceFindingRepository(tmp_path / "op.db"),
            scan_repository=MaintenanceScanRepository(tmp_path / "op.db"),
            mission_service=MissionService(
                SqliteMissionRepository(tmp_path / "missions.db"),
                workspace_manager=workspace,
                emergency_stop=UNGOVERNED_FIXTURE,
            ),
            worker_foundry=foundry,
            # The function the private executor service dispatches repairs to.
            executor_service=ExecutorService(
                profile="test",
                runner=execute_registered_operation_in_service,
                backend_name="private_service",
            ),
            verifier_registry=VerifierRegistry(
                scanner_adapters=get_admitted_scanners()
            ),
            verification_authority=VerificationAuthority(),
            promotion_authority=PromotionAuthority(
                workspace, emergency_stop=UNGOVERNED_FIXTURE
            ),
            workspace_manager=workspace,
            lifecycle_engine=MaintenanceLifecycleEngine(),
            emergency_stop=UNGOVERNED_FIXTURE,
        )
        return service

    return build


async def _run_mission(service, project: Path, proof_db: Path):
    scan = service.run_scan(
        _contract(project),
        vulture_dead_import_scanner,
        scanner_id=VULTURE_DEAD_IMPORT_SCANNER_ID,
        scanner_version="1",
        target_id=".",
        source_digest="initial",
    )
    assert scan.scan.status == "completed"
    finding = next(f for f in scan.findings if f.target_id == "pkg/mod.py")
    record = service.create_repair_mission(
        finding.fingerprint, operator_id="op-1", workspace_root=str(project)
    )
    mission_id = record.mission_id
    service.mission_service.start_deliberation(mission_id)
    service.mission_service.request_approval(mission_id)
    service.mission_service.approve(
        mission_id,
        operator_id="op-1",
        capability_digest="cap-1",
        contract_digest=record.contract_digest,
        authentication_event_id="auth-1",
        session_id="session-1",
    )
    snapshot = {p: p.read_bytes() for p in project.rglob("*") if p.is_file()}

    def restore(_checkpoint, _request) -> bool:
        for path, data in snapshot.items():
            path.write_bytes(data)
        return True

    return await service.run_approved_repair(
        mission_id,
        scanner=vulture_dead_import_scanner,
        rescan_contract=_contract(project),
        capability_consumer=lambda _r: True,
        consumed_capability_proof=consume_real_capability_proof(
            proof_db, mission_id=mission_id
        ),
        create_checkpoint=lambda _r: "cp-1",
        restore_checkpoint=restore,
        smoke_test=lambda r: (
            python_smoke(Path(r.project_root), r.required_targets, timeout_s=300).passed
        ),
    )


@pytest.mark.anyio
async def test_the_mission_repairs_dead_imports_end_to_end(
    tmp_path, mission_env
) -> None:
    project = _project(tmp_path / "project")
    result = await _run_mission(mission_env(project), project, tmp_path / "caps.db")
    assert result.status == "VERIFIED_RESOLVED", result.reason
    assert (project / "pkg/mod.py").read_text(encoding="utf-8") == (
        "import os\n\n\ndef sep():\n    return os.sep\n"
    )
    # The other file's dead import is another finding, untouched.
    assert (project / "pkg/other.py").read_text(encoding="utf-8") == "import sys\n"


@pytest.mark.anyio
async def test_the_smoke_rolls_back_a_repair_a_test_proves_wrong(
    tmp_path, mission_env
) -> None:
    project = _project(tmp_path / "project", dynamic_use=True)
    result = await _run_mission(mission_env(project), project, tmp_path / "caps.db")
    assert result.status == "PROMOTION_FAILED", result.reason
    assert "rolled_back" in result.reason or "checkpoint_restored" in result.reason
    assert (project / "pkg/mod.py").read_text(encoding="utf-8") == MOD
