"""Facts two parts of GAGOS each keep, held equal (2026-11-04, the operator:
"I want u to make my cross-system consistency of my project 10/10 honestly
100%"; docs/architecture/CONSISTENCY_REGISTER.md).

Each test names the fact and fails when its places disagree. Where one place
could be the source, the others now import it and the test pins that no
second copy returns; where two must stay separate (a frontend and a backend,
a frozen core and the code around it), the test compares them.
"""

from __future__ import annotations

import ast
import re
import shutil
import sys
import typing
from pathlib import Path
from types import SimpleNamespace

import pytest

from aios import config

ROOT = Path(__file__).resolve().parents[1]


def _text(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


# --- What may leave the machine: the law's names and default ----------------


def test_the_env_template_names_the_laws_cloud_task_classes() -> None:
    from aios.bootstrap import default_env_contents
    from aios.security import limits

    said = re.search(r"valid names:\n# ([a-z_, ]+)\)", default_env_contents())
    assert said, "the template no longer names the valid classes"
    names = {n.strip() for n in said.group(1).split(",")}
    assert names == set(limits._VALID_ROUTER_TASKS), (
        "the .env template must name exactly the cloud-task classes the law "
        "accepts (aios/security/limits.py); until 2026-11-04 it named general "
        "and fast, which the law silently drops"
    )


def test_config_keeps_no_copy_of_the_law() -> None:
    for name in (
        "_VALID_ROUTER_TASKS",
        "_env_router_tasks",
        "_ROUTER_CLOUD_TASKS_DEFAULT",
    ):
        assert not hasattr(config, name), f"aios/config.py copies the law's {name}"


def test_the_shipped_default_is_read_from_the_law_itself(tmp_path: Path) -> None:
    from tools.thesis_audit import shipped_cloud_tasks

    assert shipped_cloud_tasks() == ()
    copy = tmp_path / "aios" / "security"
    copy.mkdir(parents=True)
    law = _text("aios/security/limits.py")
    opened = law.replace(
        'ROUTER_CLOUD_TASKS: Final[tuple[str, ...]] = _env_router_tasks(\n    "AIOS_ROUTER_CLOUD_TASKS", ()\n)',
        'ROUTER_CLOUD_TASKS: Final[tuple[str, ...]] = _env_router_tasks(\n    "AIOS_ROUTER_CLOUD_TASKS", ("reasoning",)\n)',
    )
    assert opened != law, "the law's assignment changed shape; update this test"
    (copy / "limits.py").write_text(opened, encoding="utf-8")
    assert shipped_cloud_tasks(tmp_path) == ("reasoning",), "a widened default is seen"


# --- One setting, one name ---------------------------------------------------


def test_bootstrap_checks_the_ollama_address_the_runtime_reads() -> None:
    from aios.bootstrap import default_env_contents

    source = _text("aios/bootstrap.py")
    assert 'os.getenv("OLLAMA_HOST"' in source and 'getenv("OLLAMA_HOST"' in _text(
        "aios/config.py"
    ).replace('_env_str("OLLAMA_HOST"', 'getenv("OLLAMA_HOST"')
    assert "\nOLLAMA_HOST=" in default_env_contents()
    for top in ("aios", "tools"):
        for path in (ROOT / top).rglob("*.py"):
            assert "AIOS_OLLAMA_URL" not in path.read_text(encoding="utf-8").replace(
                "this checked AIOS_OLLAMA_URL", ""
            ), f"{path.relative_to(ROOT)} names AIOS_OLLAMA_URL, which nothing reads"


def _ports(rel: str, pattern: str) -> set[int]:
    found = {int(m) for m in re.findall(pattern, _text(rel))}
    assert found, f"{rel} no longer matches {pattern!r}; update this test"
    return found


def test_every_default_port_agrees() -> None:
    """The counter, the executor and the face each have one port, read from
    each place's own source (so the operator's environment cannot hide a
    disagreement)."""
    counter = (
        _ports("aios/config.py", r'"AIOS_API_PORT", (\d+)')
        | _ports("aios/launcher.py", r'"AIOS_API_PORT", (\d+)')
        | _ports(
            "tools/daily_backend.py", r"^BACKEND_PORT = (\d+)$".replace("^", "(?m)^")
        )
        | _ports("frontend/src/config.js", r"localhost:(\d+)")
        | _ports("frontend/vite.config.js", r"localhost:(\d+)")
    )
    executor = (
        _ports("aios/config.py", r'"AIOS_EXECUTOR_URL", "http://127\.0\.0\.1:(\d+)"')
        | _ports("aios/executor_service.py", r'"AIOS_EXECUTOR_PORT", "(\d+)"')
        | _ports("tools/daily_backend.py", r"(?m)^EXECUTOR_PORT = (\d+)$")
    )
    face = _ports("tools/daily_backend.py", r"(?m)^FACE_PORT = (\d+)$")
    allowed = _ports("aios/config.py", r"http://localhost:(\d+)")
    assert (counter, executor, face) == ({8000}, {8081}, {5173})
    assert face <= allowed, "the counter's CORS default must allow the face's origin"


# --- Where things are stored -------------------------------------------------

#: Modules whose ``.db`` names are a scenario's own temporary stores.
_SCENARIOS = {
    "aios/application/governance/runtime_proof.py",
    "aios/application/governance/r15_runtime_proof.py",
    "aios/application/governance/adversarial_simulations.py",
    # The rebuild drill runs before the clone it rebuilds is importable.
    "tools/rebuild_drill.py",
}


def _db_literals() -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}
    for top in ("aios", "tools"):
        for path in (ROOT / top).rglob("*.py"):
            rel = path.relative_to(ROOT).as_posix()
            if rel in _SCENARIOS:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                value = getattr(node, "value", None)
                if (
                    isinstance(node, ast.Constant)
                    and isinstance(value, str)
                    and value.endswith(".db")
                    and value != ".db"
                ):
                    found.setdefault(value, set()).add(rel)
    return found


