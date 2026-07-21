"""Unit tests for memory compaction and experience distillation."""

import json
from pathlib import Path
import pytest

from aios.memory.compaction import MemoryCompactor


def test_distill_experiences(tmp_path: Path):
    exp_file = tmp_path / "experiences.jsonl"
    trusted_file = tmp_path / "trusted_workflows.md"

    # Write test experiences
    exp_data = [
        {"ts": "2026-06-01T00:00:00Z", "outcome": "success: test pass", "lessons": "Always verify inputs.", "confidence": 0.9},
        {"ts": "2026-06-01T01:00:00Z", "outcome": "failure: test fail", "lessons": "Low confidence lesson.", "confidence": 0.3},
        {"ts": "2026-06-01T02:00:00Z", "outcome": "success: test pass 2", "lessons": "Always verify inputs.", "confidence": 0.85}, # Duplicate
        {"ts": "2026-06-01T03:00:00Z", "outcome": "success: test pass 3", "lessons": "Keep functions pure.", "confidence": 0.88},
    ]

    with open(exp_file, "w", encoding="utf-8") as f:
        for entry in exp_data:
            f.write(json.dumps(entry) + "\n")

    compactor = MemoryCompactor()

    # Test dry run
    res_dry = compactor.distill_experiences(exp_file, trusted_file, min_confidence=0.8, dry_run=True)
    assert res_dry["experiences_total"] == 4
    assert res_dry["trusted_workflows_added"] == 2
    assert not trusted_file.exists()

    # Test real run
    res_real = compactor.distill_experiences(exp_file, trusted_file, min_confidence=0.8, dry_run=False)
    assert res_real["trusted_workflows_added"] == 2
    assert trusted_file.exists()

    content = trusted_file.read_text(encoding="utf-8")
    assert "Always verify inputs." in content
    assert "Keep functions pure." in content
