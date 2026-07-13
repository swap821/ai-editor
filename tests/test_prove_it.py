"""Hermetic smoke test for prove_it.py.

Exercises prove_it.py's SCRIPTED mode against the REAL FastAPI app object
(real executor/approval store/verifier/skills/development stores, hermetic
temp DBs -- only the Ollama dependency is overridden). Non-network: scripted
mode never touches Ollama or a spawned server, so this test needs nothing
running.

Each scenario is run as its own ``.venv\\Scripts\\python prove_it.py --scripted
[--sabotage X]`` subprocess. This is required, not incidental: prove_it.py's
own hermetic-ordering guard refuses to run a second time in a process that has
already imported ``aios`` (the same guard that protects a real run from
silently binding to the wrong DB), so exercising multiple scenarios means
exercising the CLI the same way an operator actually invokes it -- one
process per run. Each invocation has an ~11-15s fixed floor (real aios/FastAPI
import cost, not this test's own work), so the number of subprocess-driving
scenarios below is deliberately kept to four (one clean + three sabotage) to
stay well under the 60s budget -- see the comment above the parametrize list.

Two things are asserted:
1. The clean run's checklist is INTERNALLY HONEST: steps 1-5 (BOOT, DIRECTIVE,
   SUPERVISION, APPROVAL, ACTION) genuinely PROVE against the real app today,
   each with a PROVED/FAILED line and real evidence/WHY text. This does NOT
   assert all 7 steps pass -- prove_it.py's job is to report the organism's
   real state, not perform one. (See PROVE_IT.md's troubleshooting table for
   a separately-flagged, real production finding that this run's own honest
   VERIFY step surfaces in this environment.)
2. The prover CAN fail, honestly: three independent sabotage hooks each force
   one working step to its failure condition and assert the run reports
   FAILED with a real WHY and a nonzero exit code -- proving prove_it.py is
   not hardcoded to print PROVED.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
VENV_PYTHON = REPO_ROOT / ".venv" / "Scripts" / "python.exe"
PROVE_IT = REPO_ROOT / "prove_it.py"

pytestmark = pytest.mark.slow


def _run_prove_it(*extra_args: str, timeout: float = 45.0) -> subprocess.CompletedProcess:
    exe = str(VENV_PYTHON) if VENV_PYTHON.exists() else sys.executable
    return subprocess.run(
        [exe, str(PROVE_IT), "--scripted", *extra_args],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _step_lines(stdout: str) -> dict[str, tuple[bool, str]]:
    """Parse the printed checklist into {STEP_NAME: (proved, why-or-evidence-blob)}.

    Only the FIRST (Checklist.record-emitted, detail-bearing) listing is
    parsed -- print_footer() reprints a bare "[STATUS] N. NAME" summary line
    per step with no evidence/WHY text, so parsing must stop before it or the
    summary's blank blobs would overwrite the real ones.
    """
    steps: dict[str, tuple[bool, str]] = {}
    current_name = None
    current_proved = False
    current_blob: list[str] = []
    for line in stdout.splitlines():
        if line.startswith("="):  # print_footer's separator rule
            break
        stripped = line.strip()
        if stripped.startswith("[PROVED]") or stripped.startswith("[FAILED]"):
            if current_name is not None:
                steps[current_name] = (current_proved, "\n".join(current_blob))
            proved = stripped.startswith("[PROVED]")
            # "[PROVED] 3. SUPERVISION" -> "SUPERVISION"
            rest = stripped.split("]", 1)[1].strip()
            name = rest.split(".", 1)[1].strip() if "." in rest else rest
            current_name = name
            current_proved = proved
            current_blob = []
        elif stripped.startswith("evidence:") or stripped.startswith("WHY:"):
            current_blob.append(stripped)
    if current_name is not None:
        steps[current_name] = (current_proved, "\n".join(current_blob))
    return steps


# --------------------------------------------------------------------------
# 1. The clean run is internally honest.
# --------------------------------------------------------------------------


def test_scripted_run_is_internally_honest():
    result = _run_prove_it()
    steps = _step_lines(result.stdout)

    assert steps, f"no checklist steps parsed from output:\n{result.stdout}"

    for name, (proved, blob) in steps.items():
        if proved:
            assert blob, f"step {name} is PROVED with no evidence line:\n{result.stdout}"
            assert "WHY:" not in blob, f"step {name} is PROVED but also carries a WHY:\n{blob}"
        else:
            assert "WHY:" in blob, f"step {name} is FAILED with no WHY line:\n{blob}"

    # The core supervised-loop beats this prover exists to demonstrate must be
    # genuinely provable against the real app object today: a directive is
    # issued, the write PAUSES for approval before anything hits disk, the
    # approval resume actually runs, and the file really lands on disk.
    for required in ("BOOT", "DIRECTIVE", "SUPERVISION", "APPROVAL", "ACTION"):
        assert required in steps, f"expected a {required} step in:\n{result.stdout}"
        proved, blob = steps[required]
        assert proved, f"{required} did not PROVE against the real app:\n{blob}"

    # The footer's honesty-clause banner requirement: SCRIPTED must be
    # unmistakably labeled, never confusable with a real/live brain.
    assert "SCRIPTED BRAIN" in result.stdout
    assert "SIMULATED" in result.stdout
    assert "LIVE BRAIN" not in result.stdout

    # The process's own exit code must agree with whether every parsed step
    # PROVED -- never a green summary text next to a nonzero/zero mismatch.
    all_proved = all(proved for proved, _ in steps.values())
    assert (result.returncode == 0) == all_proved, (
        f"exit code {result.returncode} disagrees with parsed steps "
        f"(all_proved={all_proved}):\n{result.stdout}"
    )


# --------------------------------------------------------------------------
# 2. The prover can fail, honestly -- sabotage hooks.
# --------------------------------------------------------------------------


#: Three sabotage scenarios, each mapped to a genuinely distinct architectural
#: gate this prover exists to demonstrate: SUPERVISION (the pause itself never
#: fires), APPROVAL (the resume mechanism is fed a bad token), LEARNING (the
#: evidence-recording DB lookup is redirected after everything else genuinely
#: ran). A fourth (ACTION) is intentionally not covered here to keep this
#: file's runtime budget -- each subprocess invocation has an ~11-15s fixed
#: floor (real aios/FastAPI import + startup cost, not this test's own work)
#: so every added case costs real wall-clock time; the three kept are the
#: minimum that still exercises an early-loop gate, a resume-loop gate, and a
#: post-loop evidence gate without redundant overlap.
@pytest.mark.parametrize(
    "sabotage,failing_step_name",
    [
        ("supervision", "SUPERVISION"),
        ("approval", "APPROVAL"),
        ("learning", "LEARNING"),
    ],
)
def test_sabotage_forces_honest_failure(sabotage, failing_step_name):
    """Forcing one step's evidence to be absent must make the run report
    FAILED (with a real WHY) and return nonzero -- proving the checklist is
    not hardcoded to always print PROVED. This is the harness's own
    self-test: a prover that can never fail cannot be trusted when it
    succeeds.

    The ``learning`` case additionally proves the sabotage is narrowly
    targeted, not a whole-run short-circuit: LEARNING sabotage only redirects
    the DB lookup *after* the real write+approval+verify machinery already
    ran, so BOOT/DIRECTIVE/SUPERVISION/APPROVAL/ACTION must still PROVE."""
    result = _run_prove_it("--sabotage", sabotage)
    steps = _step_lines(result.stdout)

    assert result.returncode != 0, (
        f"sabotage={sabotage} should have made prove_it.py exit nonzero:\n{result.stdout}"
    )
    assert failing_step_name in steps, (
        f"sabotage={sabotage} should have produced a {failing_step_name} step "
        f"(steps seen: {list(steps)}):\n{result.stdout}"
    )
    proved, blob = steps[failing_step_name]
    assert not proved, f"sabotage={sabotage} should have made {failing_step_name} FAIL"
    assert "WHY:" in blob, f"sabotage={sabotage}: {failing_step_name} is FAILED but has no WHY"
    assert "RUN FAILED" in result.stdout

    if sabotage == "learning":
        for required in ("BOOT", "DIRECTIVE", "SUPERVISION", "APPROVAL", "ACTION"):
            assert required in steps, f"missing {required}:\n{result.stdout}"
            req_proved, req_blob = steps[required]
            assert req_proved, (
                f"sabotage=learning should not affect {required}, but it FAILED:\n{req_blob}"
            )


# --------------------------------------------------------------------------
# 3. training_ground/ sandbox hygiene -- the .git exclusion is load-bearing.
#    (Pure in-process unit tests: no aios import, so no subprocess needed.)
# --------------------------------------------------------------------------


def _import_prove_it_utils():
    import importlib

    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    return importlib.import_module("prove_it")


def test_walk_scope_files_never_yields_anything_under_git(tmp_path):
    """Regression guard for the exact incident called out in this task's hard
    constraints: cleanup logic must exclude .git categorically BEFORE
    walking, or it risks corrupting the RollbackEngine's snapshot repo."""
    prove_it = _import_prove_it_utils()
    scope_root = tmp_path / "training_ground"
    (scope_root / ".git" / "objects").mkdir(parents=True)
    (scope_root / ".git" / "objects" / "deadbeef").write_text("not a real git object")
    (scope_root / ".git" / "HEAD").write_text("ref: refs/heads/master\n")
    (scope_root / "ordinary_file.py").write_text("# ordinary\n")
    (scope_root / "subdir").mkdir()
    (scope_root / "subdir" / "nested.py").write_text("# nested\n")

    seen = {p.relative_to(scope_root) for p in prove_it._walk_scope_files(scope_root)}

    # The load-bearing invariant: no path *under* .git is ever yielded -- the
    # bare top-level ".git" directory entry itself may appear (snapshot/
    # restore both filter to is_file() before acting, so a bare directory
    # node is inert), but nothing inside it may leak through.
    for rel in seen:
        assert rel.parts[0] != ".git" or len(rel.parts) == 1, (
            f"a path INSIDE .git leaked through _walk_scope_files: {rel}"
        )
    assert Path("ordinary_file.py") in seen
    assert Path("subdir") / "nested.py" in seen