def test_a_store_file_name_has_one_home() -> None:
    """A database file is named once: by aios/config.py, or by the module that
    owns it. On 2026-11-04 the launcher's provenance command opened a file
    nothing wrote, missions.db was named four times and eleven tools rebuilt
    config's names by hand."""
    owned = {
        value.name
        for key, value in vars(config).items()
        if key.endswith(("_DB_PATH", "_DB")) and isinstance(value, Path)
    }
    problems = []
    for name, files in sorted(_db_literals().items()):
        if name in owned and files != {"aios/config.py"}:
            problems.append(
                f"{name}: config names it, and so do {sorted(files - {'aios/config.py'})}"
            )
        elif name not in owned and len(files) > 1:
            problems.append(f"{name}: named in {sorted(files)}")
    assert not problems, "\n".join(problems)


def test_the_workshop_and_the_counter_open_one_ledger(monkeypatch) -> None:
    from aios.api.routes import gagos_tasks
    from aios.maintenance import daily_work
    from tools import gagos_daily

    for module in (gagos_tasks, gagos_daily):
        monkeypatch.setattr(
            module, "DailyLedger", lambda path: SimpleNamespace(path=path)
        )
    assert gagos_daily.ledger().path == gagos_tasks.get_gagos_task_ledger().path
    assert gagos_daily.ledger().path == daily_work.ledger_path()


def test_the_executor_is_pointed_at_a_staging_root_the_scope_lock_pins() -> None:
    from aios.security.scope_lock import ScopeLockAuthority
    from tools import daily_backend

    assert ScopeLockAuthority(roots=[ROOT]).is_pinned_staging_root(
        daily_backend.staged_root()
    )


def test_the_daily_backend_names_the_sandboxs_image() -> None:
    from aios.maintenance import sandbox_tests
    from tools import daily_backend

    requirements = (ROOT / "requirements.txt").read_bytes()
    assert daily_backend.verify_image() == sandbox_tests.verify_image(requirements)


# --- The backend's vocabularies, as the face reads them ----------------------


