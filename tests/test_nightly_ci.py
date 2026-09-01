"""The nightly workflow exists, is scheduled, and its gate has teeth.

Ultra-plan Phase 8 / inventory item 88: "No scheduled/nightly CI workflow exists
— every automation tool is manual-only."

Verified before the workflow was written: `codeql.yml` held the repository's
only `schedule:` trigger, and `tools/learning_loop_prover.py` and
`tools/endurance_tester.py` were invoked by nothing at all. The concrete
consequence in item 88's words: the README's "19/19 learning-loop prover, stable
across repeated runs" claim was evidenced only by manual local runs, never by an
artifact anyone else could fetch.

These tests assert the two things that make a nightly real:

1. it is actually SCHEDULED and actually invokes the tools, and
2. its endurance gate fails on a broken harness rather than rubber-stamping
   whatever the log happens to contain.

They do not run the nightly. That needs Ollama, a live backend, and tens of
minutes; the workflow is where that belongs.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "nightly.yml"
CHECK = REPO_ROOT / "scripts" / "ci_nightly_endurance_check.py"


def _load_check():
    spec = importlib.util.spec_from_file_location("_endurance_check", CHECK)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --------------------------------------------------------------------------- #
# The workflow
# --------------------------------------------------------------------------- #
def test_the_nightly_workflow_is_actually_scheduled() -> None:
    """A "nightly" that only runs on dispatch is a manual tool with a new name.

    `golden-cohort-local` and `release-strict-gate` were both dispatch-only and
    consequently never ran at all until someone noticed. That is the failure
    this item exists to end.
    """
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "schedule:" in text, "the nightly workflow has no schedule trigger"
    assert "cron:" in text
    assert "workflow_dispatch:" in text, (
        "a scheduled workflow with no manual trigger cannot be debugged without "
        "waiting a day for the next run"
    )


def test_the_nightly_invokes_the_tools_no_other_workflow_ran() -> None:
    """The specific tools item 88 named as invoked by nothing."""
    text = WORKFLOW.read_text(encoding="utf-8")
    for tool in ("tools/learning_loop_prover.py", "tools/endurance_tester.py"):
        assert tool in text, f"{tool} is still invoked by no workflow"


def test_the_prover_is_gated_on_its_exit_code_not_swallowed() -> None:
    """`|| true` here would make the job prove nothing.

    The prover has a first-class answer for "the model is small": `--lenient`
    downgrades the LLM-obedience-dependent checks to warnings while structural
    checks still fail. Using it means the exit code is a real gate on the
    learning CHAIN, which is the thing worth gating on.
    """
    text = WORKFLOW.read_text(encoding="utf-8")
    prover_line = next(
        line for line in text.splitlines() if "learning_loop_prover.py run" in line
    )
    assert "--lenient" in prover_line, (
        "the prover must run --lenient in CI, or a small model's disobedience "
        "fails the nightly for reasons unrelated to the chain"
    )
    assert "|| true" not in prover_line, (
        "the prover's exit code is swallowed; with --lenient it is a real "
        "harness gate and must be allowed to fail the job"
    )


def test_readiness_is_waited_on_rather_than_liveness() -> None:
    """`/health` returns ok from a process that cannot serve a turn.

    Waiting on it would start the prover against a backend whose database is
    unwritable or which can reach no model, and blame the resulting failure on
    the model. `/ready` was added in #269 for exactly this.
    """
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "/ready" in text
    assert "8300/health" not in text and "8301/health" not in text, (
        "the nightly waits on the liveness probe instead of the readiness probe"
    )


# --------------------------------------------------------------------------- #
# The endurance gate
# --------------------------------------------------------------------------- #
_GOOD_LOG = """\
[endurance] turn 1 ok
[endurance] turn 2 ok

[endurance] RED
  turns: 12
  success rate: 0.42 (threshold: 0.80)
  latency p50=9.1s p95=31.0s baseline_p95=20.0s
  duration: 10.0 minutes
"""


def test_a_completed_run_passes_even_when_the_model_scored_RED() -> None:
    """The whole point: score is not the gate.

    A CI-sized model on a 2-core runner will be RED. Failing on that would
    create pressure to pick a model that flatters the suite -- the exact
    reasoning `local-clerk-live` and `ci_local_cohort_check.py` already record.
    """
    assert _load_check().check(_GOOD_LOG) == []


@pytest.mark.parametrize(
    "log, expected_fragment",
    [
        ("[endurance] turn 1 ok\n(process died here)\n", "never printed its summary"),
        (
            "[endurance] ABORT: 5 consecutive errors\n\n[endurance] RED\n  turns: 5\n",
            "ABORTED on consecutive errors",
        ),
        ("\n[endurance] RED\n  turns: 0\n", "zero turns"),
        (
            "\n[endurance] RED\n  turns: 4\nTraceback (most recent call last):\n",
            "infrastructure failure",
        ),
        (
            "\n[endurance] RED\n  turns: 4\n[endurance] backend unreachable: x\n",
            "infrastructure failure",
        ),
    ],
)
def test_a_broken_harness_fails(log: str, expected_fragment: str) -> None:
    """Each failure mode the gate exists to catch, exercised individually."""
    problems = _load_check().check(log)
    assert problems, f"expected a failure for: {expected_fragment}"
    assert any(expected_fragment in p for p in problems), problems


def test_the_gate_is_wired_into_the_workflow() -> None:
    """A check nobody invokes is a claim -- the fifth time in this repo."""
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "scripts/ci_nightly_endurance_check.py" in text