def test_restore_training_ground_never_deletes_inside_git(tmp_path):
    """Even if a file were somehow added under .git between snapshot and
    restore, restore_training_ground must never touch it."""
    prove_it = _import_prove_it_utils()
    scope_root = tmp_path / "training_ground"
    (scope_root / ".git" / "objects").mkdir(parents=True)
    git_object = scope_root / ".git" / "objects" / "deadbeef"
    git_object.write_text("not a real git object")

    before = prove_it.snapshot_training_ground(scope_root)
    assert not any(".git" in b for b in before), ".git content leaked into the snapshot"

    # Simulate new files appearing (as a real demo run would), INCLUDING one
    # that lands inside .git (the adversarial case the hard constraint warns
    # about) -- restore must delete the ordinary new file but leave .git alone.
    (scope_root / "new_demo_file.py").write_text("# demo\n")
    (scope_root / ".git" / "objects" / "newblob").write_text("also not real")

    deleted = prove_it.restore_training_ground(scope_root, before)

    assert "new_demo_file.py" in deleted
    assert not (scope_root / "new_demo_file.py").exists()
    assert git_object.exists(), ".git/objects/deadbeef was touched by restore"
    assert (scope_root / ".git" / "objects" / "newblob").exists(), (
        "restore_training_ground deleted something under .git -- this is exactly "
        "the corruption incident the hard constraints warn about"
    )


def test_cleanup_stale_rollback_pointer_removes_only_broken_pointer(tmp_path):
    """A prior interrupted prover must not poison the next isolated run.

    RollbackEngine stores its git database outside the sandbox and leaves a
    ``gitdir:`` pointer in ``training_ground/.git``. The pointer itself is
    safe to remove when its target is already gone; rollback database contents
    remain outside the sandbox and are never traversed by cleanup.
    """
    prove_it = _import_prove_it_utils()
    scope_root = tmp_path / "training_ground"
    scope_root.mkdir()
    pointer = scope_root / ".git"
    pointer.write_text("gitdir: C:/missing/prove-it-rollback\n", encoding="utf-8")

    prove_it.cleanup_stale_rollback_pointer(scope_root)

    assert not pointer.exists()