def _js_list(rel: str, name: str) -> list[str]:
    found = re.search(rf"{name}\s*=\s*\[([^\]]*)\]", _text(rel))
    assert found, f"{rel} no longer defines {name}"
    return re.findall(r"'([^']+)'", found.group(1))


def test_the_face_offers_repair_in_the_states_the_backend_repairs_from() -> None:
    from aios.domain.maintenance.lifecycle import REPAIRABLE_STATES

    rel = "frontend/src/workbench/MaintenanceCenterPanel.jsx"
    assert set(_js_list(rel, "REPAIRABLE_STATUSES")) == set(REPAIRABLE_STATES)
    assert "REPAIRABLE_STATUSES.includes(finding.status)" in _text(rel)


def test_the_faces_skill_states_are_the_backends() -> None:
    from aios.domain.learning.skill_contracts import SkillState

    face = _js_list(
        "frontend/src/livingMirror/contracts.ts", "export const skillStates"
    )
    assert face == list(typing.get_args(SkillState)), (
        "the face throws on a skill state it does not know"
    )


def test_every_task_status_has_its_face_style_and_no_other() -> None:
    from aios.maintenance.daily_work import TASK_STATUSES

    styled = set(
        re.findall(
            r"\.gagos-tasks__status--([a-z]+)",
            _text("frontend/src/workbench/GagosTasksPanel.css"),
        )
    )
    assert styled == set(TASK_STATUSES)


# --- How the operator's CLIs are asked ---------------------------------------


def _contains(argv: list[str], part: tuple[str, ...]) -> bool:
    return any(tuple(argv[i : i + len(part)]) == part for i in range(len(argv)))


def test_the_workshop_asks_the_clis_sealed_as_the_plan_client_does(
    monkeypatch, tmp_path
) -> None:
    from aios.core import plan_cli
    from tools import gagos_daily

    seen: list[list[str]] = []

    def fake_run(argv, **kwargs):
        seen.append(list(argv))
        if "-o" in argv:
            Path(argv[argv.index("-o") + 1]).write_text(
                '{"verdict":"accept","reason":"ok"}', encoding="utf-8"
            )
        out = '{"structured_output":{"verdict":"accept","reason":"ok"},"modelUsage":{"m":{}}}'
        return SimpleNamespace(returncode=0, stdout=out, stderr="")

    monkeypatch.setattr(gagos_daily.subprocess, "run", fake_run)
    monkeypatch.setattr(gagos_daily, "_claude_executable", lambda: "claude")
    monkeypatch.setattr(gagos_daily, "_codex_executable", lambda: "codex")
    monkeypatch.setattr(gagos_daily, "codex_settings", lambda: {})
    for runner in (gagos_daily.run_claude, gagos_daily.run_codex):
        try:
            runner("p", model="m", timeout_s=5)
        except gagos_daily.ReviewUnavailable:
            pass
    claude_argv, codex_argv = seen
    assert _contains(claude_argv, plan_cli.CLAUDE_SEALED)
    assert _contains(codex_argv, plan_cli.CODEX_SEALED)


def test_the_workshop_finds_codex_as_the_plan_client_does(monkeypatch) -> None:
    from tools import gagos_daily

    monkeypatch.setattr(gagos_daily, "_codex_executable", lambda: None)
    monkeypatch.setattr(shutil, "which", lambda name: "C:/npm/codex.cmd")
    with pytest.raises(gagos_daily.ReviewUnavailable, match="shim is refused"):
        gagos_daily.run_codex("p", model="m", timeout_s=5)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(pytest.main([__file__, "-q"]))


# --- The operator's plans: which models, by which name -----------------------


