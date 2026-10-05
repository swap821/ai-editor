"""Plan Phase 8b: the learning-guards workflow gates on the instruments.

A workflow that runs the probe without `--check`, runs the reel without its
gate, or whose shard matrix misses a shard would print green over a broken
guard -- the "apparatus that is only a document" failure the learning
ledger's LC2 exists to catch. Pinned here.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/learning-guards.yml"


def _workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _runs(job: dict) -> str:
    return "\n".join(str(step.get("run", "")) for step in job["steps"])


def test_it_can_be_dispatched() -> None:
    triggers = _workflow()[True]  # YAML 1.1 reads the `on:` key as True
    assert "workflow_dispatch" in triggers


def test_the_reel_is_gated_on_its_structural_verdicts() -> None:
    runs = _runs(_workflow()["jobs"]["reel"])
    assert "tools/learning_redteam_runner.py run" in runs
    assert "--out reel.json" in runs
    assert "scripts/learning_reel_gate.py reel.json" in runs


def test_every_probe_shard_runs_and_fails_on_a_survivor() -> None:
    job = _workflow()["jobs"]["probe"]
    runs = _runs(job)
    assert "--check" in runs
    (count,) = re.findall(r"--shard \$\{\{ matrix\.shard \}\}/(\d+)", runs)
    assert job["strategy"]["matrix"]["shard"] == list(range(int(count)))
    assert job["strategy"]["fail-fast"] is False