def test_the_plan_models_agree_across_the_counter_the_workshop_and_the_face() -> None:
    """The daily backend offers the plan models; the workshop writes with some
    of them; the face's menu names two; the report names each. aios/config.py
    offers none by default on purpose (opt-in), so these agree only as the
    daily backend starts the counter, and this keeps them agreeing there."""
    from tools import daily_backend, gagos_daily

    offered = set(daily_backend.PLAN_CLAUDE) | set(daily_backend.PLAN_CODEX)
    assert set(gagos_daily.CLAUDE_WRITERS) <= set(daily_backend.PLAN_CLAUDE)
    assert set(gagos_daily.CODEX_WRITERS) <= set(daily_backend.PLAN_CODEX)
    menu = re.findall(
        r"id: 'plan\.([^']+)'", _text("frontend/src/workbench/GagosChrome.jsx")
    )
    assert menu and set(menu) <= offered, (
        "the face offers a plan model the counter does not"
    )
    assert offered <= set(gagos_daily.MODEL_NAMES), (
        "a plan model without a name in the report"
    )


# --- Which profile GAGOS runs as ---------------------------------------------


def test_one_default_profile() -> None:
    """AIOS_PROFILE is read through config.profile(), with one default. Until
    2026-11-09 the private executor service defaulted to production and every
    other reader to development, so one process held two profiles. Two places
    keep their own read: aios/core/executor.py, which this work does not edit
    (its default must be the one default), and the launcher, whose default is
    the profile it launches, not the one it runs as."""
    found: dict[str, set] = {}
    for top in ("aios", "tools"):
        for path in (ROOT / top).rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not (isinstance(node, ast.Call) and node.args):
                    continue
                first = node.args[0]
                if not (
                    isinstance(first, ast.Constant) and first.value == "AIOS_PROFILE"
                ):
                    continue
                default = node.args[1] if len(node.args) > 1 else None
                value = default.value if isinstance(default, ast.Constant) else None
                found.setdefault(path.relative_to(ROOT).as_posix(), set()).add(value)
    assert set(found) == {
        "aios/config.py",
        "aios/core/executor.py",
        "aios/launcher.py",
    }, found
    assert found["aios/core/executor.py"] == {config.DEFAULT_PROFILE}


def test_the_operators_counter_runs_as_production(monkeypatch) -> None:
    from tools import daily_backend

    assert daily_backend.daily_settings()["AIOS_PROFILE"] == "production"
    monkeypatch.delenv("AIOS_PROFILE", raising=False)
    assert config.profile() == config.DEFAULT_PROFILE == "development"


# --- Whether tests passed: two questions, one rule each ----------------------


def test_a_verification_command_is_judged_one_way() -> None:
    """ "Did this command succeed?" is asked by the Verifier (the Testing queen,
    the tool agent) and the VerificationAuthority (maintenance). Both decide on
    the exit code, count tests with one parser and derive strength one way:
    until 2026-11-09 the Verifier kept its own copy of the count parser."""
    from tests.source_rules import executable_source
    from aios.application.evidence import verification
    from aios.core import verification_strength, verifier

    verifier_src = executable_source(verifier)
    assert "result.exit_code == 0" in verifier_src
    assert "observation.exit_code == 0" in executable_source(verification)
    for src in (verifier_src, executable_source(verification)):
        assert "derive_strength(" in src
    assert "parse_test_counts(" in verifier_src
    assert "re.compile" not in verifier_src, "a second count parser"
    assert verification_strength.parse_test_counts("3 passed, 1 failed") == (3, 1)


def test_did_a_change_break_a_test_is_asked_one_way() -> None:
    """ "Did this change break a test that passed before?" is the workshop's
    question, judged against the base by the sandbox alone: no other module
    calls it, and the workshop asks nothing else."""
    found = []
    for top in ("aios", "tools"):
        for path in (ROOT / top).rglob("*.py"):
            if "run_change_tests(" in path.read_text(encoding="utf-8"):
                found.append(path.relative_to(ROOT).as_posix())
    assert sorted(found) == [
        "aios/maintenance/sandbox_tests.py",
        "tools/gagos_daily.py",
    ]


# --- Settings read in more than one place ------------------------------------

_READERS = {
    "getenv",
    "get",
    "_env_str",
    "_env_int",
    "_env_bool",
    "_env_path",
    "_env_float",
    "_int_env",
}

#: Settings read in several files whose readers do not share one literal
#: default, each with its reason. Anything else read twice must agree.
SETTING_EXCEPTIONS: dict[str, str] = {
    "AIOS_PROFILE": "config.profile() is the reader; aios/core/executor.py is pinned to its "
    "default (test_one_default_profile); the launcher's default is what it launches",
    "AIOS_DATA_DIR": "config's default, the launcher's launch root and the construction "
    "ledger's per-call read all name <repo>/data; bootstrap only checks it is set",
    "AIOS_EXECUTOR_WORKSPACE_ROOT": "where the process that runs jobs keeps them: the backend's "
    "DATA_DIR on the host, /workspace/jobs inside the executor's container",
    "AIOS_VERIFICATION_AUTHORITY_KEY": "config and the authority read the AIOS_ name, then "
    "the legacy one, in the same order",
    "AIOS_PROMOTION_AUTHORITY_KEY": "as the verification key",
    "AIOS_CHECKPOINT_AUTHORITY_KEY": "as the verification key",
    "AIOS_LLM_MODEL": "the sovereignty drills default to config.LLM_MODEL itself",
    "AIOS_BEDROCK_REGION": "the workshop takes the setting or config.BEDROCK_REGION",
    "AIOS_CRAG": "the red-team runner reads it only to record the operator's value",
}


def _setting_reads() -> dict[str, dict[str, set[str]]]:
    reads: dict[str, dict[str, set[str]]] = {}
    for top in ("aios", "tools"):
        for path in (ROOT / top).rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if not (isinstance(node, ast.Call) and node.args):
                    continue
                func = node.func
                name = (
                    func.attr
                    if isinstance(func, ast.Attribute)
                    else getattr(func, "id", "")
                )
                if name not in _READERS:
                    continue
                if name == "get" and not (
                    isinstance(func, ast.Attribute)
                    and getattr(func.value, "attr", getattr(func.value, "id", ""))
                    == "environ"
                ):
                    continue
                first = node.args[0]
                if not (
                    isinstance(first, ast.Constant)
                    and str(first.value).startswith("AIOS_")
                ):
                    continue
                default = ast.unparse(node.args[1]) if len(node.args) > 1 else ""
                if default in ("None", "''", '""'):
                    default = ""  # unset and empty read alike
                rel = path.relative_to(ROOT).as_posix()
                reads.setdefault(first.value, {}).setdefault(rel, set()).add(default)
    return reads


def test_a_setting_read_in_several_places_has_one_default() -> None:
    """18 of 198 AIOS_* settings were read in more than one file (2026-11-04).
    Read twice, a setting must agree on its default everywhere, or be named in
    SETTING_EXCEPTIONS with why it differs."""
    disagree, stale = [], []
    reads = _setting_reads()
    for setting, by_file in reads.items():
        if len(by_file) < 2:
            continue
        defaults = set().union(*by_file.values())
        if len(defaults) > 1 and setting not in SETTING_EXCEPTIONS:
            disagree.append(f"{setting}: {dict(sorted(by_file.items()))}")
    for setting in SETTING_EXCEPTIONS:
        if len(reads.get(setting, {})) < 2:
            stale.append(setting)
    assert not disagree, "\n".join(disagree)
    assert not stale, f"exceptions no longer read twice, so remove them: {stale}"


def test_the_test_key_rule_is_written_once() -> None:
    """When a missing signing key may fall back to a placeholder: four modules
    spelled it out until 2026-11-09 (aios/core/signing_keys.py now)."""
    reads = _setting_reads()
    assert set(reads["AIOS_TEST_SIGNING_KEYS_ALLOWED"]) == {"aios/core/signing_keys.py"}
    assert set(reads["AIOS_ENV"]) == {"aios/core/signing_keys.py"}


def test_rollbacks_and_checkpoints_each_have_their_own_setting() -> None:
    """AIOS_ROLLBACK_DIR named both the rollback engine's git directory and the
    promotion checkpoints' store until 2026-11-09: one setting, two meanings."""
    reads = _setting_reads()
    assert set(reads["AIOS_ROLLBACK_DIR"]) == {"aios/config.py"}
    assert set(reads["AIOS_CHECKPOINT_DIR"]) == {
        "aios/application/promotion/checkpoint.py"
    }


# --- Whether a brain can serve now ---------------------------------------------

_SESSION = "model call failed: LLMError: Claude Code exited 1: You've hit your session limit · resets 3:10pm (Asia/Kolkata)"
_WEEKLY = "model call failed: LLMError: Claude Code exited 1: You've hit your weekly limit · resets Nov 7, 9:30pm (Asia/Kolkata)"
_CODEX = "model call failed: LLMError: Codex exited 1: usageLimitExceeded"
_AWS = "model call failed: LLMError: Bedrock Converse failed for 'deepseek.v3.2': An error occurred (AccessDeniedException)"


def test_a_usage_limit_is_neither_a_refusal_nor_one_models_absence() -> None:
    from aios.core import model_availability as ma

    for limit in (_SESSION, _WEEKLY, _CODEX):
        assert ma.is_usage_limit_error(limit), limit
        assert not ma.is_model_unavailable_error(limit), limit
    assert not ma.is_usage_limit_error(_AWS)


def test_the_workshop_rests_a_writer_at_its_limit_and_queues_a_refused_one(
    tmp_path,
) -> None:
    """Until 2026-11-09 a plan writer at its session limit was 'refused', and
    the one probe a batch went to the longest refused writer: it waited behind
    every writer AWS had refused."""
    from aios.maintenance import daily_work as dw

    led = dw.DailyLedger(tmp_path / "l.db")
    finding = dw.Finding(
        rel="frontend/src/a.js", rule="no-unused-vars", warnings=((1, 1, "x"),)
    )
    for model, refusal in (
        ("deepseek.v3.2", _AWS),
        ("mistral.devstral-2-123b", _AWS),
        ("claude-haiku-5-5", _SESSION),
        ("gpt-6-luna", _CODEX),
    ):
        led.record_proposal(
            finding,
            base_text="x\n",
            base_commit="c" * 40,
            model=model,
            new_text=None,
            verdict=None,
            refusal=refusal,
        )
    writers = (
        "deepseek.v3.2",
        "mistral.devstral-2-123b",
        "claude-haiku-5-5",
        "gpt-6-luna",
        "claude-sonnet-5-5",
    )
    assert led.refused_writers(writers) == ["deepseek.v3.2", "mistral.devstral-2-123b"]
    assert led.resting_writers(writers) == ["claude-haiku-5-5", "gpt-6-luna"]


def test_the_workshop_classifies_failures_as_the_router_does() -> None:
    source = _text("aios/maintenance/daily_work.py")
    assert "from aios.core.model_availability import is_usage_limit_error" in source


def test_a_tool_ci_pins_is_pinned_as_the_lock_pins_it() -> None:
    """2026-11-10, a review of the whole codebase: CI installed mypy 2.3.1
    over requirements.txt's 2.4.1, so the type gate ran a version nobody had
    locked. Every ``name==version`` a workflow installs that the lock also pins
    must name the same version."""
    lock = {}
    for line in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines():
        found = re.match(r"^([A-Za-z0-9_.\-\[\]]+)==([^\s;#]+)", line.strip())
        if found:
            lock[found.group(1).split("[")[0].lower()] = found.group(2)
    drift = []
    for workflow in sorted((ROOT / ".github" / "workflows").glob("*.yml")):
        for line in workflow.read_text(encoding="utf-8").splitlines():
            if "pip install" not in line:
                continue
            for name, version in re.findall(
                r"\b([A-Za-z0-9_.\-]+)==([0-9][^\s\"']*)", line
            ):
                pinned = lock.get(name.lower())
                if pinned is not None and pinned != version:
                    drift.append(f"{workflow.name}: {name}=={version}, lock {pinned}")
    assert not drift, drift
